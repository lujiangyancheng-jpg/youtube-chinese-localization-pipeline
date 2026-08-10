# Windows offline installer

`build_offline_installer.ps1` creates a self-contained Windows x64 package with Python,
FFmpeg, the standalone Ollama runtime, Whisper Medium, Qwen3:4b, and both Argos translation
models. It also bundles Noto Sans CJK SC, Noto Serif CJK SC, and LXGW WenKai for subtitle rendering.
A newly installed copy therefore does not download a model, require a system font, or depend on
a separate system Python/Tk installation on first use.

Build prerequisites:

- Windows x64 with at least 18 GB free for caches, staging, and output
- both Argos models and `qwen3:4b` already present in their default user model directories
- Inno Setup 6 (`winget install JRSoftware.InnoSetup`)
- `curl`, `ffmpeg`, and `ffprobe` available locally

Build from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\build_offline_installer.ps1
```

The script pins Python 3.12.10, every Python runtime dependency, the Whisper model revision,
Ollama v0.32.5, and the three font source revisions. It verifies downloaded binaries and bundled
model checksums, records an `offline-assets.json` manifest, loads Whisper with network-free
resolution, and then emits a split setup set under `dist`. Keep the generated `.exe` and every
adjacent `.bin` file together when copying or installing it.

Validate an installed copy, including one real Qwen inference on an isolated local port:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\test_offline_install.ps1 `
  -InstallRoot "C:\path\to\installed-copy"
```

The installer also adds **Verify YouTube Localizer Installation** to the Start menu. It validates
the installed asset sizes and SHA-256 hashes before loading the desktop application and local
models. The shortcut skips the longer Qwen inference; run the command above without
`-SkipInference` for the complete release check.

Large generated models, staging files, and installer binaries are intentionally ignored by Git.
Only the reproducible builder, license inventory, and code are committed.
