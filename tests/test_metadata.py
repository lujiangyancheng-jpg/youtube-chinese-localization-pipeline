from __future__ import annotations

from youtube_localizer.download.metadata import metadata_from_probe


def test_rotated_phone_video_uses_display_dimensions(tmp_path) -> None:
    source = tmp_path / "phone.mp4"
    data = {
        "format": {"duration": "2.0"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30/1",
                "side_data_list": [{"rotation": -90}],
            }
        ],
    }

    metadata = metadata_from_probe(source, data, video_id="phone")

    assert metadata.width == 1080
    assert metadata.height == 1920
