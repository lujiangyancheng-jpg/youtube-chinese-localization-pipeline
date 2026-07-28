from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from ..config import DownloadConfig
from ..errors import InputValidationError, LocalizerError
from ..models import SourceMetadata
from ..utils.files import atomic_write_json

LOGGER = logging.getLogger(__name__)
YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def is_youtube_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in YOUTUBE_HOSTS


def youtube_video_id(value: str) -> str | None:
    if not is_youtube_url(value):
        return None
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = parse_qs(parsed.query).get("v", [""])[0]
    elif parsed.path.startswith(("/shorts/", "/live/", "/embed/")):
        candidate = parsed.path.strip("/").split("/")[1]
    else:
        return None
    return candidate if VIDEO_ID_RE.fullmatch(candidate or "") else None


def _youtube_dl(options: dict[str, Any]):
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise LocalizerError("yt-dlp is not installed. Run: python -m pip install yt-dlp") from exc
    return YoutubeDL(options)


def _validate_info(info: dict[str, Any]) -> None:
    availability = (info.get("availability") or "public").lower()
    if availability in {"private", "subscriber_only", "premium_only", "needs_auth"}:
        raise InputValidationError(
            f"This video is not publicly available ({availability}). "
            "The application does not bypass access controls."
        )
    if int(info.get("age_limit") or 0) >= 18:
        raise InputValidationError(
            "This video is age-restricted. Authenticated access is intentionally unsupported."
        )
    if info.get("is_drm") or info.get("_has_drm"):
        raise InputValidationError("DRM-protected videos are not supported.")
    if info.get("live_status") == "is_live":
        raise InputValidationError("Live streams must finish before they can be processed.")


def inspect_youtube(url: str) -> tuple[SourceMetadata, dict[str, Any]]:
    video_id = youtube_video_id(url)
    if not video_id:
        raise InputValidationError(
            "Invalid or unsupported YouTube URL. Use a public youtube.com/watch, shorts, live, "
            "embed, or youtu.be video URL."
        )
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
    }
    try:
        with _youtube_dl(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        if isinstance(exc, LocalizerError):
            raise
        raise InputValidationError(
            "yt-dlp could not inspect this video. Confirm that it is public, available in your "
            f"region, and not protected. Details: {exc}"
        ) from exc
    if not isinstance(info, dict):
        raise InputValidationError("yt-dlp did not return video metadata.")
    _validate_info(info)
    metadata = SourceMetadata(
        source_type="youtube",
        source_input=url,
        source_url=info.get("webpage_url") or url,
        video_id=str(info.get("id") or video_id),
        title=info.get("title") or f"YouTube video {video_id}",
        channel=info.get("channel") or info.get("uploader") or "",
        duration=float(info.get("duration") or 0),
        description=info.get("description") or "",
        upload_date=info.get("upload_date") or "",
        language=info.get("language") or "",
        thumbnail_url=info.get("thumbnail") or "",
        width=info.get("width"),
        height=info.get("height"),
        frame_rate=info.get("fps"),
        video_codec=info.get("vcodec") or "",
        audio_codec=info.get("acodec") or "",
    )
    return metadata, info


def choose_english_subtitle(info: dict[str, Any]) -> tuple[str, str] | None:
    manual = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    manual_languages = [language for language in manual if language == "en"]
    manual_languages += sorted(
        language for language in manual if language.lower().startswith("en-")
    )
    if manual_languages:
        return manual_languages[0], "creator"
    automatic_languages = [language for language in automatic if language == "en"]
    automatic_languages += sorted(
        language for language in automatic if language.lower().startswith("en-")
    )
    if automatic_languages:
        return automatic_languages[0], "automatic"
    return None


def download_youtube(
    url: str,
    info: dict[str, Any],
    destination_dir: Path,
    config: DownloadConfig,
) -> tuple[Path, Path | None, str, str]:
    destination_dir.mkdir(parents=True, exist_ok=True)
    subtitle = choose_english_subtitle(info)
    options: dict[str, Any] = {
        "quiet": False,
        "noplaylist": True,
        "continuedl": True,
        "overwrites": False,
        "format": config.format,
        "outtmpl": str(destination_dir / "download.%(ext)s"),
        "writesubtitles": bool(subtitle and subtitle[1] == "creator"),
        "writeautomaticsub": bool(subtitle and subtitle[1] == "automatic"),
        "subtitleslangs": [subtitle[0]] if subtitle else [],
        "subtitlesformat": "vtt/srt/best",
    }
    if config.prefer_mp4:
        options["merge_output_format"] = "mp4"
    try:
        with _youtube_dl(options) as ydl:
            downloaded_info = ydl.extract_info(url, download=True)
            prepared = Path(ydl.prepare_filename(downloaded_info))
    except Exception as exc:
        if isinstance(exc, LocalizerError):
            raise
        raise LocalizerError(
            "yt-dlp failed to download the public video. The partial download is retained so a "
            f"later --resume can continue it. Details: {exc}"
        ) from exc

    candidates = [
        path
        for path in destination_dir.glob("download.*")
        if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
        and ".part" not in path.name
    ]
    if prepared.is_file() and prepared not in candidates:
        candidates.append(prepared)
    if not candidates:
        raise LocalizerError("yt-dlp completed but no downloaded video file was found.")
    video = max(candidates, key=lambda item: item.stat().st_size)
    destination = destination_dir / f"source_video{video.suffix.lower()}"
    if video != destination:
        video.replace(destination)

    subtitle_file = None
    if subtitle:
        subtitle_candidates = sorted(
            [
                *destination_dir.glob("download*.vtt"),
                *destination_dir.glob("download*.srt"),
                *destination_dir.glob("download*.ass"),
            ]
        )
        if subtitle_candidates:
            original = subtitle_candidates[0]
            subtitle_file = destination_dir / f"source.en{original.suffix.lower()}"
            original.replace(subtitle_file)
    return (
        destination,
        subtitle_file,
        subtitle[0] if subtitle else "",
        subtitle[1] if subtitle else "",
    )


def save_thumbnail(url: str, destination: Path) -> None:
    if not url:
        return
    try:
        response = httpx.get(url, follow_redirects=True, timeout=30)
        response.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(response.content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
    except (httpx.HTTPError, OSError) as exc:
        LOGGER.warning("Thumbnail download failed; processing will continue: %s", exc)


def save_raw_metadata(info: dict[str, Any], destination: Path) -> None:
    safe = json.loads(json.dumps(info, ensure_ascii=False, default=str))
    atomic_write_json(destination, safe)
