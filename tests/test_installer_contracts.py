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


def test_model_pack_refuses_missing_or_mismatched_base_installations() -> None:
    script = (INSTALLER / "whisper-model-pack.iss").read_text(encoding="utf-8")

    assert "function BaseInstallationError" in script
    assert "offline-assets.json" in script
    assert '"version"' in script
    assert '"{#AppVersion}"' in script
    assert "function PrepareToInstall" in script


def test_release_signing_is_optional_but_requires_a_real_certificate() -> None:
    signer = (INSTALLER / "sign_release.ps1").read_text(encoding="utf-8")
    base_builder = (INSTALLER / "build_offline_installer.ps1").read_text(encoding="utf-8")
    model_builder = (INSTALLER / "build_whisper_model_pack.ps1").read_text(encoding="utf-8")

    assert "Cert:\\CurrentUser\\My" in signer
    assert "Get-AuthenticodeSignature" in signer
    assert "CertificateThumbprint" in base_builder
    assert "CertificateThumbprint" in model_builder
