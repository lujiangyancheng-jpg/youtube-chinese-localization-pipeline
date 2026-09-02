# Third-party notices

Video Localizer's own source code is licensed under the MIT License. Distributed installers also contain independent third-party components under their respective licenses. Installing or using the application does not relicense those components.

The installed `licenses` directory contains the detailed inventory and available license/readme files. Notable components include Python and Python packages, FFmpeg, Noto Sans CJK SC, Argos translation models, optional faster-whisper models, optional Ollama/Qwen local AI, and optional `waifu2x-ncnn-vulkan` super-resolution runtime and models.

The Standard package's pinned Gyan FFmpeg build is GPLv3. Its installed `FFmpeg-build-README.txt` identifies the exact corresponding FFmpeg source commit and build configuration; `FFmpeg-GPLv3.txt` contains the license. Reproducible binary versions and SHA-256 values are also pinned in `installer/build_offline_installer.ps1`.

The optional super-resolution pack redistributes `waifu2x-ncnn-vulkan` 20250915 and its included model files under the upstream MIT license. Its installer preserves the upstream `LICENSE` and `README.md` beside the runtime notices.
