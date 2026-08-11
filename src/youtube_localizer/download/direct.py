"""Authorized direct-media URL support without webpage scraping or authentication."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx

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
PLAYBACK_PAGE_EXTENSIONS = frozenset({".asp", ".aspx", ".htm", ".html", ".jsp", ".php"})
DIRECT_MEDIA_CONTENT_TYPES = frozenset(
    {
        "application/dash+xml",
        "application/vnd.apple.mpegurl",
        "application/x-mpegurl",
        "audio/mpegurl",
    }
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


def is_direct_media_candidate_url(value: str) -> bool:
    """Return whether *value* can safely be checked as an explicit media address.

    A playback-page extension is rejected before any request. URLs without a file extension are
    allowed here because large CDNs commonly serve MP4 files from opaque paths.
    """
    parsed = _parsed_direct_media_url(value)
    if not parsed:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
        and Path(unquote(parsed.path)).suffix.lower() not in PLAYBACK_PAGE_EXTENSIONS
    )


def is_direct_media_url(value: str) -> bool:
    """Return whether *value* names a media URL through a known filename extension."""
    parsed = _parsed_direct_media_url(value)
    return bool(
        parsed
        and is_direct_media_candidate_url(value)
        and Path(unquote(parsed.path)).suffix.lower() in DIRECT_MEDIA_EXTENSIONS
    )


def _content_type_is_media(content_type: str) -> bool:
    normalized = content_type.partition(";")[0].strip().lower()
    return normalized.startswith(("video/", "audio/")) or normalized in DIRECT_MEDIA_CONTENT_TYPES


def _probe_direct_media_content_type(url: str) -> str:
    """Verify an extensionless URL from response headers, without fetching the video body."""
    headers = {"Accept": "video/*,audio/*,application/dash+xml,application/vnd.apple.mpegurl"}
    try:
        response = httpx.head(url, headers=headers, follow_redirects=True, timeout=20)
        if response.status_code not in {405, 501}:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if _content_type_is_media(content_type):
                return content_type
            raise InputValidationError(
                "The direct URL did not identify itself as video or an HLS/DASH playlist. "
                "Paste the actual media address, not a playback webpage."
            )
    except httpx.HTTPError as exc:
        raise InputValidationError(
            "Could not verify this extensionless direct media URL. Confirm that it is current, "
            "publicly accessible, and not protected."
        ) from exc

    # Some CDNs reject HEAD but permit a one-byte range probe. The stream context ensures that
    # this validation never downloads the media body.
    try:
        with httpx.stream(
            "GET",
            url,
            headers={**headers, "Range": "bytes=0-0"},
            follow_redirects=True,
            timeout=20,
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
    except httpx.HTTPError as exc:
        raise InputValidationError(
            "Could not verify this extensionless direct media URL. Confirm that it is current, "
            "publicly accessible, and not protected."
        ) from exc
    if not _content_type_is_media(content_type):
        raise InputValidationError(
            "The direct URL did not identify itself as video or an HLS/DASH playlist. "
            "Paste the actual media address, not a playback webpage."
        )
    return content_type


def direct_media_id(value: str) -> str:
    """Generate a stable project ID while allowing refreshed signed-query URLs to resume."""
    parsed = _parsed_direct_media_url(value)
    if not parsed or not is_direct_media_candidate_url(value):
        raise InputValidationError(
            "Direct media URLs must be an http(s) media address without login credentials."
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
    if not is_direct_media_candidate_url(url):
        raise InputValidationError(
            "This is not a direct media URL. Paste an authorized media address rather than a "
            "playback webpage or a URL with login credentials."
        )
    if not is_direct_media_url(url):
        _probe_direct_media_content_type(url)
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
