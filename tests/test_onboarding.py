from __future__ import annotations

from youtube_localizer import __version__
from youtube_localizer.onboarding import (
    onboarding_completed,
    onboarding_state_path,
    release_asset_url,
    release_page_url,
    setup_status_message,
    whisper_model_asset_names,
)


def test_release_links_use_the_current_version() -> None:
    assert release_page_url().endswith(f"/releases/tag/v{__version__}")
    assert release_asset_url("setup.exe").endswith(f"/v{__version__}/setup.exe")


def test_whisper_model_assets_are_paired_and_versioned() -> None:
    setup, data = whisper_model_asset_names("small")

    assert setup.endswith("Whisper-Small-Model-Setup.exe")
    assert data == setup.removesuffix(".exe") + "-1.bin"


def test_onboarding_completion_is_saved_per_version(tmp_path) -> None:
    from youtube_localizer.onboarding import mark_onboarding_completed

    state_path = tmp_path / "onboarding.json"
    assert not onboarding_completed(state_path=state_path)

    mark_onboarding_completed(state_path=state_path)

    assert onboarding_completed(state_path=state_path)


def test_onboarding_state_prefers_local_app_data() -> None:
    path = onboarding_state_path({"LOCALAPPDATA": r"C:\\Users\\demo\\AppData\\Local"})

    assert str(path).endswith(r"YouTube Chinese Localizer\onboarding.json")


def test_setup_status_explains_missing_or_ready_models() -> None:
    assert "还需安装 Whisper" in setup_status_message("standard", ())
    assert "Small / Medium 已就绪" in setup_status_message("complete", ("small", "medium"))
    assert "源码运行环境" in setup_status_message(None, ())
