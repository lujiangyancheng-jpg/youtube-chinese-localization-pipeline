from __future__ import annotations

import re
from pathlib import Path

from youtube_localizer import __version__

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent_across_package_metadata() -> None:
    expected = __version__
    files = {
        PROJECT_ROOT / "pyproject.toml": rf'^version = "{re.escape(expected)}"$',
        PROJECT_ROOT / "installer" / "build_offline_installer.ps1": rf'\$Version = "{re.escape(expected)}"',
        PROJECT_ROOT / "installer" / "offline-installer.iss": rf'#define AppVersion "{re.escape(expected)}"',
        PROJECT_ROOT / "installer" / "build_whisper_model_pack.ps1": rf'\$Version = "{re.escape(expected)}"',
        PROJECT_ROOT / "installer" / "whisper-model-pack.iss": rf'#define AppVersion "{re.escape(expected)}"',
    }

    for path, pattern in files.items():
        assert re.search(pattern, path.read_text(encoding="utf-8"), flags=re.MULTILINE), path
