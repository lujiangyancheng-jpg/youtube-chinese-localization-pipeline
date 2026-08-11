# Windows offline installer

`build_offline_installer.ps1` creates self-contained Windows x64 base packages. Both tiers bundle
Python/Tk, FFmpeg (including the NVENC compatibility build), both Argos translation models, and
one curated Noto Sans CJK SC font for subtitle rendering. A newly installed copy does not require
a system font or separate system Python/Tk installation.

- **Standard** is the smaller, broadly compatible package. It supports fast offline sentence
  translation once a user-selected Whisper model pack is installed.
- **Complete** adds the standalone Ollama runtime and Qwen3:4b for local paragraph-aware
  translation. It is intended for higher-quality no-API localization on systems with ample
  storage and memory; it also requires a user-selected Whisper model pack for subtitle jobs.

Build and distribute Whisper recognition models separately so users install only the model their
hardware can run:

- **Whisper Small** is the recommended choice for most computers.
- **Whisper Medium** needs more RAM/VRAM and storage, but provides higher recognition quality.

Build prerequisites:

- Windows x64 with enough free space for caches, staging, and output (22 GB minimum for Standard;
  substantially more for Complete)
- both Argos models present in their default user model directories; Complete also requires
  `qwen3:4b` in its default Ollama model directory
- Inno Setup 6 (`winget install JRSoftware.InnoSetup`)
- `curl`, `ffmpeg`, and `ffprobe` available locally

Build from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\build_offline_installer.ps1
```

Build the smaller package explicitly:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\build_offline_installer.ps1 -PackageTier Standard
```

Build a selected Whisper model pack after the base package:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\build_whisper_model_pack.ps1 -Model Small
powershell -ExecutionPolicy Bypass -File .\installer\build_whisper_model_pack.ps1 -Model Medium
```

The base builder pins Python 3.12.10, every Python runtime dependency, Ollama v0.32.5 for
Complete, and the Noto Sans CJK SC font source revision. The model-pack builder pins each Whisper revision
and validates its `model.bin` hash before it emits the selected model installer. Keep every
generated `.exe` and its adjacent `.bin` files together when copying or installing it.

Each build writes `SHA256SUMS-<version>-<tier>.txt`; `SHA256SUMS.txt` is a combined list for
all package tiers present in `dist`.

Validate an installed base copy. Complete additionally runs one real Qwen inference on an
isolated local port:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\test_offline_install.ps1 `
  -InstallRoot "C:\path\to\installed-copy"
```

The installer also adds **Verify YouTube Localizer Installation** to the Start menu. It validates
the installed asset sizes and SHA-256 hashes before loading the desktop application and local
base assets. The shortcut skips the longer Qwen inference; run the command above without
`-SkipInference` for the Complete release check. Install a Whisper model pack afterward; its
installer validates the model checksum before it is packaged. Upgrading from Complete to Standard
removes the Complete-only local AI files during installation.

Large generated models, staging files, and installer binaries are intentionally ignored by Git.
Only the reproducible builder, license inventory, and code are committed.
