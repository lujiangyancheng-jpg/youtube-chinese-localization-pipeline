from __future__ import annotations

from pathlib import Path

import pytest

from youtube_localizer.download.browser_capture import (
    _player_candidates,
    candidates_from_cdp_message,
    find_edge_executable,
    validate_browser_capture_page,
)


def test_network_response_extracts_only_media_url_and_safe_metadata() -> None:
    candidates = candidates_from_cdp_message(
        {
            "method": "Network.responseReceived",
            "params": {
                "type": "Media",
                "response": {
                    "url": "https://groupvideo.photo.qq.com/owned/video/resource/",
                    "mimeType": "video/mp4",
                    "headers": {
                        "Content-Length": "123456",
                        "Set-Cookie": "must-not-be-copied",
                        "Authorization": "must-not-be-copied",
                    },
                },
            },
        }
    )

    assert len(candidates) == 1
    assert candidates[0].url == "https://groupvideo.photo.qq.com/owned/video/resource/"
    assert candidates[0].source == "response"
    assert candidates[0].mime_type == "video/mp4"
    assert candidates[0].content_length == 123456
    assert not hasattr(candidates[0], "headers")


def test_non_media_network_response_is_ignored() -> None:
    assert not candidates_from_cdp_message(
        {
            "method": "Network.responseReceived",
            "params": {
                "type": "Script",
                "response": {
                    "url": "https://cdn.example.test/app.js",
                    "mimeType": "application/javascript",
                },
            },
        }
    )


def test_player_evaluation_prefers_current_media_url() -> None:
    candidates = _player_candidates(
        {
            "id": 7,
            "result": {
                "result": {
                    "type": "object",
                    "value": {
                        "title": "Authorized demo",
                        "media": [
                            "https://cdn.example.test/owned/demo.mp4?signature=current",
                            "blob:https://example.test/not-exportable",
                        ],
                    },
                }
            },
        }
    )

    assert len(candidates) == 1
    assert candidates[0].source == "player"
    assert candidates[0].priority == 0
    assert candidates[0].title == "Authorized demo"


def test_validate_browser_capture_page_checks_public_destination(monkeypatch) -> None:
    checked: list[str] = []
    monkeypatch.setattr(
        "youtube_localizer.download.browser_capture._assert_public_http_url",
        checked.append,
    )

    page = "https://www.example.test/play/episode.html"
    assert validate_browser_capture_page(f"  {page}  ") == page
    assert checked == [page]


def test_find_edge_executable_prefers_explicit_existing_candidate(tmp_path: Path) -> None:
    edge = tmp_path / "msedge.exe"
    edge.touch()
    assert find_edge_executable([edge]) == edge.resolve()


@pytest.mark.parametrize("value", ["", "C:/video.mp4", "ftp://example.test/video"])
def test_validate_browser_capture_page_rejects_non_web_pages(value: str) -> None:
    with pytest.raises(Exception, match="HTTP"):
        validate_browser_capture_page(value)
