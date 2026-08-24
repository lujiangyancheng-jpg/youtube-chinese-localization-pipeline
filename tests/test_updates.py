from __future__ import annotations

import httpx

from youtube_localizer.onboarding import REPOSITORY_API_URL
from youtube_localizer.updates import check_for_update, is_newer_version, version_key


def test_version_comparison_handles_v_prefixes_and_short_versions() -> None:
    assert version_key("v0.6.5") == (0, 6, 5)
    assert is_newer_version("v0.6.6", "0.6.5")
    assert not is_newer_version("0.6.5", "0.6.5.0")
    assert is_newer_version("0.7.0.2", "0.7.0.1")


def test_update_check_reports_an_available_public_release(monkeypatch) -> None:
    response = httpx.Response(
        200,
        json={"tag_name": "v9.0.0", "html_url": "https://example.test/releases/v9.0.0"},
        request=httpx.Request("GET", "https://example.test"),
    )
    monkeypatch.setattr("youtube_localizer.updates.httpx.get", lambda *args, **kwargs: response)

    result = check_for_update()

    assert result.status == "available"
    assert result.latest_version == "9.0.0"
    assert result.release_url == "https://example.test/releases/v9.0.0"


def test_update_check_uses_the_renamed_repository_and_follows_redirects(monkeypatch) -> None:
    captured: dict[str, object] = {}
    response = httpx.Response(
        200,
        json={"tag_name": "v0.7.0.10", "html_url": "https://example.test/current"},
        request=httpx.Request("GET", "https://example.test"),
    )

    def get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return response

    monkeypatch.setattr("youtube_localizer.updates.httpx.get", get)

    check_for_update()

    assert captured["url"] == f"{REPOSITORY_API_URL}/releases/latest"
    assert captured["follow_redirects"] is True


def test_update_check_degrades_cleanly_when_offline(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr("youtube_localizer.updates.httpx.get", fail)

    result = check_for_update()

    assert result.status == "unavailable"
    assert "offline" in result.detail


def test_development_channel_includes_prereleases_and_ignores_drafts(monkeypatch) -> None:
    response = httpx.Response(
        200,
        json=[
            {
                "tag_name": "v9.0.0.1",
                "html_url": "https://example.test/releases/v9.0.0.1",
                "prerelease": True,
                "draft": False,
            },
            {
                "tag_name": "v10.0.0.0",
                "html_url": "https://example.test/releases/draft",
                "prerelease": True,
                "draft": True,
            },
            {"tag_name": "not-semver", "draft": False},
        ],
        request=httpx.Request("GET", "https://example.test"),
    )
    monkeypatch.setattr("youtube_localizer.updates.httpx.get", lambda *args, **kwargs: response)

    result = check_for_update(channel="development")

    assert result.status == "available"
    assert result.channel == "development"
    assert result.latest_version == "9.0.0.1"
    assert result.release_url == "https://example.test/releases/v9.0.0.1"
