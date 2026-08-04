from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
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
SIMPLIFIED_CHINESE_LANGUAGES = ("zh-Hans", "zh-CN", "zh")


@dataclass(frozen=True)
class YouTubeDownloadResult:
    video: Path
    english_subtitle: Path | None = None
    english_language: str = ""
    english_kind: str = ""
    chinese_subtitle: Path | None = None
    chinese_language: str = ""
    chinese_kind: str = ""
    warnings: tuple[str, ...] = ()


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


def _matching_language(catalog: dict[str, Any], wanted: tuple[str, ...]) -> str | None:
    by_casefold = {language.casefold(): language for language in catalog}
    for preferred in wanted:
        match = by_casefold.get(preferred.casefold())
        if match:
            return match
    return None


def choose_chinese_subtitle(info: dict[str, Any]) -> tuple[str, str] | None:
    """Prefer creator Simplified Chinese captions, then YouTube automatic captions."""
    manual = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    manual_language = _matching_language(manual, SIMPLIFIED_CHINESE_LANGUAGES)
    if manual_language:
        return manual_language, "creator"
    automatic_language = _matching_language(automatic, SIMPLIFIED_CHINESE_LANGUAGES)
    if automatic_language:
        return automatic_language, "automatic"
    return None


def _downloaded_subtitle(destination_dir: Path, language: str) -> Path | None:
    wanted = f".{language}.".casefold()
    candidates = sorted(
        path
        for path in destination_dir.glob("download*.*")
        if path.suffix.lower() in {".vtt", ".srt", ".ass"}
        and wanted in path.name.casefold()
    )
    return candidates[0] if candidates else None


def _run_youtube_download(url: str, options: dict[str, Any]) -> Path:
    with _youtube_dl(options) as ydl:
        downloaded_info = ydl.extract_info(url, download=True)
        if not isinstance(downloaded_info, dict):
            raise LocalizerError("yt-dlp did not return downloaded video information.")
        return Path(ydl.prepare_filename(downloaded_info))


def _is_optional_subtitle_failure(exc: BaseException) -> bool:
    return "unable to download video subtitles" in str(exc).casefold()


def download_youtube(
    url: str,
    info: dict[str, Any],
    destination_dir: Path,
    config: DownloadConfig,
) -> YouTubeDownloadResult:
    destination_dir.mkdir(parents=True, exist_ok=True)
    english = choose_english_subtitle(info)
    chinese = choose_chinese_subtitle(info) if config.prefer_youtube_chinese else None
    selections = [selection for selection in (english, chinese) if selection is not None]
    options: dict[str, Any] = {
        "quiet": False,
        "noplaylist": True,
        "continuedl": True,
        "overwrites": False,
        "format": config.format,
        "format_sort": list(config.format_sort),
        "outtmpl": str(destination_dir / "download.%(ext)s"),
        "writesubtitles": any(selection[1] == "creator" for selection in selections),
        "writeautomaticsub": any(selection[1] == "automatic" for selection in selections),
        "subtitleslangs": list(dict.fromkeys(selection[0] for selection in selections)),
        "subtitlesformat": "vtt/srt/best",
    }
    if config.prefer_mp4:
        options["merge_output_format"] = "mp4"
    download_warnings: list[str] = []
    try:
        prepared = _run_youtube_download(url, options)
    except Exception as exc:
        if isinstance(exc, LocalizerError):
            raise
        if selections and _is_optional_subtitle_failure(exc):
            warning = (
                "YouTube temporarily rejected one or more optional subtitle downloads. "
                "The video download will continue without the unavailable captions; the pipeline "
                "will use another caption track or local Whisper transcription."
            )
            LOGGER.warning("%s Details: %s", warning, exc)
            download_warnings.append(warning)
            video_only_options = {
                **options,
                "writesubtitles": False,
                "writeautomaticsub": False,
                "subtitleslangs": [],
            }
            try:
                prepared = _run_youtube_download(url, video_only_options)
            except Exception as retry_exc:
                if isinstance(retry_exc, LocalizerError):
                    raise
                raise LocalizerError(
                    "yt-dlp failed to download the public video after the optional subtitle "
                    "fallback. The partial download is retained so a later --resume can continue "
                    f"it. Details: {retry_exc}"
                ) from retry_exc
        else:
            raise LocalizerError(
                "yt-dlp failed to download the public video. The partial download is retained so "
                f"a later --resume can continue it. Details: {exc}"
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

    english_file = None
    if english:
        original = _downloaded_subtitle(destination_dir, english[0])
        if original:
            english_file = destination_dir / f"source.en{original.suffix.lower()}"
            original.replace(english_file)
    chinese_file = None
    if chinese:
        original = _downloaded_subtitle(destination_dir, chinese[0])
        if original:
            chinese_file = destination_dir / f"source.zh{original.suffix.lower()}"
            original.replace(chinese_file)
    return YouTubeDownloadResult(
        video=destination,
        english_subtitle=english_file,
        english_language=english[0] if english and english_file else "",
        english_kind=english[1] if english and english_file else "",
        chinese_subtitle=chinese_file,
        chinese_language=chinese[0] if chinese and chinese_file else "",
        chinese_kind=chinese[1] if chinese and chinese_file else "",
        warnings=tuple(download_warnings),
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
