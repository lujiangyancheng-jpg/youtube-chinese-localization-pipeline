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


def test_probe_metadata_preserves_high_bit_depth_color_and_vfr_information(tmp_path) -> None:
    source = tmp_path / "hdr-vfr.mp4"
    data = {
        "format": {"duration": "2.0"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
                "avg_frame_rate": "24000/1001",
                "r_frame_rate": "60/1",
                "pix_fmt": "yuv420p10le",
                "color_space": "bt2020nc",
                "color_transfer": "smpte2084",
                "color_primaries": "bt2020",
            }
        ],
    }

    metadata = metadata_from_probe(source, data, video_id="hdr-vfr")

    assert metadata.pixel_format == "yuv420p10le"
    assert metadata.color_transfer == "smpte2084"
    assert metadata.variable_frame_rate is True
