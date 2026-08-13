"""Local first-run state and public release links for the desktop application."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from . import __version__
from .utils.files import atomic_write_json, load_json

REPOSITORY_URL = "https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline"


def release_page_url(version: str = __version__) -> str:
    return f"{REPOSITORY_URL}/releases/tag/v{version}"


def release_asset_url(asset_name: str, version: str = __version__) -> str:
    return f"{REPOSITORY_URL}/releases/download/v{version}/{asset_name}"


def whisper_model_asset_names(model: str, version: str = __version__) -> tuple[str, str]:
    normalized = model.strip().title()
    if normalized not in {"Small", "Medium"}:
        raise ValueError("Whisper model must be Small or Medium.")
    stem = f"YouTube-Chinese-Localizer-{version}-Whisper-{normalized}-Model-Setup"
    return f"{stem}.exe", f"{stem}-1.bin"


def onboarding_state_directory(environment: Mapping[str, str] | None = None) -> Path:
    environment = os.environ if environment is None else environment
    local_app_data = environment.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "YouTube Chinese Localizer"
    return Path.home() / ".youtube-chinese-localizer"


def onboarding_state_path(environment: Mapping[str, str] | None = None) -> Path:
    return onboarding_state_directory(environment) / "onboarding.json"


def onboarding_completed(
    *, environment: Mapping[str, str] | None = None, state_path: Path | None = None
) -> bool:
    path = state_path or onboarding_state_path(environment)
    try:
        data = load_json(path)
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("completed_version") == __version__


def mark_onboarding_completed(
    *, environment: Mapping[str, str] | None = None, state_path: Path | None = None
) -> Path:
    path = state_path or onboarding_state_path(environment)
    atomic_write_json(path, {"completed_version": __version__})
    return path


def setup_status_message(package: str | None, whisper_models: tuple[str, ...]) -> str:
    """Produce a user-facing installation summary without exposing implementation details."""
    if package is None:
        return "当前为源码运行环境；可直接继续设置和处理。"
    package_name = "Complete" if package == "complete" else "Standard"
    if whisper_models:
        return f"{package_name} 基础包已安装；Whisper {' / '.join(item.title() for item in whisper_models)} 已就绪。"
    return f"{package_name} 基础包已安装；生成字幕前还需安装 Whisper Small 或 Medium 模型包。"
