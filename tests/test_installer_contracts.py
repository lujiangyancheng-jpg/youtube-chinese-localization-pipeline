from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = PROJECT_ROOT / "installer"


def test_native_launcher_source_has_a_noninteractive_verification_mode() -> None:
    source = (INSTALLER / "LocalizeStudioLauncher.cs").read_text(encoding="utf-8")

    assert '"--verify"' in source
    assert "pythonw.exe" in source
    assert "YOUTUBE_LOCALIZER_HOME" in source
    assert "Environment.SpecialFolder.MyDocuments" in source


def test_base_installer_uses_the_native_launcher_not_a_cmd_wrapper() -> None:
    script = (INSTALLER / "offline-installer.iss").read_text(encoding="utf-8")
    builder = (INSTALLER / "build_offline_installer.ps1").read_text(encoding="utf-8")
    verifier = (INSTALLER / "test_offline_install.ps1").read_text(encoding="utf-8")

    assert 'Filename: "{app}\\Localize Studio.exe"' in script
    assert "Localize Studio Launcher.exe" in script
    assert "InstallLocation" in (INSTALLER / "LocalizeStudioLauncher.cs").read_text(encoding="utf-8")
    assert "Launch Localizer.cmd" not in script
    assert "build_launcher.ps1" in builder
    assert 'ArgumentList "--verify"' in verifier


def test_standard_installer_downloads_only_selected_hash_verified_model_packs() -> None:
    script = (INSTALLER / "offline-installer.iss").read_text(encoding="utf-8")
    builder = (INSTALLER / "build_offline_installer.ps1").read_text(encoding="utf-8")

    assert "CreateInputOptionPage" in script
    assert "CreateDownloadPage" in script
    assert "DownloadPage.Add" in script
    assert "ReleaseAssetBaseUrl" in script
    assert "WhisperSmallSetupSha256" in script
    assert "LocalAIBin3Sha256" in script
    assert "CurStep = ssPostInstall" in script
    assert "InstallModelPack" in script
    assert "Get-RequiredReleaseAssetHash" in builder
    assert "Local-AI-Model-Setup" in builder


def test_model_pack_refuses_missing_or_mismatched_base_installations() -> None:
    for filename in ("whisper-model-pack.iss", "local-ai-model-pack.iss"):
        script = (INSTALLER / filename).read_text(encoding="utf-8")

        assert "function BaseInstallationError" in script
        assert "offline-assets.json" in script
        assert '"version"' in script
        assert '"{#AppVersion}"' in script
        assert "function PrepareToInstall" in script


def test_local_ai_pack_only_copies_qwen_files_referenced_by_its_manifest() -> None:
    builder = (INSTALLER / "build_local_ai_model_pack.ps1").read_text(encoding="utf-8")
    base_builder = (INSTALLER / "build_offline_installer.ps1").read_text(encoding="utf-8")

    assert "Copy-RequiredOllamaModel" in builder
    assert '"digest"\\s*:' in builder
    assert "Copy-RequiredOllamaQwenModel" in base_builder
    assert "Copy-RequiredDirectory $OllamaModelRoot" not in base_builder


def test_release_signing_is_optional_but_requires_a_real_certificate() -> None:
    signer = (INSTALLER / "sign_release.ps1").read_text(encoding="utf-8")
    base_builder = (INSTALLER / "build_offline_installer.ps1").read_text(encoding="utf-8")
    model_builder = (INSTALLER / "build_whisper_model_pack.ps1").read_text(encoding="utf-8")
    local_ai_builder = (INSTALLER / "build_local_ai_model_pack.ps1").read_text(encoding="utf-8")

    assert "Cert:\\CurrentUser\\My" in signer
    assert "Get-AuthenticodeSignature" in signer
    assert "CertificateThumbprint" in base_builder
    assert "CertificateThumbprint" in model_builder
    assert "CertificateThumbprint" in local_ai_builder
