# YouTube Chinese Localization Pipeline

A production-oriented local Python application that localizes authorized English- or
Chinese-language YouTube and local videos in either direction. Each reusable project contains
normalized English subtitles, Simplified Chinese subtitles, optional bilingual subtitles, and
a validated hard-subtitled MP4. A download-only mode keeps the highest-quality merged source
video without creating or burning subtitles.

The pipeline is resumable, keeps intermediate files, never uploads content, and can complete
English↔Chinese localization without an API by using local multilingual Whisper transcription
and local translation models. YouTube caption tracks are never downloaded or consumed. Manual
ChatGPT export/import remains available.

> 中文用户：请阅读完整的[中文使用说明书](docs/USER_GUIDE.zh-CN.md)。

## Legal-use notice

Use this tool only for:

- videos you own;
- public-domain material;
- Creative Commons material whose license permits your intended use; or
- material for which you have explicit translation and redistribution permission.

It does not bypass DRM, paywalls, private-video controls, age gates, region/authentication
requirements, or platform access controls. You are responsible for verifying the license,
attribution requirements, and publishing-platform rules.

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
- H.264/AAC hard-subtitled MP4 rendering with NVENC-to-libx264 fallback
- Preview rendering and output stream/duration/decode validation
- Atomic state/report writes and hash-based resume decisions
- Structured JSONL file logs plus readable console output
- Conservative publishing metadata drafts marked for human review
- Offline unit tests and an FFmpeg synthetic-video integration test

Advanced retiming, thumbnail overlays, soft-subtitle MP4 creation, and polished
platform-specific metadata generation remain future enhancements. Timestamps are deliberately
not changed in Phase 1.

## Windows quick start

For a normal Windows installation, use the split offline setup set from `dist`: keep the setup
`.exe` and all adjacent `.bin` files together, then run the `.exe`. It installs its own Python,
FFmpeg, Ollama runtime, Whisper Medium, Qwen3:4b, and both fast translation models. No model is
downloaded on first use. See [installer/README.md](installer/README.md) for reproducible build
instructions.

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

The command-line default translation provider is `manual`. Add `--translation-provider
offline` for a no-API end-to-end run. The desktop interface defaults to offline translation.

## Windows paste-a-link desktop interface

After completing the Windows installation above, double-click `Start Localizer.cmd` in the
project folder. The streamlined downloader-style interface makes **Paste Link** the primary
action, keeps the empty state distraction-free, and reveals the current task only after a video
is added. Processing settings, API fields, and the run log stay collapsed until needed. You can then:

1. paste an authorized public YouTube URL (or select a local video);
2. choose **English → Simplified Chinese** or **Simplified Chinese → English**;
3. choose target-only or bilingual subtitles;
4. confirm that you have the required rights or permission; and
5. click **开始本地化**.

The window streams progress from the existing resumable pipeline and provides a button for
opening the `output` folder. Closing or stopping a run keeps completed stages so the same
input can be resumed later. There is no YouTube-caption option: both directions always transcribe
the source audio with the local bundled Whisper model.

YouTube downloads default to the highest-resolution video stream and the best available audio
stream without restricting the source codec to MP4/M4A. Formats are ranked by resolution,
frame rate, bitrate, and file size; FFmpeg still produces the final hard-subtitled MP4. The
project dependency set includes Deno and `yt-dlp-ejs`; `python main.py doctor` must report
`yt-dlp JavaScript support: ok` so YouTube's complete format list can be discovered.

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

## Configuration

Copy `config.example.yaml` to a new filename and edit it; the example is never overwritten:

```powershell
Copy-Item config.example.yaml config.local.yaml
python main.py process "D:\Videos\owned-video.mp4" --config config.local.yaml
```

Important settings:

```yaml
output_directory: output
subtitle_mode: chinese  # download_only, chinese, bilingual_en_zh, bilingual_zh_en

transcription:
  model: medium
  device: auto          # auto, cpu, cuda
  compute_type: auto
  beam_size: 5
  vad_filter: true
  word_timestamps: true

translation:
  direction: en-to-zh   # en-to-zh or zh-to-en
  provider: ollama      # manual, offline, ollama, or openai-compatible
  batch_size: 40
  offline_device: auto  # auto uses reliable CPU; cuda must be selected explicitly
  ollama_endpoint: http://localhost:11434
  ollama_model: qwen3:4b

download:
  format: bestvideo+bestaudio/best
  format_sort: [res, fps, br, size]

subtitles:
  font: Noto Sans CJK SC
  font_size: 48
  max_chinese_chars_per_line: 20

render:
  codec: libx264        # h264_nvenc/hevc_nvenc are also accepted
  crf: 18
  preset: medium
```

Each project stores `config.resolved.json` so later project commands use the same settings.

To download the best available video and audio without transcription, translation, or subtitle
rendering:

```powershell
python main.py process "https://www.youtube.com/watch?v=VIDEO_ID" --subtitle-mode download_only
```

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
bundles `Noto Sans CJK SC` (the default), `Noto Serif CJK SC`, and `LXGW WenKai` under the SIL Open
Font License. The desktop app exposes all three plus the Windows `Microsoft YaHei` system font
in its subtitle-font selector. FFmpeg loads bundled fonts directly from the application, so they
do not need to be installed system-wide. Source-checkout users can set `subtitles.font` to any
installed family. Render a short preview before the full video:

```powershell
python main.py preview "output\PROJECT_NAME" --start 60 --duration 15
```

The readability pass wraps long Chinese text without changing timestamps and reports high
characters-per-second cues. ASS canvas width and Chinese line length follow the source video's
display aspect ratio, including rotation metadata, so portrait video does not crop a landscape
subtitle layout. Bilingual output projects the translated paragraph onto the same local Whisper
timeline, so independent platform-caption boundaries cannot drift apart. The pass does not invent
or rewrite factual content.

## Optional NVIDIA/CUDA setup

`faster-whisper` uses CTranslate2. The offline installer already includes the CUDA 12 runtime
required by its bundled Whisper stack, via its bundled Ollama runtime. Version 0.4.3 registers
that runtime before starting Whisper, so an NVIDIA GPU is used only after a real DLL preflight.
Check the chosen device with:

```powershell
python main.py doctor
```

With `transcription.device: auto`, CUDA is selected only when CTranslate2 detects a device and
the CUDA 12 libraries can be loaded. Otherwise Whisper starts directly on CPU `int8`, avoiding an
unsafe partial GPU attempt. If a later GPU execution error occurs, transcription restarts on CPU.
CPU fallback uses six threads by default, leaving the desktop responsive. Avoid `large-v3` on CPU
unless you understand the RAM/runtime cost.

For a source-checkout installation, install Ollama or set `YOUTUBE_LOCALIZER_CUDA_RUNTIME` to a
folder that contains the CUDA 12 libraries. The offline installer needs no separate CUDA setup.

Offline subtitle translation prioritizes reliability: `translation.offline_device: auto` uses
CPU `int8`. Set it to `cuda` only when the CTranslate2 CUDA and cuDNN runtime is fully installed;
Whisper and video rendering keep their independent device settings.

For rendering, set `render.codec: h264_nvenc` or `hevc_nvenc`. If the selected NVENC encoder
fails, the application retries with `libx264`.

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
