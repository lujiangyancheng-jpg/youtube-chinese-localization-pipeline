"""Surface source-media limits before an unavoidable hard-subtitle re-encode."""

from __future__ import annotations

import re

from ..models import SourceMetadata

_HDR_TRANSFERS = {"smpte2084", "arib-std-b67", "hlg"}


def source_bit_depth(pixel_format: str) -> int | None:
    """Return a known high bit depth from an FFmpeg pixel-format name."""
    match = re.search(r"p0?(10|12|14|16)(?:le|be)?$", pixel_format.casefold())
    return int(match.group(1)) if match else None


def rendering_media_warnings(metadata: SourceMetadata) -> list[str]:
    """Describe quality and timing limits users should know before hard subtitles."""
    pixel_format = metadata.pixel_format.casefold()
    transfer = metadata.color_transfer.casefold()
    primaries = metadata.color_primaries.casefold()
    high_bit_depth = source_bit_depth(pixel_format)
    warnings: list[str] = []

    if transfer in _HDR_TRANSFERS or primaries == "bt2020":
        warnings.append(
            "Source is HDR or wide-gamut. Current hard-subtitle output is H.264 SDR/8-bit, "
            "so tone mapping or colors may change. Keep the original, or use the selectable "
            "subtitle MP4 when available to preserve the source video."
        )
    elif high_bit_depth and high_bit_depth > 8:
        warnings.append(
            f"Source uses {high_bit_depth}-bit video ({metadata.pixel_format}). Hard-subtitle "
            "rendering may convert it to 8-bit; review gradients in the final MP4."
        )

    if metadata.variable_frame_rate:
        warnings.append(
            "Source has a variable frame rate. The rendered file is validated automatically, "
            "but review subtitle sync around cuts before publishing."
        )
    return warnings
