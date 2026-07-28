from __future__ import annotations

import shutil
from pathlib import Path

from ..errors import InputValidationError
from ..models import SourceMetadata
from ..utils.hashing import hash_text
from .metadata import metadata_from_probe, probe_media

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".webm",
    ".avi",
    ".m4v",
    ".mts",
    ".m2ts",
}


def inspect_local(path: Path) -> SourceMetadata:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise InputValidationError(f"Local video file does not exist: {resolved}")
    if resolved.suffix.lower() not in VIDEO_EXTENSIONS:
        raise InputValidationError(
            f"Unsupported local file extension {resolved.suffix!r}. "
            f"Expected one of: {', '.join(sorted(VIDEO_EXTENSIONS))}"
        )
    probe = probe_media(resolved)
    video_id = hash_text(str(resolved).casefold())[:10]
    return metadata_from_probe(resolved, probe, video_id=video_id)


def import_local(source: Path, destination_dir: Path) -> Path:
    source = source.resolve()
    destination = destination_dir / f"source_video{source.suffix.lower()}"
    destination_dir.mkdir(parents=True, exist_ok=True)
    if source == destination.resolve():
        return destination
    temp = destination.with_name(f"{destination.stem}.partial{destination.suffix}")
    try:
        shutil.copy2(source, temp)
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)
    return destination
