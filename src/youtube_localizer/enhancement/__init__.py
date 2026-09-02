"""Optional local video-restoration features."""

from .super_resolution import enhance_video, super_resolution_target_height

__all__ = ["enhance_video", "super_resolution_target_height"]
