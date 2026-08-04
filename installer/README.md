# Windows offline installer

`build_offline_installer.ps1` creates a self-contained Windows x64 package with Python,
FFmpeg, the standalone Ollama runtime, Whisper Medium, Qwen3:4b, and both Argos translation
models. A newly installed copy therefore does not download a model on first use.

Build prerequisites:

- Windows x64 with at least 18 GB free for caches, staging, and output
- both Argos models and `qwen3:4b` already present in their default user model directories
- Inno Setup 6 (`winget install JRSoftware.InnoSetup`)
- `curl`, `ffmpeg`, and `ffprobe` available locally

Build from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\build_offline_installer.ps1
```

The script pins Python 3.12.10, the Whisper model revision, and Ollama v0.32.5; validates the
Python and official Ollama checksums; hashes every bundled model in
`offline-assets.json`, loads Whisper with network-free resolution, and then emits a split setup
set under `dist`. Keep the generated `.exe` and every adjacent `.bin` file together when copying
or installing it.

Validate an installed copy, including one real Qwen inference on an isolated local port:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\test_offline_install.ps1 `
  -InstallRoot "C:\path\to\installed-copy"
```

Large generated models, staging files, and installer binaries are intentionally ignored by Git.
Only the reproducible builder, license inventory, and code are committed.
