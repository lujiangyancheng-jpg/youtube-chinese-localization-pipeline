from __future__ import annotations

from youtube_localizer.utils.files import sanitize_filename


def test_sanitize_filename_removes_windows_illegal_characters() -> None:
    assert sanitize_filename("  My: Video? <test>  ") == "My_ Video_ _test_"


def test_sanitize_filename_handles_reserved_and_empty_names() -> None:
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("...") == "untitled"


def test_sanitize_filename_limits_length() -> None:
    assert len(sanitize_filename("a" * 200, max_length=32)) == 32
