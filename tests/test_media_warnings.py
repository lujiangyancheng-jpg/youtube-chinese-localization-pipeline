from __future__ import annotations

from youtube_localizer.models import SourceMetadata
from youtube_localizer.rendering.media_warnings import (
    rendering_media_warnings,
    source_bit_depth,
)


def test_high_bit_depth_formats_are_recognized() -> None:
    assert source_bit_depth("yuv420p10le") == 10
    assert source_bit_depth("p010le") == 10
    assert source_bit_depth("yuv420p") is None


def test_hdr_and_vfr_sources_get_publishable_rendering_warnings() -> None:
    metadata = SourceMetadata(
        source_type="local",
        source_input="source.mp4",
        video_id="hdr",
        title="HDR source",
        pixel_format="yuv420p10le",
        color_transfer="smpte2084",
        color_primaries="bt2020",
        variable_frame_rate=True,
    )

    warnings = rendering_media_warnings(metadata)

    assert any("HDR or wide-gamut" in warning for warning in warnings)
    assert any("variable frame rate" in warning for warning in warnings)
