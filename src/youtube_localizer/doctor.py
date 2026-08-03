from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .transcription.whisper_engine import cuda_available
from .translation.offline import validate_offline_model
from .utils.subprocesses import resolve_executable


@dataclass
class DoctorCheck:
    name: str
    status: str
    detail: str
    required: bool = True


def _module_check(module: str, label: str, *, required: bool = True) -> DoctorCheck:
    found = importlib.util.find_spec(module) is not None
    return DoctorCheck(
        label,
        "ok" if found else ("missing" if required else "optional"),
        "installed" if found else f"install Python package: {module.replace('_', '-')}",
        required,
    )


def _font_check() -> DoctorCheck:
    candidates = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC"]
    font_files: list[Path] = []
    if os.name == "nt":
        fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for pattern in ("msyh*.ttc", "simhei.ttf", "*NotoSansCJK*"):
            font_files.extend(fonts.glob(pattern))
    else:
        for root in (Path("/usr/share/fonts"), Path("/Library/Fonts")):
            if root.exists():
                font_files.extend(root.rglob("*Noto*Sans*CJK*"))
    return DoctorCheck(
        "Chinese subtitle font",
        "ok" if font_files else "warning",
        str(font_files[0]) if font_files else f"none of {', '.join(candidates)} detected",
        False,
    )


def run_doctor(output_directory: Path) -> list[DoctorCheck]:
    version_ok = sys.version_info >= (3, 11)
    checks = [
        DoctorCheck(
            "Python",
            "ok" if version_ok else "missing",
            sys.version.split()[0] + (" (3.11+)" if version_ok else "; Python 3.11+ required"),
        ),
    ]
    for executable in ("ffmpeg", "ffprobe"):
        path = resolve_executable(executable)
        checks.append(
            DoctorCheck(
                executable,
                "ok" if path else "missing",
                path or f"{executable} is not on PATH",
            )
        )
    ytdlp_path = resolve_executable("yt-dlp")
    ytdlp_module = importlib.util.find_spec("yt_dlp") is not None
    checks.append(
        DoctorCheck(
            "yt-dlp",
            "ok" if ytdlp_path or ytdlp_module else "missing",
            ytdlp_path or ("Python module installed" if ytdlp_module else "install package yt-dlp"),
        )
    )
    offline_runtime = all(
        importlib.util.find_spec(module) is not None
        for module in ("ctranslate2", "sentencepiece")
    )
    checks.append(
        DoctorCheck(
            "Offline translation runtime",
            "ok" if offline_runtime else "optional",
            (
                "CTranslate2 and SentencePiece installed"
                if offline_runtime
                else 'install with: python -m pip install -e ".[offline-translation]"'
            ),
            False,
        )
    )
    default_offline_model = Path(
        "~/.youtube-chinese-localizer/models/translate-en_zh-1_9"
    ).expanduser()
    model_ready = validate_offline_model(default_offline_model) is not None
    checks.append(
        DoctorCheck(
            "Offline English→Chinese model",
            "ok" if model_ready else "optional",
            (
                str(default_offline_model)
                if model_ready
                else "downloads automatically on first offline translation"
            ),
            False,
        )
    )
    zh_en_model = Path(
        "~/.youtube-chinese-localizer/models/translate-zh_en-1_9"
    ).expanduser()
    zh_en_model_ready = (
        validate_offline_model(zh_en_model, source_code="zh", target_code="en")
        is not None
    )
    checks.append(
        DoctorCheck(
            "Offline Chinese-to-English model",
            "ok" if zh_en_model_ready else "optional",
            (
                str(zh_en_model)
                if zh_en_model_ready
                else "downloads automatically on first Chinese-to-English translation"
            ),
            False,
        )
    )
    checks.append(_module_check("faster_whisper", "faster-whisper", required=False))
    checks.append(
        DoctorCheck(
            "CUDA for faster-whisper",
            "ok" if cuda_available() else "optional",
            "available" if cuda_available() else "not detected; CPU mode remains supported",
            False,
        )
    )
    api_key = bool(os.getenv("OPENAI_COMPATIBLE_API_KEY"))
    checks.append(
        DoctorCheck(
            "Translation configuration",
            "ok" if api_key or model_ready or zh_en_model_ready else "optional",
            (
                "API key detected"
                if api_key
                else (
                    "offline translation ready; API is optional"
                    if model_ready or zh_en_model_ready
                    else "manual export/import available; ChatGPT Plus does not include API credits"
                )
            ),
            False,
        )
    )
    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output_directory, delete=True):
            pass
        writable = True
        detail = str(output_directory.resolve())
    except OSError as exc:
        writable = False
        detail = str(exc)
    checks.append(
        DoctorCheck(
            "Output directory",
            "ok" if writable else "missing",
            detail,
        )
    )
    checks.append(_font_check())
    return checks
