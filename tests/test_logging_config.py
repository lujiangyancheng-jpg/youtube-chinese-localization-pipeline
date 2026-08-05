from __future__ import annotations

import logging

from youtube_localizer.logging_config import configure_logging


def test_reconfiguring_logging_closes_removed_file_handler(tmp_path) -> None:
    root = logging.getLogger()
    try:
        configure_logging(tmp_path / "first.log")
        first = next(
            handler for handler in root.handlers if isinstance(handler, logging.FileHandler)
        )

        configure_logging(tmp_path / "second.log")

        assert first.stream is None or first.stream.closed
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
            handler.close()
