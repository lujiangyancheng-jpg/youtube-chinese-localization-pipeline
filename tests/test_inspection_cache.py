from __future__ import annotations

from youtube_localizer import pipeline
from youtube_localizer.inspection_cache import (
    DIRECT_CACHE_TTL_SECONDS,
    REMOTE_CACHE_TTL_SECONDS,
    load_cached_inspection,
    save_cached_inspection,
)
from youtube_localizer.models import SourceMetadata


def test_remote_cache_restores_current_source_without_storing_signed_url(tmp_path) -> None:
    source = "https://cdn.example.test/video.mp4?token=secret"
    metadata = SourceMetadata(
        source_type="direct_media",
        source_input=source,
        source_url=source,
        video_id="video",
        title="Example",
    )

    path = save_cached_inspection(source, metadata, cache_directory=tmp_path, now=100)
    cached = load_cached_inspection(source, cache_directory=tmp_path, now=101)

    assert cached is not None
    assert cached.source_input == source
    assert cached.source_url == source
    serialized = path.read_text(encoding="utf-8")
    assert "token=secret" not in serialized


def test_cache_uses_shorter_ttl_for_direct_media_than_youtube(tmp_path) -> None:
    direct = "https://cdn.example.test/video.mp4"
    youtube = "https://youtu.be/abc123"
    save_cached_inspection(
        direct,
        SourceMetadata(
            source_type="direct_media",
            source_input=direct,
            video_id="direct",
            title="Direct",
        ),
        cache_directory=tmp_path,
        now=100,
    )
    save_cached_inspection(
        youtube,
        SourceMetadata(
            source_type="youtube",
            source_input=youtube,
            video_id="abc123",
            title="YouTube",
        ),
        cache_directory=tmp_path,
        now=100,
    )

    assert (
        load_cached_inspection(
            direct, cache_directory=tmp_path, now=100 + DIRECT_CACHE_TTL_SECONDS + 1
        )
        is None
    )
    assert (
        load_cached_inspection(
            youtube, cache_directory=tmp_path, now=100 + DIRECT_CACHE_TTL_SECONDS + 1
        )
        is not None
    )
    assert (
        load_cached_inspection(
            youtube, cache_directory=tmp_path, now=100 + REMOTE_CACHE_TTL_SECONDS + 1
        )
        is None
    )


def test_local_cache_is_invalidated_when_the_file_changes(tmp_path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"first")
    metadata = SourceMetadata(
        source_type="local",
        source_input=str(video),
        video_id="local",
        title="Local",
    )
    cache = tmp_path / "cache"
    save_cached_inspection(str(video), metadata, cache_directory=cache, now=100)

    assert load_cached_inspection(str(video), cache_directory=cache, now=101) is not None
    video.write_bytes(b"changed-content")
    assert load_cached_inspection(str(video), cache_directory=cache, now=102) is None


def test_pipeline_reuses_cached_remote_inspection_without_another_network_call(
    monkeypatch,
) -> None:
    source = "https://youtu.be/abc123"
    metadata = SourceMetadata(
        source_type="youtube",
        source_input=source,
        video_id="abc123",
        title="Cached",
    )
    monkeypatch.setattr(pipeline, "load_cached_inspection", lambda _source: metadata)
    monkeypatch.setattr(
        pipeline,
        "inspect_youtube",
        lambda _source: (_ for _ in ()).throw(AssertionError("network inspection repeated")),
    )

    inspected, raw = pipeline._inspect_input(source)

    assert inspected == metadata
    assert raw is not None
    assert raw["_localizer_inspection_cache"] is True
