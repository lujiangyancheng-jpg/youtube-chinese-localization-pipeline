"""Small, explicit GitHub Release update checks for the desktop application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

from . import __version__
from .onboarding import REPOSITORY_URL

_LATEST_RELEASE_API = "https://api.github.com/repos/lujiangyancheng-jpg/youtube-chinese-localization-pipeline/releases/latest"
_RELEASES_API = "https://api.github.com/repos/lujiangyancheng-jpg/youtube-chinese-localization-pipeline/releases?per_page=30"
UpdateChannel = Literal["stable", "development"]


@dataclass(frozen=True)
class ReleaseCheck:
    status: str
    current_version: str
    channel: UpdateChannel = "stable"
    latest_version: str | None = None
    release_url: str | None = None
    detail: str = ""


def version_key(version: str) -> tuple[int, ...]:
    """Compare stable numeric versions without adding a packaging dependency."""
    normalized = version.strip().lstrip("vV")
    if not normalized or any(not part.isdigit() for part in normalized.split(".")):
        raise ValueError(f"Unsupported release version: {version!r}")
    return tuple(int(part) for part in normalized.split("."))


def is_newer_version(candidate: str, current: str = __version__) -> bool:
    candidate_key = version_key(candidate)
    current_key = version_key(current)
    width = max(len(candidate_key), len(current_key))
    return candidate_key + (0,) * (width - len(candidate_key)) > current_key + (0,) * (
        width - len(current_key)
    )


def _development_release(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, list):
        raise TypeError("GitHub development release feed was not a list.")
    candidates: list[tuple[tuple[int, ...], dict[str, Any]]] = []
    for item in payload:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        try:
            key = version_key(str(item["tag_name"]))
        except (KeyError, ValueError):
            continue
        candidates.append((key, item))
    if not candidates:
        raise ValueError("No numeric public release was found in the development feed.")
    return max(candidates, key=lambda candidate: candidate[0])[1]


def check_for_update(
    *, channel: UpdateChannel = "stable", timeout_seconds: float = 5.0
) -> ReleaseCheck:
    """Check the public release feed only when the user requests it.

    No machine identifier, source link, configuration, or API credential is sent.
    """
    if channel not in {"stable", "development"}:
        raise ValueError(f"Unsupported update channel: {channel}")
    try:
        response = httpx.get(
            _LATEST_RELEASE_API if channel == "stable" else _RELEASES_API,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Localize-Studio"},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        if channel == "development":
            payload = _development_release(payload)
        if not isinstance(payload, dict):
            raise TypeError("GitHub stable release feed was not an object.")
        tag_name = str(payload["tag_name"])
        html_url = str(payload.get("html_url") or REPOSITORY_URL + "/releases")
        latest_version = tag_name.lstrip("vV")
        if is_newer_version(latest_version):
            return ReleaseCheck(
                "available",
                __version__,
                channel=channel,
                latest_version=latest_version,
                release_url=html_url,
            )
        return ReleaseCheck(
            "current",
            __version__,
            channel=channel,
            latest_version=latest_version,
            release_url=html_url,
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        return ReleaseCheck("unavailable", __version__, channel=channel, detail=str(exc))
