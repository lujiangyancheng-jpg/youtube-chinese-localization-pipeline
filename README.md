# Localize Studio — 视频本地化工具

<div align="center">

把你有权处理的视频，转换为带自然字幕的本地化成品。支持 YouTube、授权的媒体直链和本地视频；下载、识别、翻译、字幕压制与断点续跑都在本机完成。

[![Release](https://img.shields.io/github/v/release/lujiangyancheng-jpg/youtube-chinese-localization-pipeline?display_name=tag&label=%E6%9C%80%E6%96%B0%E7%89%88%E6%9C%AC)](https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/lujiangyancheng-jpg/youtube-chinese-localization-pipeline/total?label=%E4%B8%8B%E8%BD%BD%E9%87%8F)](https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline/releases)
[![License](https://img.shields.io/github/license/lujiangyancheng-jpg/youtube-chinese-localization-pipeline)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4?logo=windows)](https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline/releases/latest)

[立即下载 v0.6.8 Standard 开发版](https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline/releases/download/v0.6.8/YouTube-Chinese-Localizer-0.6.8-Standard-Offline-Setup.exe)
· [查看全部发布包](https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline/releases/latest)
· [中文完整说明](docs/USER_GUIDE.zh-CN.md)

</div>

> 仅处理你拥有、已获授权、属于公共领域或许可允许本次用途的视频。软件不会绕过 DRM、登录、付费、地区或平台访问限制。

## 🚀 三步开始使用

1. 下载并放在同一文件夹：
   [Setup.exe](https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline/releases/download/v0.6.8/YouTube-Chinese-Localizer-0.6.8-Standard-Offline-Setup.exe)
   和
   [Setup-1.bin](https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline/releases/download/v0.6.8/YouTube-Chinese-Localizer-0.6.8-Standard-Offline-Setup-1.bin)。
2. 双击 `Setup.exe` 安装；需要生成字幕时，再安装一个 Whisper 模型包（Small 适合多数电脑，Medium 识别质量更高）。
3. 打开 Localize Studio，粘贴视频链接，选择翻译方向和字幕方式，然后点击“开始本地化”。

| 你想做什么 | 选择方式 | 需要什么 |
| --- | --- | --- |
| 最高画质无字幕下载 | “仅下载原视频（无字幕）” | 只需 Standard |
| 英文 ↔ 简体中文 | “本地快速翻译” | Standard + 一个 Whisper 包 |
| 更自然的中英字幕 | “本地 AI 段落翻译” | Complete + 一个 Whisper 包 |
| 日 / 韩 / 西 / 法 / 德 / 葡 / 俄 / 阿字幕 | “本地 AI”或“API 自动翻译” | Complete + Whisper，或 API |

**Standard v0.6.8 开发版：约 463 MiB 下载体积。** 它包含主程序、Python、FFmpeg、字幕字体、GPU/CPU 编码回退和两套中英快速离线翻译模型。安装完成后不必联网；字幕任务需要单独安装一个 Whisper 模型包。首次启动会用三步说明你下一步需要什么。

## ✨ 你能得到什么

| 输入 | 处理 | 输出 |
| --- | --- | --- |
| YouTube 公开视频、授权直链或本地视频 | 本地 Whisper 识别、段落翻译、字幕质量检查 | SRT、ASS、硬字幕 MP4、可选软字幕 MP4、项目报告 |
| 英文或简体中文语音 | 中英双向、本地 AI 或 API 多语种翻译 | 中文、英文、日语、韩语、西班牙语、法语、德语、葡萄牙语、俄语、阿拉伯语字幕 |
| 高画质视频 | 自动选择已验证的 NVIDIA / Intel / AMD 编码器；不可用则安全回退 CPU | 保持原始分辨率和帧率，或按你的设置限制输出 |

## 👥 适合谁

- 想离线观看、学习英文视频的中文用户；
- 有授权素材、需要制作多语言字幕的创作者、课程编辑和播客团队；
- 希望保留项目文件、可中断续跑、可复核字幕和术语的专业用户。

不适合批量搬运、无人值守转载、规避平台限制，或处理未获授权的内容。

## 📌 版本与支持

- 新增、优化和修复：[CHANGELOG.md](CHANGELOG.md)
- 完整中文使用手册：[docs/USER_GUIDE.zh-CN.md](docs/USER_GUIDE.zh-CN.md)
- 安装、模型和故障排查：[docs/INSTALLATION.zh-CN.md](docs/INSTALLATION.zh-CN.md)
- 报告问题或提出功能建议：[Issues](https://github.com/lujiangyancheng-jpg/youtube-chinese-localization-pipeline/issues)

---

## 面向开发者的详细说明

This production-oriented local Python application localizes authorized English- or Chinese-language
videos in either direction. Each reusable project contains normalized subtitles, optional bilingual
subtitles, and a validated hard-subtitled MP4. The pipeline is resumable, keeps intermediate files,
and never uploads content. YouTube caption tracks are never downloaded or consumed.

## Legal-use notice

Use this tool only for:

- videos you own;
- public-domain material;
- Creative Commons material whose license permits your intended use; or
- material for which you have explicit translation and redistribution permission.

It does not bypass DRM, paywalls, private-video controls, age gates, region/authentication
requirements, or platform access controls. You are responsible for verifying the license,
attribution requirements, and publishing-platform rules.

For non-YouTube sources, paste only a public, direct media URL you are authorized to download
(`.mp4`, `.webm`, `.mov`, `.mkv`, `.m3u8`, or `.mpd`), or an extensionless URL whose server
explicitly identifies it as video/HLS/DASH. Playback webpages, browser cookies, login credentials,
and DRM-protected streams are intentionally unsupported.

## Phase 1 capabilities

- Public YouTube metadata inspection with `yt-dlp` before download
- Highest-quality video plus audio direct-download mode with no subtitle processing
- Consistent local English or Chinese transcription without YouTube caption requests
- Local video validation and safe copying
- VTT/SRT/ASS parsing and normalized UTF-8 SRT output
- Rolling-caption overlap cleanup and conservative English cleanup
- `faster-whisper` English or Chinese transcription with VAD and word timestamps
- CUDA runtime preflight and bundled-runtime discovery for reliable GPU Whisper acceleration
- Responsiveness-preserving CPU Whisper fallback (six threads by default)
- Manual Markdown/JSONL translation chunks with strict cue/timestamp validation
- Local offline English↔Simplified Chinese translation with directional model selection and caching
- OpenAI-compatible subtitle translation with retries and deterministic response caching
- English or Simplified Chinese target SRT and styled ASS output
- Target-only, English-above-Chinese, and Chinese-above-English subtitle modes
- H.264/AAC hard-subtitled MP4 rendering with verified NVIDIA, Intel Quick Sync, AMD AMF, or CPU fallback
- Selectable soft-subtitle MP4 output without recompressing the source video or audio
- Preview rendering and output stream/duration/decode validation
- Final-target subtitle quality report for fast-reading, duplicate, flash, and line-length cues
- Atomic state/report writes and hash-based resume decisions
- Structured JSONL file logs plus readable console output
- Conservative publishing metadata drafts marked for human review
- Offline unit tests and an FFmpeg synthetic-video integration test

Advanced retiming, thumbnail overlays, and polished platform-specific metadata generation remain
future enhancements. Timestamps are deliberately not changed in Phase 1.

## Who this is for

- Learners who want a private, offline way to understand English YouTube videos with Chinese
  subtitles.
- Creators and editors working with videos they own or are authorized to localize, who need
  Chinese, English, bilingual, hard-subtitle, and selectable-subtitle deliverables.
- Course, interview, and podcast editors who need an auditable project folder, a terminology
  glossary, resumable processing, and focused subtitle-review flags.

It is not intended for mass unattended redistribution, bypassing platform restrictions, or use
with material that you are not authorized to translate or publish.

## Windows quick start

For a normal Windows installation, use the split offline setup set from `dist`: keep the setup
`.exe` and all adjacent `.bin` files together, then run the `.exe`. Choose the package that fits
the computer and workflow:

- **Standard** includes its own Python, FFmpeg, both fast offline translation models, and
  subtitle fonts. It is the smaller choice for everyday work.
- **Complete** additionally includes the Ollama runtime and Qwen3:4b for local paragraph-aware
  translation. It is the recommended no-API quality package for computers with sufficient disk
  space and memory.

Install one external Whisper model pack after installing either base package: **Small** is the
recommended balanced choice for most computers; **Medium** needs more RAM/VRAM but improves
recognition quality. The app detects installed model packs before a subtitle job and never
silently downloads a model.

Both packages stay offline on first use. Before every job, the app checks available storage,
installed package tier, GPU memory, and model availability, then selects a safe installed fallback
when necessary. See [installer/README.md](installer/README.md) for reproducible build
instructions. Chinese installation notes: [docs/INSTALLATION.zh-CN.md](docs/INSTALLATION.zh-CN.md).

The following steps are for running directly from a source checkout:

The recommended interpreter is Python 3.11, 3.12, or 3.13. Python 3.14 may run the core
application, but `faster-whisper`/CTranslate2 wheels may not yet be available for it.

1. Install [Python](https://www.python.org/downloads/windows/) and enable **Add Python to PATH**.
2. Install FFmpeg with one of these methods:

   ```powershell
   winget install Gyan.FFmpeg
   ```

   Or download an FFmpeg build that includes `ffprobe` and the `subtitles`/libass filter,
   extract it, and add its `bin` directory to `PATH`. Open a new terminal afterward.
   The application also detects `tools\ffmpeg\bin` inside the project, or explicit
   `FFMPEG_PATH` and `FFPROBE_PATH` environment variables.

3. In this project directory, create and activate a virtual environment:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -e ".[transcription,offline-translation]"
   ```

4. Check the environment:

   ```powershell
   python main.py doctor
   ```

5. Process a video you are authorized to localize:

   ```powershell
   python main.py process "D:\Videos\owned-video.mp4"
   python main.py process "https://www.youtube.com/watch?v=VIDEO_ID"
   ```

   To inspect the effective offline model, hardware plan, and required temporary space before
   processing, run:

   ```powershell
   python main.py preflight "D:\Videos\owned-video.mp4"
   ```

The command-line default translation provider is `manual`. Add `--translation-provider
offline` for a no-API end-to-end run. The desktop interface defaults to offline translation.

## Smart acceleration and output controls

The desktop interface now uses one automatic high-quality path instead of asking users to choose
technical performance presets. Whisper uses NVIDIA CUDA only after a runtime check, then safely
uses CPU `int8` when CUDA is unavailable. Final rendering verifies NVIDIA NVENC (including the
bundled older-driver compatibility encoder), Intel Quick Sync, and AMD AMF before using one; it
uses CPU/libx264 only when none pass the real probe. The default is Medium Whisper plus the
highest final encode quality.

The desktop app keeps its helper command windows hidden and turns real pipeline messages into
progress: download percentage, local-AI paragraph count, and FFmpeg rendering percentage. It also
downloads up to four DASH/HLS fragments concurrently and groups more complete spoken paragraphs
for local AI, reducing model-request overhead without sacrificing context. The compatibility
encoder is selected only after a real probe succeeds, so supported older drivers retain GPU
rendering without changing driver versions; CPU encoding remains the safe fallback.

Completed projects also include `logs/subtitle_quality.json`. When only a few cues need attention,
`subtitles/review_required.srt` contains exactly the flagged timestamps for focused proofreading.

Source downloads remain ranked by resolution, then frame rate, bitrate, and file size. For the
hard-subtitled MP4, the settings panel offers only three clear output choices:

- **Output quality:** Highest (default), High/smaller file, or Standard/smaller file.
- **Output FPS:** Keep the source rate (default), cap at 60 FPS, or cap at 30 FPS. The app never
  creates fake frames by converting a 30 FPS source to 60 FPS.
- **Output resolution:** Keep the source dimensions (default), or cap at 4K, 1440p, 1080p, or
  720p. A lower-resolution source is never upscaled.

The equivalent CLI command is:

```powershell
python main.py process "D:\Videos\authorized-video.mp4" `
  --translation-provider offline --processing-profile auto `
  --output-quality best --output-fps 60 --output-height 2160
```

## Windows paste-a-link desktop interface

After completing the Windows installation above, double-click `Start Localizer.cmd` in the
project folder. The streamlined downloader-style interface makes **Paste Link** the primary
action, keeps the empty state distraction-free, and reveals the current task only after a video
is added. Processing settings, API fields, and the run log stay collapsed until needed. You can then:

1. paste an authorized public YouTube URL, an authorized direct media URL, or select a local video;
2. choose an English/Chinese source and its target language;
3. choose target-only or bilingual subtitles;
4. confirm that you have the required rights or permission; and
5. click **开始本地化**.

The window streams progress from the existing resumable pipeline and provides a button for
opening the `output` folder. Closing or stopping a run keeps completed stages so the same
input can be resumed later. There is no YouTube-caption option: both directions always transcribe
the source audio with a locally installed Whisper model pack.

YouTube downloads default to the highest-resolution video stream and the best available audio
stream without restricting the source codec to MP4/M4A. Formats are ranked by resolution,
frame rate, bitrate, and file size; FFmpeg still produces the final hard-subtitled MP4. The
project dependency set includes Deno and `yt-dlp-ejs`; `python main.py doctor` must report
`yt-dlp JavaScript support: ok` so YouTube's complete format list can be discovered.

An authorized direct media address can be pasted in the same field. The URL must point to the
actual MP4/WebM/MOV/MKV file or HLS/DASH manifest (`.m3u8`/`.mpd`), not to a site playback page.
An extensionless CDN URL is also accepted when its response identifies it as video or a playlist.
The app does not scrape player pages, supply browser cookies, or bypass DRM. If a signed media URL
expires, paste its refreshed direct URL and keep **resume** enabled; the project is matched by its
stable media path rather than the temporary query string.

The desktop interface offers four translation modes:

- **Free/manual mode** downloads the video, obtains or transcribes source-language subtitles, and
  exports translation chunks. You translate and import those chunks before rendering.
- **Local fast mode** translates in the selected direction on this computer and continues
  through hard-subtitle rendering without an API. The offline installer includes both directional
  models. Rolling transcript fragments are grouped into complete paragraphs before translation;
  configured glossary terms are enforced.
- **Local AI paragraph mode** uses the bundled `qwen3:4b` and standalone Ollama runtime on
  a dedicated loopback port. It needs no API key and sends no subtitle text to a cloud service.
  This dedicated service prevents an existing system Ollama installation from hiding the bundled
  model. The model
  translates a complete spoken paragraph first; the application then segments the natural target
  paragraph at target-language punctuation and maps it across the source time range.
- **API automatic mode** continues through target-language translation and hard-subtitle
  rendering. It requires an OpenAI-compatible endpoint, model name, and API key. Values
  entered in the window are passed to the processing run. The API key is never saved;
  endpoint and model settings may be recorded in the local project's resolved configuration
  so an interrupted run can be resumed.

For Japanese, Korean, Spanish, French, German, Portuguese, Russian, and Arabic output, choose
**Local AI paragraph mode** (a capable local Ollama model is required) or **API automatic mode**.
The fast bundled models and the Chinese-English bilingual layouts intentionally remain limited to
English↔Simplified Chinese. Extra-language jobs create target-only subtitle files such as
`subtitles/es.srt`, `subtitles/es.ass`, and `rendered/es_hardsub.mp4`.

ChatGPT Plus cannot be used by the local program as an API and does not include API credits.
The interface can also be opened from PowerShell with:

```powershell
python main.py gui
```

The equivalent no-API command is:

```powershell
python main.py process "https://www.youtube.com/watch?v=VIDEO_ID" `
  --translation-provider offline

python main.py process "D:\Videos\authorized-Chinese-video.mp4" `
  --translation-direction zh-to-en --translation-provider offline

# Higher-quality local paragraph translation; no cloud API or API key.
python main.py process "https://www.youtube.com/watch?v=VIDEO_ID" `
  --translation-provider ollama

# Chinese speech to Spanish subtitles using a local Ollama model.
python main.py process "D:\Videos\authorized-Chinese-video.mp4" `
  --translation-direction zh-to-es --translation-provider ollama
```

The offline models are stored under
`~/.youtube-chinese-localizer/models/translate-en_zh-1_9` and
`~/.youtube-chinese-localizer/models/translate-zh_en-1_9`. They are derived from OPUS-MT and
distributed with CC-BY 4.0 model notices in their included `README.md`. Local model translation
is convenient and private, but names, jokes, and specialized terminology still need review.

## Manual ChatGPT translation workflow (no API billing)

**ChatGPT Plus does not include OpenAI API credits. OpenAI API usage is billed separately.**
If you do not want separate API billing, use this workflow:

1. Start processing:

   ```powershell
   python main.py process "D:\Videos\owned-video.mp4"
   ```

2. Open the printed project path, then locate
   `subtitles\translation_chunks\chunk_001.md`, `chunk_002.md`, and so on.
3. Upload one chunk to ChatGPT. The file already contains the strict translation rules.
4. Save ChatGPT's JSONL response as a UTF-8 text file. It must retain every `id`, `start`,
   `end`, and `en` field and fill every `zh` field.
5. Import each response:

   ```powershell
   python main.py translate-import "output\PROJECT_NAME" "D:\Translations\chunk_001.txt"
   python main.py translate-import "output\PROJECT_NAME" "D:\Translations\chunk_002.txt"
   ```

6. When the CLI reports all cues imported, render:

   ```powershell
   python main.py render "output\PROJECT_NAME"
   python main.py validate "output\PROJECT_NAME"
   ```

You can regenerate chunks at any time without calling an API:

```powershell
python main.py translate-export "output\PROJECT_NAME"
```

The importer rejects unknown/duplicate cue IDs, changed timestamps, changed English source
text, malformed JSON, and empty translations. Partial imports are saved and merged.

## OpenAI-compatible API workflow

Copy `.env.example` to `.env` for reference, but set secrets in the current environment or
your secret manager. The application never logs the API key.

```powershell
$env:OPENAI_COMPATIBLE_API_KEY = "your-key"
$env:OPENAI_COMPATIBLE_ENDPOINT = "https://api.openai.com/v1"
$env:OPENAI_COMPATIBLE_MODEL = "your-compatible-model"
python main.py process "D:\Videos\owned-video.mp4" --translation-provider openai-compatible
```

You may instead set `translation.endpoint` and `translation.model` in a private YAML config.
Successful batch responses are cached under the project `temp\translation_cache` directory,
so an unchanged paid request is not repeated. Endpoint behavior and billing depend on your
chosen provider.

## Commands

```text
python main.py process INPUT
python main.py INPUT
python main.py process INPUT --subtitle-mode bilingual_en_zh
python main.py process INPUT --translation-provider manual
python main.py process INPUT --translation-provider offline --prefer-youtube-chinese
python main.py process INPUT --resume
python main.py process INPUT --force-step transcribe
python main.py --batch inputs.txt
python main.py batch inputs.txt --parallel-jobs 2
python main.py inspect PROJECT_PATH
python main.py transcribe PROJECT_PATH
python main.py translate PROJECT_PATH
python main.py translate-export PROJECT_PATH
python main.py translate-import PROJECT_PATH TRANSLATED_FILE
python main.py render PROJECT_PATH
python main.py preview PROJECT_PATH --start 60 --duration 15
python main.py metadata PROJECT_PATH
python main.py validate PROJECT_PATH
python main.py clean PROJECT_PATH
python main.py doctor
```

`clean` removes only temporary/cache/partial files and preserves source and final assets.
It asks for confirmation unless `--yes` is provided.

`batch --parallel-jobs 2` overlaps downloads for up to two videos. Whisper transcription, local
translation, and hard-subtitle rendering automatically wait for one shared performance slot, so
they do not compete for GPU VRAM or the CPU encoder. Use `--parallel-jobs 1` for fully sequential
processing.

## Configuration

Copy `config.example.yaml` to a new filename and edit it; the example is never overwritten:

```powershell
Copy-Item config.example.yaml config.local.yaml
python main.py process "D:\Videos\owned-video.mp4" --config config.local.yaml
```

Important settings:

```yaml
# Keep source, cache, and rendered video files outside OneDrive whenever possible.
output_directory: ~/Videos/YouTube Chinese Localizer
subtitle_mode: chinese  # download_only, chinese, bilingual_en_zh, bilingual_zh_en

transcription:
  model: medium
  device: auto          # auto, cpu, cuda
  compute_type: auto
  cpu_threads: 0        # 0 adapts to CPU cores and RAM; set 1-32 to override
  beam_size: 5
  vad_filter: true
  word_timestamps: true

translation:
  direction: en-to-zh   # en-to-zh / zh-to-en; extra targets: ja, ko, es, fr, de, pt, ru, ar
  provider: ollama      # manual, offline, ollama, or openai-compatible
  batch_size: 40
  offline_device: auto  # auto uses reliable CPU; cuda must be selected explicitly
  ollama_endpoint: http://localhost:11434
  ollama_model: qwen3:4b
  ollama_context_tokens: 4096  # avoids an unnecessarily large VRAM reservation on 12 GB GPUs

download:
  format: bestvideo+bestaudio/best
  format_sort: [res, fps, br, size]
  concurrent_fragment_downloads: 4

subtitles:
  font: Noto Sans CJK SC
  font_size: 48
  max_chinese_chars_per_line: 20

render:
  codec: auto           # verifies NVIDIA, Intel, AMD, then falls back to libx264
  crf: 17
  preset: medium
  soft_subtitles: true  # also create a selectable-subtitle MP4 without re-encoding media
  output_height: null   # keep the source dimensions; 2160/1440/1080/720 cap the result
  output_fps: null      # keep source FPS; 60/30 only cap higher frame-rate sources
```

Each project stores `config.resolved.json` so later project commands use the same settings.

To download the best available video and audio without transcription, translation, or subtitle
rendering:

```powershell
python main.py process "https://www.youtube.com/watch?v=VIDEO_ID" --subtitle-mode download_only
```

The desktop interface uses this same local Videos-folder default and lets you choose another
location per task. It warns before starting when the selected folder is in OneDrive or has less
than 20 GiB free, because syncing high-bitrate source and rendered files can noticeably slow the
pipeline.

The merged original is saved in the project's `source` directory.

## Project folder

```text
output/
  sanitized_title_videoid/
    source/
      source_video.mp4       # extension may reflect the actual compatible container
      metadata.json
      metadata.raw.json
      thumbnail.jpg
    subtitles/
      source.en.vtt
      source.zh.vtt
      english.cleaned.srt
      english.ass
      chinese.srt
      chinese.ass
      bilingual.srt
      bilingual.ass
      transcription.raw.json
      translation_chunks/
    audio/
      transcription_audio.wav
    rendered/
      chinese_hardsub.mp4
      english_hardsub.mp4
      chinese_softsub.mp4
      english_softsub.mp4
      preview_START_DURATION.mp4
    publishing/
      title.txt
      description.txt
      tags.txt
      metadata_localized.json
    logs/
      pipeline.log
      report.json
      report.md
      subtitle_quality.json
    temp/
    config.resolved.json
    pipeline_state.json
```

The local original is never modified. A project copy is made using a temporary file followed
by an atomic rename. Download partials are retained so `--resume` can continue.

## Resume, overwrite, and force

- Default: refuse to overwrite an existing project.
- `--resume`: reuse a project with the same video ID/local-path ID and skip completed steps
  only when input hash, relevant configuration hash, and output files still match.
- `--overwrite`: remove and recreate only the exact matching project directory.
- `--force-step NAME`: repeat a selected stage. Supported names are `acquire`,
  `english_subtitles`, `chinese_subtitles`, `transcribe`, `translate`, and `render`. Unknown or
  misspelled names are rejected.

Every state entry records start/end times, status, hashes, outputs, errors, elapsed time, and
retry count. Failed runs are explicitly marked `failed`; manual runs are marked
`awaiting_manual_translation`.

## Subtitle styling

Hard subtitles use ASS styling with a dark outline and bottom alignment. The offline installer
bundles one carefully selected font, `Noto Sans CJK SC`, under the SIL Open Font License. The
desktop app keeps that consistent typeface and lets users select a small, standard (48), large,
or extra-large subtitle size. FFmpeg loads the bundled font directly from the application, so it
does not need to be installed system-wide. Source-checkout users can still set `subtitles.font`
to any installed family. Render a short preview before the full video:

Before starting a task, the desktop app also offers **Preview and adjust subtitles**. Drag the
subtitle box to set its horizontal/vertical position, then drag the green lower-right handle to
set an exact size. The selected values are passed to the renderer as `position_x_percent`,
`position_y_percent`, and `font_size`, so the final ASS and hard-subtitle video use the layout
you approved. The preview is a layout canvas; it does not download a video or start processing.

After a project finishes, use the desktop toolbar's **字幕审核** button, choose that project's
folder, and edit individual target-language cues without changing their timestamps. **保存修改**
rebuilds the affected SRT/ASS (including bilingual tracks), while **从此处预览 12 秒** renders a
separate `review_preview_*.mp4` around the selected cue. The final video is never overwritten by
the review preview; run the normal full render only after you approve the result.

```powershell
python main.py preview "output\PROJECT_NAME" --start 60 --duration 15
```

The readability pass wraps long Chinese text without changing timestamps and reports high
characters-per-second cues. ASS canvas width and Chinese line length follow the source video's
display aspect ratio, including rotation metadata, so portrait video does not crop a landscape
subtitle layout. Bilingual output projects the translated paragraph onto the same local Whisper
timeline, so independent platform-caption boundaries cannot drift apart. The pass does not invent
or rewrite factual content.

Every completed localized project also attempts to produce a selectable-subtitle MP4. Its video
and audio are stream-copied, so it is much faster than a hard-subtitle render and lets viewers
turn captions on or off in compatible players. If a source container cannot be remuxed safely,
the hard-subtitle video still succeeds and the report records the soft-subtitle warning.
`logs/subtitle_quality.json` and the corresponding section in
`logs/report.md` list only the cues that warrant review: overly fast reading, flashes under 0.7s,
overlong lines, and adjacent duplicate text. These findings do not alter the subtitle automatically.

## Optional NVIDIA/CUDA setup

`faster-whisper` uses CTranslate2. The Complete package includes the CUDA 12 runtime via its
bundled Ollama runtime; the Standard package uses CPU safely unless compatible CUDA libraries are
available on the computer. The app registers a compatible runtime before starting Whisper, so an
NVIDIA GPU is used only after a real DLL preflight.
Check the chosen device with:

```powershell
python main.py doctor
```

With `transcription.device: auto`, CUDA is selected only when CTranslate2 detects a device and
the CUDA 12 libraries can be loaded. Otherwise Whisper starts directly on CPU `int8`, avoiding an
unsafe partial GPU attempt. If a later GPU execution error occurs, transcription restarts on CPU.
CPU fallback chooses a conservative thread count from the available cores and RAM, leaving the
desktop responsive. Set `transcription.cpu_threads` to `1`–`32` only when an explicit override is
needed. Avoid `large-v3` on CPU unless you understand the RAM/runtime cost.

For a source-checkout installation, install Ollama or set `YOUTUBE_LOCALIZER_CUDA_RUNTIME` to a
folder that contains the CUDA 12 libraries. The offline installer needs no separate CUDA setup.

Offline subtitle translation prioritizes reliability: `translation.offline_device: auto` uses
CPU `int8`. Set it to `cuda` only when the CTranslate2 CUDA and cuDNN runtime is fully installed;
Whisper and video rendering keep their independent device settings.

For rendering, leave `render.codec: auto` to test NVIDIA NVENC, Intel Quick Sync, and AMD AMF on
the current computer. NVENC is checked in the normal FFmpeg and then the bundled compatibility
encoder. If no hardware path works, the application retries with `libx264`. You may still set an
explicit codec such as `h264_nvenc`, `h264_qsv`, `h264_amf`, or `libx264` for a reproducible setup.

## Release verification

Version 0.6.8 adds a native Windows desktop launcher, matching-version model-pack validation,
safe two-job GUI scheduling, and bounded retry handling for temporary public-source limits. It also preserves the
compressed Standard distribution. It also includes local-AI/API-only translation paths from English
or Simplified Chinese to eight additional target languages, extensionless CDN video URL validation,
and the interactive subtitle layout preview. Install one Whisper pack after the base application; a
packaged app blocks subtitle processing with a clear instruction when no model pack is present. See [CHANGELOG.md](CHANGELOG.md) for the complete
per-version history.
After installation, run **Verify YouTube Localizer Installation** from the Start menu to validate
the packaged base manifest and load the desktop app without processing a video. The full repository
verification command also starts bundled Qwen once:

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\test_offline_install.ps1 `
  -InstallRoot "C:\path\to\YouTube Chinese Localizer"
```

For a diagnostic ZIP that omits video and subtitle text and redacts links, paths, and credentials:

```powershell
python main.py support-bundle "C:\Users\you\Videos\YouTube Chinese Localizer\project_name"
```

## Running tests

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

The integration test creates a two-second audio/video fixture with local FFmpeg, burns an
ASS subtitle, and validates the output. It is skipped when FFmpeg or ffprobe is unavailable
and never uses the internet.

## Troubleshooting

### `ffmpeg` or `ffprobe` is missing

Install FFmpeg, ensure its `bin` directory is on `PATH`, open a new terminal, and rerun
`python main.py doctor`. Use a build with libass; otherwise the `subtitles`/`ass` filter may
be missing.

### `faster-whisper` cannot be installed

Use Python 3.11-3.13 in a new virtual environment. The rest of the pipeline works without
it when usable source-language subtitles already exist. On a new Python release, CTranslate2 wheels
may not yet be published.

### Whisper runs out of GPU memory

Set `transcription.model: small` or `medium`, set `device: cpu`, or select a lower-memory
compute type. The error message identifies this recovery path.

### Offline translation model cannot download or load

Install the lightweight runtime with `python -m pip install -e ".[offline-translation]"`.
The offline installer already contains both directional models. A source-checkout installation
downloads a missing model only on its first offline run. `offline_device: auto` uses CPU `int8` to
avoid partial CUDA installations stalling translation; select `cuda` explicitly only after its
runtime is complete.

### YouTube video is unavailable

Confirm it is a public single-video URL. Private, authenticated, age-restricted, DRM, and
currently-live sources are intentionally unsupported. The application does not accept
cookies or browser-authentication bypasses.

### YouTube video download returns HTTP 429

The application does not request YouTube captions, so caption-endpoint rate limits no longer apply.
If the video request itself is rate-limited, wait before rerunning the same input with `--resume`;
repeated immediate retries can extend a temporary rate limit.

### FFmpeg cannot render subtitles

Check `ffmpeg -filters` for `ass` and `subtitles`, install a libass-enabled build, confirm
the configured font is installed, and run `preview` before rendering the whole video.

If FFmpeg reports Windows status `0xC000013A` (decimal `3221225786`), rendering was stopped
by the Stop button, a closed localizer window, or another interruption; it is not a codec
failure. Keep the window open and resume the same project. Rendering now reports percentage,
encoded timestamp, and speed every two seconds, and resume repeats only the unfinished stage.

### A manual import is rejected

Ask ChatGPT to return JSONL only. Do not change `id`, `start`, `end`, or the source field
(`en` or `zh`); fill every target field (`zh` or `en`). Re-export the original chunk if needed.

### Existing project error

Use `--resume` to continue safely. Use `--overwrite` only when you intend to replace the
exact matching project.

## Known limitations

- Public YouTube extraction depends on the current `yt-dlp` release and YouTube behavior.
- Phase 1 does not authenticate to YouTube or bypass restrictions.
- Translation quality and name choices require human review, especially for niche proper nouns
  and humor. Local AI paragraph mode is more fluent than the compact fast model but still cannot
  recover names that were seriously corrupted by automatic speech recognition.
- Publishing drafts are conservative and deliberately mark titles/license text for review.
- No automatic upload is implemented.
- No automatic advanced subtitle retiming is performed.
- Soft-subtitle MP4 and thumbnail text overlays are not yet exposed in Phase 1.
- Source videos with no audio stream cannot pass final output validation.
