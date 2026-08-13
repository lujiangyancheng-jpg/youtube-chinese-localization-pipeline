from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import monotonic

from filelock import FileLock

LOGGER = logging.getLogger(__name__)


def heavy_workload_lock_path() -> Path:
    """Store the cross-process lock outside project and OneDrive folders."""
    if os.name == "nt" and (local_app_data := os.getenv("LOCALAPPDATA")):
        root = Path(local_app_data) / "YouTube Chinese Localizer"
    else:
        root = Path(tempfile.gettempdir()) / "youtube-chinese-localizer"
    return root / "heavy-workload.lock"


@contextmanager
def heavy_workload_slot(label: str) -> Iterator[None]:
    """Serialize GPU/encoder-heavy work across localizer processes.

    Batch workers may download in parallel, but Whisper, local models, and rendering share this
    lock so they do not compete for GPU VRAM or saturate the CPU encoder at the same time.
    """
    path = heavy_workload_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    started = monotonic()
    lock = FileLock(str(path))
    LOGGER.info("Waiting for the shared performance slot for %s when another heavy task is active.", label)
    with lock:
        waited = monotonic() - started
        if waited >= 0.2:
            LOGGER.info("Acquired the shared performance slot for %s after %.1f seconds.", label, waited)
        else:
            LOGGER.info("Using the shared performance slot for %s.", label)
        yield
