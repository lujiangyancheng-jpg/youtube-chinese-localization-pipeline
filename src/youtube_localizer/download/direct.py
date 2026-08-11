"""Authorized direct-media URL support without webpage scraping or authentication."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from ..config import DownloadConfig
from ..errors import InputValidationError, LocalizerError
from ..models import SourceMetadata
from ..utils.hashing import hash_text
from .youtube import (
    _enable_javascript_runtime,
    _validate_info,
    _youtube_dl,
    download_media,
)

DIRECT_MEDIA_EXTENSIONS = frozenset(
    {".mp4", ".m4v", ".mkv", ".mov", ".webm", ".avi", ".m3u8", ".mpd"}
)


@dataclass(frozen=True)
class DirectMediaDownloadResult:
    video: Path
    warnings: tuple[str, ...] = ()


def _parsed_direct_media_url(value: str):
    try:
        return urlparse(value.strip())
    except ValueError:
        return None


def is_direct_media_url(value: str) -> bool:
    """Return whether *value* is a non-authenticated URL to an actual media resource.

    A playback page is deliberately not accepted.  Supporting only explicit media paths avoids
    website-specific scraping and keeps the feature within its authorized-download scope.
    """
    parsed = _parsed_direct_media_url(value)
    if not parsed:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
        and Path(unquote(parsed.path)).suffix.lower() in DIRECT_MEDIA_EXTENSIONS
    )


def direct_media_id(value: str) -> str:
    """Generate a stable project ID while allowing refreshed signed-query URLs to resume."""
    parsed = _parsed_direct_media_url(value)
    if not parsed or not is_direct_media_url(value):
        raise InputValidationError(
            "Direct media URLs must be an http(s) MP4, WebM, MOV, MKV, M3U8, or MPD address."
        )
    canonical = f"{parsed.hostname.lower()}{unquote(parsed.path)}"
    return hash_text(canonical)[:10]


def _fallback_title(value: str) -> str:
    parsed = _parsed_direct_media_url(value)
    if not parsed:
        return "Direct media"
    title = Path(unquote(parsed.path)).stem.strip()
    return title or "Direct media"


def inspect_direct_media(url: str) -> tuple[SourceMetadata, dict[str, Any]]:
    """Inspect a supplied public media file or HLS/DASH manifest with yt-dlp."""
    if not is_direct_media_url(url):
        raise InputValidationError(
            "This is not a direct media URL. Paste an authorized MP4, WebM, MOV, MKV, M3U8, "
            "or MPD address rather than a playback webpage."
        )
    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
    }
    _enable_javascript_runtime(options)
    try:
        with _youtube_dl(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        if isinstance(exc, LocalizerError):
            raise
        raise InputValidationError(
            "yt-dlp could not inspect this direct media URL. Confirm that the address is current, "
            "publicly accessible, not DRM-protected, and points to the media file or playlist. "
            f"Details: {exc}"
        ) from exc
    if not isinstance(info, dict):
        raise InputValidationError("yt-dlp did not return media metadata.")
    _validate_info(info)
    return (
        SourceMetadata(
            source_type="direct_media",
            source_input=url,
            source_url=url,
            video_id=direct_media_id(url),
            title=info.get("title") or _fallback_title(url),
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
        ),
        info,
    )


def download_direct_media(
    url: str,
    _info: dict[str, Any],
    destination_dir: Path,
    config: DownloadConfig,
) -> DirectMediaDownloadResult:
    """Download a user-supplied direct media URL at the configured best quality."""
    return DirectMediaDownloadResult(
        video=download_media(
            url,
            destination_dir,
            config,
            source_description="direct media URL",
        )
    )
