from __future__ import annotations

from unittest.mock import patch

import pytest

from youtube_localizer.download import webpage
from youtube_localizer.download.webpage import (
    ResolvedWebpageMedia,
    inspect_webpage_media,
    resolve_webpage_media,
    webpage_media_id,
)
from youtube_localizer.errors import InputValidationError
from youtube_localizer.models import SourceMetadata
from youtube_localizer.pipeline import _inspect_input, _source_identifier


def _allow_public_urls(monkeypatch) -> None:
    monkeypatch.setattr(webpage, "_assert_public_http_url", lambda _value: None)


def test_resolver_accepts_relative_html5_video_source(monkeypatch) -> None:
    _allow_public_urls(monkeypatch)
    monkeypatch.setattr(
        webpage,
        "_fetch_public_html",
        lambda _url: (
            "https://media.example.com/watch/lesson.html",
            """
            <html><head><title> Authorized lesson </title></head>
            <body><video controls><source src="../assets/master.m3u8" type="application/x-mpegURL"></video></body></html>
            """,
        ),
    )

    resolved = resolve_webpage_media("https://media.example.com/watch/lesson.html")

    assert resolved.media_url == "https://media.example.com/assets/master.m3u8"
    assert resolved.page_title == "Authorized lesson"
    assert resolved.declaration == "HTML5 video source"


def test_resolver_accepts_video_object_content_url(monkeypatch) -> None:
    _allow_public_urls(monkeypatch)
    monkeypatch.setattr(
        webpage,
        "_fetch_public_html",
        lambda _url: (
            "https://creator.example.com/lessons/1",
            """
            <script type="application/ld+json">
            {"@context":"https://schema.org","@type":"VideoObject","name":"Course demo",
             "contentUrl":"https://cdn.example.com/course/demo.mp4",
             "thumbnailUrl":"/thumb.jpg"}
            </script>
            """,
        ),
    )

    resolved = resolve_webpage_media("https://creator.example.com/lessons/1")

    assert resolved.media_url == "https://cdn.example.com/course/demo.mp4"
    assert resolved.page_title == "Course demo"
    assert resolved.thumbnail_url == "https://creator.example.com/thumb.jpg"


def test_resolver_drops_a_private_thumbnail_without_rejecting_public_media(monkeypatch) -> None:
    monkeypatch.setattr(
        webpage,
        "_fetch_public_html",
        lambda _url: (
            "https://creator.example.com/watch/1.html",
            '<meta property="og:image" content="http://127.0.0.1/private.jpg">'
            '<video src="https://cdn.example.com/video.mp4"></video>',
        ),
    )

    def validate(value: str) -> None:
        if "127.0.0.1" in value:
            raise InputValidationError("blocked")

    monkeypatch.setattr(webpage, "_assert_public_http_url", validate)

    resolved = resolve_webpage_media("https://creator.example.com/watch/1.html")

    assert resolved.media_url == "https://cdn.example.com/video.mp4"
    assert resolved.thumbnail_url == ""


def test_resolver_rejects_iframe_only_and_script_only_pages(monkeypatch) -> None:
    _allow_public_urls(monkeypatch)
    monkeypatch.setattr(
        webpage,
        "_fetch_public_html",
        lambda _url: (
            "https://media.example.com/watch/1.html",
            '<iframe src="https://player.example.com/embed/1"></iframe>'
            '<script>window.player({token: "secret"})</script>',
        ),
    )

    with pytest.raises(InputValidationError, match="iframe"):
        resolve_webpage_media("https://media.example.com/watch/1.html")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/video.html",
        "http://[::1]/video.html",
        "http://169.254.169.254/latest/meta-data/",
    ],
)
def test_public_page_resolver_blocks_local_and_link_local_addresses(url) -> None:
    with pytest.raises(InputValidationError, match="公网地址"):
        webpage._assert_public_http_url(url)


def test_webpage_urls_reject_embedded_credentials() -> None:
    with pytest.raises(InputValidationError, match="用户名或密码"):
        webpage_media_id("https://user:password@example.com/watch/1.html")


def test_inspection_preserves_page_as_source_and_direct_url_for_acquisition(monkeypatch) -> None:
    source = "https://creator.example.com/watch/1.html"
    media = "https://cdn.example.com/assets/high.m3u8?token=current"
    monkeypatch.setattr(
        webpage,
        "_resolve_webpage_media_candidates",
        lambda _url: [
            ResolvedWebpageMedia(
                page_url=source,
                media_url=media,
                page_title="Creator lesson",
                description="Licensed course",
                thumbnail_url="https://creator.example.com/thumb.jpg",
                declaration="HTML5 video",
            )
        ],
    )
    _allow_public_urls(monkeypatch)
    monkeypatch.setattr(
        webpage,
        "inspect_direct_media",
        lambda _url: (
            SourceMetadata(
                source_type="direct_media",
                source_input=media,
                source_url=media,
                video_id="direct",
                title="high",
                duration=30,
                width=3840,
                height=2160,
            ),
            {"id": "direct", "formats": []},
        ),
    )

    metadata, info = inspect_webpage_media(source)

    assert metadata.source_type == "webpage_media"
    assert metadata.source_input == source
    assert metadata.source_url == media
    assert metadata.video_id == webpage_media_id(source)
    assert metadata.title == "Creator lesson"
    assert metadata.width == 3840
    assert info["_localizer_source_page"] == source


def test_inspection_falls_back_to_the_next_declared_media_candidate(monkeypatch) -> None:
    source = "https://creator.example.com/watch/1.html"
    first = "https://cdn.example.com/stale.m3u8"
    second = "https://cdn.example.com/current.mp4"
    monkeypatch.setattr(
        webpage,
        "_resolve_webpage_media_candidates",
        lambda _url: [
            ResolvedWebpageMedia(source, first, "Lesson", declaration="HTML5 video"),
            ResolvedWebpageMedia(source, second, "Lesson", declaration="og:video"),
        ],
    )
    _allow_public_urls(monkeypatch)
    calls: list[str] = []

    def inspect(candidate: str):
        calls.append(candidate)
        if candidate == first:
            raise InputValidationError("expired")
        return (
            SourceMetadata(
                source_type="direct_media",
                source_input=candidate,
                source_url=candidate,
                video_id="direct",
                title="Lesson",
            ),
            {"id": "direct"},
        )

    monkeypatch.setattr(webpage, "inspect_direct_media", inspect)

    metadata, _ = inspect_webpage_media(source)

    assert calls == [first, second]
    assert metadata.source_url == second


def test_pipeline_routes_playback_pages_to_the_public_page_inspector(monkeypatch) -> None:
    source = "https://creator.example.com/watch/1.html"
    metadata = SourceMetadata(
        source_type="webpage_media",
        source_input=source,
        source_url="https://cdn.example.com/video.mp4",
        video_id=webpage_media_id(source),
        title="Creator lesson",
    )
    monkeypatch.setattr("youtube_localizer.pipeline.load_cached_inspection", lambda _value: None)
    monkeypatch.setattr(
        "youtube_localizer.pipeline.inspect_webpage_media",
        lambda _value: (metadata, {"id": "remote"}),
    )

    inspected, raw = _inspect_input(source)

    assert inspected == metadata
    assert raw == {"id": "remote"}
    assert _source_identifier(source) == metadata.video_id


def test_example_cloudflare_page_reports_supported_boundary() -> None:
    response = type(
        "FakeResponse",
        (),
        {"status_code": 403, "headers": {"cf-mitigated": "challenge"}},
    )()

    class FakeStream:
        def __enter__(self):
            return response

        def __exit__(self, *_args):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return FakeStream()

    with (
        patch.object(webpage, "_assert_public_http_url"),
        patch.object(webpage.httpx, "Client", FakeClient),
        pytest.raises(InputValidationError, match="Cloudflare"),
    ):
        webpage._fetch_public_html("https://www.lmm85.com/play/8164_1_1.html")
