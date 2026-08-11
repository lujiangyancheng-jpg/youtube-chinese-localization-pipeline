# Windows offline installer

`build_offline_installer.ps1` creates self-contained Windows x64 packages. Both tiers bundle
Python/Tk, FFmpeg (including the NVENC compatibility build), Whisper Small, both Argos
translation models, and Noto Sans CJK SC, Noto Serif CJK SC, and LXGW WenKai for subtitle
rendering. A newly installed copy therefore does not download a model, require a system font,
or depend on a separate system Python/Tk installation on first use.

- **Standard** is the smaller, broadly compatible package. It uses Whisper Small and fast
  offline sentence translation; the application automatically selects those bundled models.
- **Complete** adds Whisper Medium plus the standalone Ollama runtime and Qwen3:4b for local
  paragraph-aware translation. It is intended for higher-quality no-API localization on systems
  with ample storage and memory.

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

The script pins Python 3.12.10, every Python runtime dependency, the bundled Whisper model
revisions, Ollama v0.32.5 for Complete, and the three font source revisions. It verifies
downloaded binaries and bundled model checksums, records an `offline-assets.json` manifest,
loads bundled Whisper with network-free resolution, and then emits a split setup set under
`dist`. Keep the generated `.exe` and every adjacent `.bin` file together when copying or
installing it.

Each build writes `SHA256SUMS-<version>-<tier>.txt`; `SHA256SUMS.txt` is a combined list for
all package tiers present in `dist`.

Validate an installed copy. Complete additionally runs one real Qwen inference on an isolated
local port:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\test_offline_install.ps1 `
  -InstallRoot "C:\path\to\installed-copy"
```

The installer also adds **Verify YouTube Localizer Installation** to the Start menu. It validates
the installed asset sizes and SHA-256 hashes before loading the desktop application and local
models. The shortcut skips the longer Qwen inference; run the command above without
`-SkipInference` for the Complete release check. Upgrading from Complete to Standard removes
the Complete-only local AI files during installation.

Large generated models, staging files, and installer binaries are intentionally ignored by Git.
Only the reproducible builder, license inventory, and code are committed.
