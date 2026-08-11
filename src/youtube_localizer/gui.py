from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections.abc import Callable, Mapping
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from .config import default_output_directory, output_directory_advice
from .models import ProjectPaths
from .resources import installed_whisper_models, ollama_executable, package_tier
from .support import create_support_bundle

PROJECT_ROOT = Path(__file__).resolve().parents[2]

APP_BACKGROUND = "#F5F6F8"
SURFACE = "#FFFFFF"
HEADER = "#FFFFFF"
PRIMARY = "#2FAD68"
PRIMARY_HOVER = "#278F57"
TEXT = "#24272C"
MUTED = "#747A84"
BORDER = "#E2E5E9"
SUCCESS = "#2FAD68"
DANGER = "#D14D57"
LOG_BACKGROUND = "#F7F8FA"
LOG_TEXT = "#40444B"
UI_FONT = "Microsoft YaHei UI"

SUBTITLE_MODES = {
    "仅下载原视频（无字幕）": "download_only",
    "仅目标语言字幕": "chinese",
    "英文在上，中文在下": "bilingual_en_zh",
    "中文在上，英文在下": "bilingual_zh_en",
}
TRANSLATION_DIRECTIONS = {
    "英文 → 简体中文": "en-to-zh",
    "简体中文 → 英文": "zh-to-en",
}
TRANSLATION_MODES = {
    "免费模式（处理到人工翻译）": "manual",
    "本地快速翻译并压制（无需 API）": "offline",
    "本地 AI 段落翻译并压制（高质量，无 API Key）": "ollama",
    "自动翻译并压制字幕（需要 API）": "openai-compatible",
}
DEFAULT_SUBTITLE_FONT = "Noto Sans CJK SC"
SUBTITLE_FONTS = {"Noto Sans CJK SC（默认）": DEFAULT_SUBTITLE_FONT}
SUBTITLE_FONT_SIZES = {
    "小号（40）": 40,
    "标准（48，推荐）": 48,
    "大号（56）": 56,
    "超大（64）": 64,
}
SUBTITLE_POSITION_MIN = 2
SUBTITLE_POSITION_MAX = 98
SUBTITLE_PREVIEW_WIDTH = 16
SUBTITLE_PREVIEW_HEIGHT = 9


PROCESSING_PROFILES = frozenset({"auto", "fast", "balanced", "quality", "safe_cpu"})

OUTPUT_QUALITIES = {
    "最高质量（推荐）": "best",
    "高质量（文件更小）": "high",
    "标准质量（节省空间）": "standard",
}
OUTPUT_FRAME_RATES = {
    "保持原视频帧率（推荐）": None,
    "60 FPS": 60,
    "30 FPS": 30,
}
OUTPUT_HEIGHTS = {
    "保持原视频分辨率（推荐）": None,
    "4K / 2160p": 2160,
    "2K / 1440p": 1440,
    "1080p": 1080,
    "720p": 720,
}

_DOWNLOAD_PROGRESS_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_LOCAL_AI_PROGRESS_RE = re.compile(r"Local AI translating paragraph\s+(\d+)/(\d+)")
_OFFLINE_PROGRESS_RE = re.compile(r"Offline translating contextual subtitle batch\s+(\d+)/(\d+)")
_RENDER_PROGRESS_RE = re.compile(r"Rendering subtitles:\s+(\d+(?:\.\d+)?)%")


def queue_input_values(value: str) -> list[str]:
    """Return one input per non-empty line while retaining local paths with spaces."""
    values = [line.strip() for line in value.splitlines() if line.strip()]
    if not values and value.strip():
        values = [value.strip()]
    return list(dict.fromkeys(values))


def progress_update_from_output(line: str, *, provider: str) -> tuple[float, str] | None:
    """Map the pipeline's real progress messages to a single GUI progress percentage."""
    if "Preflight ready:" in line:
        return 2.0, "正在检查硬件、离线模型和磁盘空间…"
    if "Preflight warning:" in line:
        return 2.0, "发现兼容性提示，正在采用安全方案…"
    if download := _DOWNLOAD_PROGRESS_RE.search(line):
        percent = min(100.0, float(download.group(1)))
        if provider == "download_only":
            return percent, f"正在下载原视频：{percent:.1f}%"
        return percent * 0.22, f"正在下载原视频：{percent:.1f}%"

    if "Processing audio with duration" in line:
        return 24.0, "正在识别原语言语音…"
    if "Local AI paragraph translation ready" in line:
        return 47.0, "正在准备本地 AI 段落翻译…"
    if local_ai := _LOCAL_AI_PROGRESS_RE.search(line):
        current, total = (int(value) for value in local_ai.groups())
        if total:
            return 47.0 + 28.0 * (current - 1) / total, f"本地 AI 翻译：{current}/{total} 段"
    if offline := _OFFLINE_PROGRESS_RE.search(line):
        current, total = (int(value) for value in offline.groups())
        if total:
            return 47.0 + 28.0 * (current - 1) / total, f"本地快速翻译：{current}/{total} 批"
    if render := _RENDER_PROGRESS_RE.search(line):
        percent = min(100.0, float(render.group(1)))
        return 77.0 + 22.0 * percent / 100, f"正在压制字幕：{percent:.1f}%"
    return None


def gui_process_creationflags() -> int:
    """Hide the CLI helper console while retaining a stoppable process group on Windows."""
    if os.name == "nt":
        return subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    return 0


def local_ai_available() -> bool:
    return ollama_executable() is not None


def whisper_model_installation_message() -> str | None:
    """Explain the required model-pack action before a packaged app starts a subtitle job."""
    if package_tier() is None or installed_whisper_models():
        return None
    return (
        "尚未安装 Whisper 语音识别模型。请安装 Whisper Small（大多数电脑推荐）或 "
        "Whisper Medium（更高质量、需要更多内存/显存）模型包后再开始字幕任务。"
    )


def mode_description(subtitle_mode: str, translation_provider: str) -> str:
    """Return the short explanation shown under the selected workflow."""
    if subtitle_mode == "download_only":
        return "只下载并合并最高画质视频与最高质量音频，不生成字幕。"
    descriptions = {
        "manual": "准备原语言字幕和翻译文件，等待人工导入译文。",
        "offline": "使用轻量本地模型自动翻译，速度优先，无需 API。",
        "ollama": "使用本地 Qwen 理解完整段落后自然翻译，推荐。",
        "openai-compatible": "使用 OpenAI-compatible 接口自动翻译；API Key 仅用于当前任务。",
    }
    return descriptions.get(translation_provider, "选择处理方式后即可开始。")


def clamp_subtitle_preview_values(
    x_percent: int, y_percent: int, font_size: int
) -> tuple[int, int, int]:
    """Keep interactive preview values valid for the ASS renderer and CLI."""
    return (
        max(SUBTITLE_POSITION_MIN, min(SUBTITLE_POSITION_MAX, round(x_percent))),
        max(SUBTITLE_POSITION_MIN, min(SUBTITLE_POSITION_MAX, round(y_percent))),
        max(12, min(120, round(font_size))),
    )


def build_process_command(
    input_value: str,
    *,
    subtitle_mode: str,
    translation_provider: str,
    translation_direction: str = "en-to-zh",
    subtitle_font: str = DEFAULT_SUBTITLE_FONT,
    subtitle_font_size: int | None = None,
    subtitle_position_x: int | None = None,
    subtitle_position_y: int | None = None,
    processing_profile: str | None = None,
    output_quality: str | None = None,
    output_fps: int | None = None,
    output_height: int | None = None,
    output_directory: str | Path | None = None,
    resume: bool = True,
    python_executable: str | None = None,
    main_script: Path | None = None,
) -> list[str]:
    """Build the argument-array command used by the desktop launcher."""
    value = input_value.strip()
    if not value:
        raise ValueError("请粘贴 YouTube 链接或选择本地视频。")
    if subtitle_mode not in SUBTITLE_MODES.values():
        raise ValueError("未知的字幕模式。")
    if translation_provider not in TRANSLATION_MODES.values():
        raise ValueError("未知的翻译模式。")
    if translation_direction not in TRANSLATION_DIRECTIONS.values():
        raise ValueError("未知的翻译方向。")
    if subtitle_font not in SUBTITLE_FONTS.values():
        raise ValueError("未知的字幕字体。")
    if subtitle_font_size is not None and not 12 <= subtitle_font_size <= 120:
        raise ValueError("字幕字号必须在 12 到 120 之间。")
    for position_value, label in (
        (subtitle_position_x, "水平"),
        (subtitle_position_y, "垂直"),
    ):
        if (
            position_value is not None
            and not SUBTITLE_POSITION_MIN <= position_value <= SUBTITLE_POSITION_MAX
        ):
            raise ValueError(f"字幕{label}位置必须在 2% 到 98% 之间。")
    if processing_profile is not None and processing_profile not in PROCESSING_PROFILES:
        raise ValueError("Unknown processing profile.")
    if output_quality is not None and output_quality not in OUTPUT_QUALITIES.values():
        raise ValueError("Unknown output quality.")
    if output_fps is not None and not 1 <= output_fps <= 240:
        raise ValueError("Output FPS must be between 1 and 240.")
    if output_height is not None and not 144 <= output_height <= 4320:
        raise ValueError("Output height must be between 144 and 4320 pixels.")
    output_path: Path | None = None
    if output_directory is not None:
        raw_output_directory = str(output_directory).strip()
        if not raw_output_directory:
            raise ValueError("请选择项目输出文件夹。")
        output_path = Path(raw_output_directory).expanduser()
    command = [
        python_executable or sys.executable,
        str(main_script or PROJECT_ROOT / "main.py"),
        "process",
        value,
        "--subtitle-mode",
        subtitle_mode,
        "--translation-provider",
        translation_provider,
        "--translation-direction",
        translation_direction,
        "--subtitle-font",
        subtitle_font,
    ]
    if subtitle_font_size is not None:
        command.extend(["--subtitle-font-size", str(subtitle_font_size)])
    if subtitle_position_x is not None:
        command.extend(["--subtitle-position-x", str(subtitle_position_x)])
    if subtitle_position_y is not None:
        command.extend(["--subtitle-position-y", str(subtitle_position_y)])
    if output_path is not None:
        command.extend(["--output-dir", str(output_path)])
    if processing_profile:
        command.extend(["--processing-profile", processing_profile])
    if output_quality:
        command.extend(["--output-quality", output_quality])
    if output_fps:
        command.extend(["--output-fps", str(output_fps)])
    if output_height:
        command.extend(["--output-height", str(output_height)])
    if resume:
        command.append("--resume")
    return command


def api_configuration(environment: Mapping[str, str]) -> tuple[str, str, str]:
    """Return the configured endpoint, model and key without persisting them."""
    return (
        environment.get("OPENAI_COMPATIBLE_ENDPOINT", ""),
        environment.get("OPENAI_COMPATIBLE_MODEL", ""),
        environment.get("OPENAI_COMPATIBLE_API_KEY", ""),
    )


def terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Stop only the launcher-owned process tree."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        process.terminate()


class SubtitlePreviewDialog:
    """Interactive layout preview that stores an ASS-compatible subtitle position."""

    def __init__(
        self,
        parent: tk.Tk,
        *,
        subtitle_mode: str,
        x_percent: int,
        y_percent: int,
        font_size: int,
        on_apply: Callable[[int, int, int], None],
    ) -> None:
        self.on_apply = on_apply
        self.subtitle_mode = subtitle_mode
        self.x_percent, self.y_percent, self.font_size = clamp_subtitle_preview_values(
            x_percent, y_percent, font_size
        )
        self._drag_mode: str | None = None
        self._drag_start = (0, 0)
        self._drag_initial = (self.x_percent, self.y_percent, self.font_size)
        self._preview_box = (0.0, 0.0, 1.0, 1.0)
        self._subtitle_bounds: tuple[float, float, float, float] | None = None

        self.window = tk.Toplevel(parent)
        self.window.title("字幕样式预览")
        self.window.configure(background=APP_BACKGROUND)
        self.window.geometry("920x650")
        self.window.minsize(700, 520)
        self.window.transient(parent)
        self.window.grab_set()

        body = ttk.Frame(self.window, style="App.TFrame", padding=(20, 18, 20, 16))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="拖动字幕位置与大小", style="SectionTitle.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text="拖动字幕本体调整位置；拖动右下角绿色控制点调整字号。此设置会用于最终压制。",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(3, 12))

        self.canvas = tk.Canvas(
            body,
            background="#E9EDF1",
            highlightthickness=0,
            borderwidth=0,
            cursor="fleur",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._stop_drag)

        self.status = tk.StringVar()
        ttk.Label(body, textvariable=self.status, style="Muted.TLabel").pack(
            anchor="w", pady=(10, 8)
        )
        buttons = ttk.Frame(body, style="App.TFrame")
        buttons.pack(fill="x")
        ttk.Button(buttons, text="恢复默认", style="Secondary.TButton", command=self._reset).pack(
            side="left"
        )
        ttk.Button(buttons, text="取消", style="Secondary.TButton", command=self.window.destroy).pack(
            side="right"
        )
        ttk.Button(buttons, text="应用到任务", style="Primary.TButton", command=self._apply).pack(
            side="right", padx=(0, 8)
        )
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.after_idle(self._draw)

    def _preview_sample(self) -> str:
        if self.subtitle_mode == "bilingual_en_zh":
            return "Natural subtitles begin with the complete idea.\n先理解完整段落，再呈现自然字幕。"
        if self.subtitle_mode == "bilingual_zh_en":
            return "先理解完整段落，再呈现自然字幕。\nNatural subtitles begin with the complete idea."
        return "先理解完整段落，再呈现自然字幕。"

    def _canvas_preview_box(self) -> tuple[float, float, float, float]:
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        unit = min((canvas_width - 24) / SUBTITLE_PREVIEW_WIDTH, (canvas_height - 24) / SUBTITLE_PREVIEW_HEIGHT)
        width = max(320.0, unit * SUBTITLE_PREVIEW_WIDTH)
        height = max(180.0, unit * SUBTITLE_PREVIEW_HEIGHT)
        left = (canvas_width - width) / 2
        top = (canvas_height - height) / 2
        return left, top, left + width, top + height

    def _draw(self) -> None:
        if not self.window.winfo_exists():
            return
        self.canvas.delete("all")
        left, top, right, bottom = self._preview_box = self._canvas_preview_box()
        self.canvas.create_rectangle(left, top, right, bottom, fill="#151B26", outline="#273244", width=1)
        self.canvas.create_rectangle(left, top, right, top + 48, fill="#1E2939", outline="")
        self.canvas.create_text(
            left + 18,
            top + 24,
            text="字幕布局预览 · 16:9",
            anchor="w",
            fill="#C7D0DC",
            font=(UI_FONT, 10),
        )
        self.canvas.create_text(
            (left + right) / 2,
            (top + bottom) / 2 - 26,
            text="VIDEO PREVIEW",
            fill="#39485E",
            font=("Segoe UI", 18, "bold"),
        )
        self.canvas.create_text(
            (left + right) / 2,
            (top + bottom) / 2 + 7,
            text="预览仅用于调整字幕布局，不会下载视频",
            fill="#5D6C82",
            font=(UI_FONT, 10),
        )

        preview_width = right - left
        preview_height = bottom - top
        x = left + preview_width * self.x_percent / 100
        y = top + preview_height * self.y_percent / 100
        size = max(14, round(self.font_size * preview_width / 1920))
        text = self._preview_sample()
        for offset_x, offset_y in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            self.canvas.create_text(
                x + offset_x,
                y + offset_y,
                text=text,
                anchor="s",
                width=preview_width - 56,
                justify="center",
                fill="#101010",
                font=(DEFAULT_SUBTITLE_FONT, size),
                tags=("subtitle",),
            )
        subtitle = self.canvas.create_text(
            x,
            y,
            text=text,
            anchor="s",
            width=preview_width - 56,
            justify="center",
            fill="#FFFFFF",
            font=(DEFAULT_SUBTITLE_FONT, size),
            tags=("subtitle", "subtitle_foreground"),
        )
        bbox = self.canvas.bbox(subtitle)
        if bbox is not None:
            bound_left, bound_top, bound_right, bound_bottom = (value - 7 if index < 2 else value + 7 for index, value in enumerate(bbox))
            self._subtitle_bounds = (bound_left, bound_top, bound_right, bound_bottom)
            self.canvas.create_rectangle(
                bound_left,
                bound_top,
                bound_right,
                bound_bottom,
                outline=PRIMARY,
                dash=(4, 3),
                width=1,
                tags=("subtitle_bounds",),
            )
            self.canvas.create_rectangle(
                bound_right - 6,
                bound_bottom - 6,
                bound_right + 6,
                bound_bottom + 6,
                fill=PRIMARY,
                outline="#FFFFFF",
                width=1,
                tags=("subtitle_handle",),
            )
        self.status.set(
            f"位置：水平 {self.x_percent}% · 垂直 {self.y_percent}%　|　字号：{self.font_size}"
        )

    def _start_drag(self, event: tk.Event[tk.Misc]) -> None:
        item_ids = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        tags = {tag for item in item_ids for tag in self.canvas.gettags(item)}
        if "subtitle_handle" in tags:
            self._drag_mode = "resize"
        elif "subtitle" in tags or "subtitle_bounds" in tags:
            self._drag_mode = "move"
        else:
            self._drag_mode = None
            return
        self._drag_start = (event.x, event.y)
        self._drag_initial = (self.x_percent, self.y_percent, self.font_size)

    def _drag(self, event: tk.Event[tk.Misc]) -> None:
        if self._drag_mode is None:
            return
        left, top, right, bottom = self._preview_box
        preview_width = max(1.0, right - left)
        preview_height = max(1.0, bottom - top)
        initial_x, initial_y, initial_size = self._drag_initial
        if self._drag_mode == "move":
            x = round((event.x - left) * 100 / preview_width)
            y = round((event.y - top) * 100 / preview_height)
            self.x_percent, self.y_percent, self.font_size = clamp_subtitle_preview_values(
                x, y, initial_size
            )
        else:
            delta = max(event.x - self._drag_start[0], event.y - self._drag_start[1])
            size_change = round(delta * 1920 / preview_width)
            self.x_percent, self.y_percent, self.font_size = clamp_subtitle_preview_values(
                initial_x, initial_y, initial_size + size_change
            )
        self._draw()

    def _stop_drag(self, _event: tk.Event[tk.Misc]) -> None:
        self._drag_mode = None

    def _reset(self) -> None:
        self.x_percent, self.y_percent, self.font_size = 50, 96, 48
        self._draw()

    def _apply(self) -> None:
        self.on_apply(self.x_percent, self.y_percent, self.font_size)
        self.window.destroy()


class LocalizerWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Localize Studio｜视频本地化")
        self.root.geometry("980x720")
        self.root.minsize(820, 620)
        self.root.configure(background=APP_BACKGROUND)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.worker: threading.Thread | None = None
        self.stop_requested = False
        self.active_direction = "en-to-zh"
        self.active_provider = ""
        self._progress_value = 0.0
        self.active_queue_index = 1
        self.active_queue_total = 1

        endpoint, model, api_key = api_configuration(os.environ)
        default_translation = (
            "本地 AI 段落翻译并压制（高质量，无 API Key）"
            if local_ai_available()
            else "本地快速翻译并压制（无需 API）"
        )

        self.input_value = tk.StringVar()
        self.direction_label = tk.StringVar(value="英文 → 简体中文")
        self.subtitle_label = tk.StringVar(value="仅目标语言字幕")
        self.translation_label = tk.StringVar(value=default_translation)
        self.font_size_label = tk.StringVar(value="标准（48，推荐）")
        self.subtitle_font_size_value = tk.IntVar(value=48)
        self.subtitle_position_x = tk.IntVar(value=50)
        self.subtitle_position_y = tk.IntVar(value=96)
        self.output_quality_label = tk.StringVar(value="最高质量（推荐）")
        self.output_fps_label = tk.StringVar(value="保持原视频帧率（推荐）")
        self.output_height_label = tk.StringVar(value="保持原视频分辨率（推荐）")
        self.output_directory = tk.StringVar(value=str(default_output_directory()))
        self.endpoint = tk.StringVar(value=endpoint or "https://api.openai.com/v1")
        self.model = tk.StringVar(value=model)
        self.api_key = tk.StringVar(value=api_key)
        self.authorized = tk.BooleanVar(value=False)
        self.resume = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="等待粘贴链接")
        self.mode_hint = tk.StringVar()
        self.output_hint = tk.StringVar()
        self.output_directory_hint = tk.StringVar()
        self.workflow_summary = tk.StringVar()
        self.settings_visible = False
        self.log_visible = False

        self._configure_style()
        self._build_layout()
        self._update_translation_fields()
        self._update_output_settings()
        self.input_value.trace_add("write", self._update_input_state)
        self.output_directory.trace_add("write", self._update_output_directory_hint)
        self._update_input_state()
        self.root.after(100, self._poll_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure("App.TFrame", background=APP_BACKGROUND)
        style.configure("Toolbar.TFrame", background=HEADER)
        style.configure("Card.TFrame", background=SURFACE, relief="flat")
        style.configure("Toolbar.TLabel", background=HEADER, foreground=TEXT, font=(UI_FONT, 10))
        style.configure("Card.TLabel", background=SURFACE, foreground=TEXT, font=(UI_FONT, 10))
        style.configure(
            "Field.TLabel", background=SURFACE, foreground=TEXT, font=(UI_FONT, 9, "bold")
        )
        style.configure("Muted.TLabel", background=SURFACE, foreground=MUTED, font=(UI_FONT, 9))
        style.configure(
            "AppMuted.TLabel", background=APP_BACKGROUND, foreground=MUTED, font=(UI_FONT, 9)
        )
        style.configure(
            "SectionTitle.TLabel",
            background=SURFACE,
            foreground=TEXT,
            font=(UI_FONT, 12, "bold"),
        )
        style.configure(
            "Primary.TButton",
            background=PRIMARY,
            foreground="#FFFFFF",
            bordercolor=PRIMARY,
            font=(UI_FONT, 10, "bold"),
            padding=(17, 9),
        )
        style.map(
            "Primary.TButton",
            background=[
                ("pressed", PRIMARY_HOVER),
                ("active", PRIMARY_HOVER),
                ("disabled", "#A9D8BD"),
            ],
            foreground=[("disabled", "#EFF8F2")],
        )
        style.configure(
            "Secondary.TButton",
            background=SURFACE,
            foreground=TEXT,
            bordercolor=BORDER,
            font=(UI_FONT, 9),
            padding=(12, 7),
        )
        style.map("Secondary.TButton", background=[("active", "#F0F2F4")])
        style.configure(
            "Toolbar.TButton",
            background=HEADER,
            foreground=TEXT,
            bordercolor=HEADER,
            font=(UI_FONT, 9),
            padding=(11, 7),
        )
        style.map("Toolbar.TButton", background=[("active", "#F0F2F4")])
        style.configure(
            "Danger.TButton",
            background="#FBEAEC",
            foreground=DANGER,
            bordercolor="#F2CDD1",
            font=(UI_FONT, 9, "bold"),
            padding=(14, 8),
        )
        style.map("Danger.TButton", background=[("active", "#F6D9DC")])
        style.configure(
            "Modern.TEntry",
            fieldbackground="#FAFAFB",
            foreground=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=8,
        )
        style.configure(
            "Modern.TCombobox",
            fieldbackground="#FAFAFB",
            background="#FAFAFB",
            foreground=TEXT,
            bordercolor=BORDER,
            arrowsize=16,
            padding=7,
        )
        style.map(
            "Modern.TCombobox",
            fieldbackground=[("readonly", "#FAFAFB"), ("disabled", "#ECEEF1")],
            foreground=[("readonly", TEXT), ("disabled", "#98A2B3")],
        )
        style.configure("Card.TCheckbutton", background=SURFACE, foreground=TEXT, font=(UI_FONT, 9))
        style.map("Card.TCheckbutton", background=[("active", SURFACE)])
        style.configure(
            "Accent.Horizontal.TProgressbar",
            background=PRIMARY,
            troughcolor="#E8ECE9",
            bordercolor="#E8ECE9",
            lightcolor=PRIMARY,
            darkcolor=PRIMARY,
            thickness=5,
        )

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame")
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(7, weight=1)

        hero = tk.Frame(outer, background=HEADER, padx=18, pady=12)
        hero.grid(row=0, column=0, sticky="ew")
        hero.columnconfigure(4, weight=1)
        brand = tk.Frame(hero, background=HEADER)
        brand.grid(row=0, column=0, sticky="w", padx=(0, 22))
        tk.Label(
            brand,
            text="L",
            width=2,
            background=PRIMARY,
            foreground="#FFFFFF",
            font=(UI_FONT, 13, "bold"),
        ).pack(side="left")
        tk.Label(
            brand,
            text="Localize Studio",
            background=HEADER,
            foreground=TEXT,
            font=(UI_FONT, 12, "bold"),
        ).pack(side="left", padx=(9, 0))
        self.paste_button = ttk.Button(
            hero, text="＋  粘贴链接", style="Primary.TButton", command=self._paste
        )
        self.paste_button.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(
            hero,
            text="选择本地视频",
            style="Secondary.TButton",
            command=self._choose_local_file,
        ).grid(row=0, column=2)
        self.settings_button = ttk.Button(
            hero,
            text="处理设置",
            style="Toolbar.TButton",
            command=self._toggle_settings,
        )
        self.settings_button.grid(row=0, column=5, padx=(8, 0))
        ttk.Button(
            hero,
            text="输出文件夹",
            style="Toolbar.TButton",
            command=self._open_output,
        ).grid(row=0, column=6, padx=(4, 0))
        ttk.Button(
            hero,
            text="导出诊断包",
            style="Toolbar.TButton",
            command=self._export_support_bundle,
        ).grid(row=0, column=7, padx=(4, 0))
        ttk.Separator(outer, orient="horizontal").grid(row=0, column=0, sticky="sew")

        self.empty_state = ttk.Frame(outer, style="App.TFrame")
        self.empty_state.grid(row=1, column=0, rowspan=7, sticky="nsew")
        empty_content = ttk.Frame(self.empty_state, style="App.TFrame")
        empty_content.pack(expand=True)
        tk.Label(
            empty_content,
            text="↓",
            width=3,
            background="#E2F4E9",
            foreground=PRIMARY,
            font=(UI_FONT, 24, "bold"),
        ).pack(pady=(0, 16))
        tk.Label(
            empty_content,
            text="添加一个或多个视频链接",
            background=APP_BACKGROUND,
            foreground=TEXT,
            font=(UI_FONT, 16, "bold"),
        ).pack()
        ttk.Label(
            empty_content,
            text="复制一个链接，或复制多行链接后点击上方“粘贴链接”",
            style="AppMuted.TLabel",
        ).pack(pady=(7, 3))
        ttk.Label(
            empty_content,
            text="最高画质下载 · 本地语音识别 · 离线翻译 · 字幕压制",
            style="AppMuted.TLabel",
        ).pack()

        self.input_frame = ttk.Frame(outer, style="Card.TFrame", padding=(22, 16, 22, 18))
        self.input_frame.grid(row=1, column=0, sticky="ew", padx=24, pady=(20, 0))
        self.input_frame.columnconfigure(0, weight=1)
        ttk.Label(self.input_frame, text="准备处理", style="SectionTitle.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )
        self.input_entry = ttk.Entry(
            self.input_frame,
            textvariable=self.input_value,
            style="Modern.TEntry",
            font=(UI_FONT, 10),
        )
        self.input_entry.grid(row=1, column=0, sticky="ew", ipady=2)
        ttk.Button(
            self.input_frame,
            text="移除",
            style="Secondary.TButton",
            command=self._clear_input,
        ).grid(row=1, column=1, padx=(8, 0))
        ttk.Label(self.input_frame, textvariable=self.workflow_summary, style="Muted.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(9, 0)
        )

        options = self.settings_panel = ttk.Frame(
            outer, style="Card.TFrame", padding=(22, 14, 22, 14)
        )
        options.grid(row=2, column=0, sticky="ew", padx=24, pady=(12, 0))
        for column in range(4):
            options.columnconfigure(column, weight=1, uniform="settings")
        ttk.Label(options, text="翻译方向", style="Field.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 5), padx=(0, 6)
        )
        ttk.Label(options, text="字幕 / 下载模式", style="Field.TLabel").grid(
            row=0, column=1, sticky="w", pady=(0, 5), padx=6
        )
        ttk.Label(options, text="翻译方式", style="Field.TLabel").grid(
            row=0, column=2, sticky="w", pady=(0, 5), padx=6
        )
        ttk.Label(options, text="字幕字号", style="Field.TLabel").grid(
            row=0, column=3, sticky="w", pady=(0, 5), padx=(6, 0)
        )
        self.direction_combo = ttk.Combobox(
            options,
            textvariable=self.direction_label,
            values=list(TRANSLATION_DIRECTIONS),
            state="readonly",
            style="Modern.TCombobox",
        )
        self.direction_combo.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        self.direction_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._update_translation_fields()
        )
        self.subtitle_combo = ttk.Combobox(
            options,
            textvariable=self.subtitle_label,
            values=list(SUBTITLE_MODES),
            state="readonly",
            style="Modern.TCombobox",
        )
        self.subtitle_combo.grid(row=1, column=1, sticky="ew", padx=6)
        self.subtitle_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._update_translation_fields()
        )
        self.font_size_combo = ttk.Combobox(
            options,
            textvariable=self.font_size_label,
            values=list(SUBTITLE_FONT_SIZES),
            state="readonly",
            style="Modern.TCombobox",
        )
        self.font_size_combo.grid(row=1, column=3, sticky="ew", padx=(6, 0))
        self.font_size_combo.bind("<<ComboboxSelected>>", self._select_subtitle_font_size)
        self.translation_combo = ttk.Combobox(
            options,
            textvariable=self.translation_label,
            values=list(TRANSLATION_MODES),
            state="readonly",
            style="Modern.TCombobox",
        )
        self.translation_combo.grid(row=1, column=2, sticky="ew", padx=6)
        self.translation_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._update_translation_fields()
        )
        ttk.Label(options, textvariable=self.mode_hint, style="Muted.TLabel").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(9, 0)
        )
        self.preview_button = ttk.Button(
            options,
            text="预览并调整字幕",
            style="Secondary.TButton",
            command=self._show_subtitle_preview,
        )
        self.preview_button.grid(row=2, column=3, sticky="e", pady=(8, 0))

        ttk.Label(options, text="智能加速", style="Field.TLabel").grid(
            row=3, column=0, sticky="w", pady=(12, 5), padx=(0, 6)
        )
        ttk.Label(options, text="输出画质", style="Field.TLabel").grid(
            row=3, column=1, sticky="w", pady=(12, 5), padx=6
        )
        ttk.Label(options, text="输出帧率", style="Field.TLabel").grid(
            row=3, column=2, sticky="w", pady=(12, 5), padx=6
        )
        ttk.Label(options, text="输出分辨率", style="Field.TLabel").grid(
            row=3, column=3, sticky="w", pady=(12, 5), padx=(6, 0)
        )
        ttk.Label(
            options,
            text="自动识别显卡；不可用时自动改用 CPU",
            style="Muted.TLabel",
        ).grid(row=4, column=0, sticky="w", padx=(0, 6))
        self.output_quality_combo = ttk.Combobox(
            options,
            textvariable=self.output_quality_label,
            values=list(OUTPUT_QUALITIES),
            state="readonly",
            style="Modern.TCombobox",
        )
        self.output_quality_combo.grid(row=4, column=1, sticky="ew", padx=6)
        self.output_quality_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._update_output_settings()
        )
        self.output_fps_combo = ttk.Combobox(
            options,
            textvariable=self.output_fps_label,
            values=list(OUTPUT_FRAME_RATES),
            state="readonly",
            style="Modern.TCombobox",
        )
        self.output_fps_combo.grid(row=4, column=2, sticky="ew", padx=6)
        self.output_fps_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._update_output_settings()
        )
        self.output_height_combo = ttk.Combobox(
            options,
            textvariable=self.output_height_label,
            values=list(OUTPUT_HEIGHTS),
            state="readonly",
            style="Modern.TCombobox",
        )
        self.output_height_combo.grid(row=4, column=3, sticky="ew", padx=(6, 0))
        self.output_height_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._update_output_settings()
        )
        ttk.Label(options, textvariable=self.output_hint, style="Muted.TLabel").grid(
            row=5, column=0, columnspan=4, sticky="w", pady=(7, 0)
        )
        ttk.Label(options, text="项目输出文件夹", style="Field.TLabel").grid(
            row=6, column=0, sticky="w", pady=(14, 5), padx=(0, 6)
        )
        self.output_directory_entry = ttk.Entry(
            options,
            textvariable=self.output_directory,
            style="Modern.TEntry",
        )
        self.output_directory_entry.grid(row=7, column=0, columnspan=3, sticky="ew", padx=(0, 6))
        ttk.Button(
            options,
            text="选择位置",
            style="Secondary.TButton",
            command=self._choose_output_directory,
        ).grid(row=7, column=3, sticky="ew", padx=(6, 0))
        ttk.Label(options, textvariable=self.output_directory_hint, style="Muted.TLabel").grid(
            row=8, column=0, columnspan=4, sticky="w", pady=(7, 0)
        )

        self.api_frame = ttk.Frame(
            outer,
            style="Card.TFrame",
            padding=(22, 12, 22, 14),
        )
        self.api_frame.grid(row=3, column=0, sticky="ew", padx=24, pady=(8, 0))
        for column in range(3):
            self.api_frame.columnconfigure(column, weight=1, uniform="api")
        ttk.Label(self.api_frame, text="接口地址", style="Field.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        ttk.Label(self.api_frame, text="模型名称", style="Field.TLabel").grid(
            row=0, column=1, sticky="w", padx=6
        )
        ttk.Label(self.api_frame, text="API Key（不会保存）", style="Field.TLabel").grid(
            row=0, column=2, sticky="w", padx=(6, 0)
        )
        self.endpoint_entry = ttk.Entry(
            self.api_frame, textvariable=self.endpoint, style="Modern.TEntry"
        )
        self.endpoint_entry.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(5, 0))
        self.model_entry = ttk.Entry(self.api_frame, textvariable=self.model, style="Modern.TEntry")
        self.model_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=(5, 0))
        self.key_entry = ttk.Entry(
            self.api_frame, textvariable=self.api_key, show="●", style="Modern.TEntry"
        )
        self.key_entry.grid(row=1, column=2, sticky="ew", padx=(6, 0), pady=(5, 0))

        confirmation = self.confirmation_frame = ttk.Frame(
            outer, style="Card.TFrame", padding=(22, 10, 22, 12)
        )
        confirmation.grid(row=4, column=0, sticky="ew", padx=24, pady=(10, 0))
        ttk.Checkbutton(
            confirmation,
            text="我确认拥有该视频，或已取得下载、翻译和再发布所需的授权/许可。",
            variable=self.authorized,
            style="Card.TCheckbutton",
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            confirmation,
            text="若项目已存在，继续上次未完成的处理",
            variable=self.resume,
            style="Card.TCheckbutton",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        actions = self.actions_frame = ttk.Frame(outer, style="App.TFrame")
        actions.grid(row=5, column=0, sticky="ew", padx=24, pady=(12, 10))
        self.start_button = ttk.Button(
            actions,
            text="开始本地化",
            style="Primary.TButton",
            command=self._start,
        )
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(
            actions,
            text="停止任务",
            style="Danger.TButton",
            command=self._stop,
            state="disabled",
        )
        self.stop_button.pack(side="left", padx=(8, 0))
        ttk.Button(
            actions,
            text="调整处理设置",
            style="Secondary.TButton",
            command=self._show_settings,
        ).pack(side="right")

        status_card = ttk.Frame(outer, style="Card.TFrame", padding=(14, 10))
        status_card.grid(row=6, column=0, sticky="ew", padx=24, pady=(0, 10))
        self.status_card = status_card
        status_card.columnconfigure(1, weight=1)
        self.status_dot = tk.Label(
            status_card,
            text="●",
            background=SURFACE,
            foreground=MUTED,
            font=("Segoe UI Symbol", 10),
        )
        self.status_dot.grid(row=0, column=0, sticky="w", padx=(0, 7))
        ttk.Label(status_card, textvariable=self.status, style="Card.TLabel").grid(
            row=0, column=1, sticky="w"
        )
        self.log_button = ttk.Button(
            status_card,
            text="显示运行记录",
            style="Toolbar.TButton",
            command=self._toggle_log,
        )
        self.log_button.grid(row=0, column=2, sticky="e")
        self.progress = ttk.Progressbar(
            status_card, style="Accent.Horizontal.TProgressbar", mode="determinate", maximum=100
        )
        self.progress.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))

        log_card = self.log_card = ttk.Frame(outer, style="Card.TFrame", padding=(18, 10, 18, 14))
        log_card.grid(row=7, column=0, sticky="nsew", padx=24, pady=(0, 16))
        log_card.rowconfigure(1, weight=1)
        log_card.columnconfigure(0, weight=1)
        ttk.Label(log_card, text="运行记录", style="SectionTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        ttk.Button(log_card, text="清空", style="Secondary.TButton", command=self._clear_log).grid(
            row=0, column=1, sticky="e", pady=(0, 8)
        )
        self.log = scrolledtext.ScrolledText(
            log_card,
            height=7,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
            background=LOG_BACKGROUND,
            foreground=LOG_TEXT,
            insertbackground=TEXT,
            selectbackground=PRIMARY,
            borderwidth=1,
            highlightthickness=0,
            relief="flat",
            padx=12,
            pady=10,
        )
        self.log.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.settings_panel.grid_remove()
        self.api_frame.grid_remove()
        self.log_card.grid_remove()
        self.paste_button.focus_set()

    def _update_input_state(self, *_args: object) -> None:
        has_input = bool(self.input_value.get().strip())
        task_frames = (
            self.input_frame,
            self.confirmation_frame,
            self.actions_frame,
            self.status_card,
        )
        if has_input:
            self.empty_state.grid_remove()
            for frame in task_frames:
                frame.grid()
            if self.settings_visible:
                self.settings_panel.grid()
            else:
                self.settings_panel.grid_remove()
            if self.log_visible:
                self.log_card.grid()
            else:
                self.log_card.grid_remove()
            self.input_entry.focus_set()
        else:
            for frame in task_frames:
                frame.grid_remove()
            self.log_card.grid_remove()
            if self.settings_visible:
                self.empty_state.grid_remove()
                self.settings_panel.grid()
            else:
                self.settings_panel.grid_remove()
                self.empty_state.grid()

        provider = TRANSLATION_MODES[self.translation_label.get()]
        automatic = provider == "openai-compatible"
        if self.settings_visible and automatic:
            self.api_frame.grid()
        else:
            self.api_frame.grid_remove()
        if has_input:
            self._update_translation_fields()

    def _toggle_settings(self) -> None:
        self.settings_visible = not self.settings_visible
        if self.settings_visible:
            self.log_visible = False
            self.log_button.configure(text="显示运行记录")
        self.settings_button.configure(text="收起设置" if self.settings_visible else "处理设置")
        self._update_input_state()

    def _show_settings(self) -> None:
        if not self.settings_visible:
            self._toggle_settings()

    def _toggle_log(self) -> None:
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.settings_visible = False
            self.settings_button.configure(text="处理设置")
        self.log_button.configure(text="隐藏运行记录" if self.log_visible else "显示运行记录")
        self._update_input_state()

    def _show_log(self) -> None:
        if not self.log_visible:
            self.log_visible = True
            self.log_button.configure(text="隐藏运行记录")
        self.settings_visible = False
        self.settings_button.configure(text="处理设置")
        self._update_input_state()

    def _clear_input(self) -> None:
        if (self.process and self.process.poll() is None) or (
            self.worker and self.worker.is_alive()
        ):
            messagebox.showinfo("任务进行中", "请先停止当前任务，再移除视频。", parent=self.root)
            return
        self.input_value.set("")
        self.authorized.set(False)

    def _paste(self) -> None:
        try:
            value = self.root.clipboard_get().strip()
        except tk.TclError:
            messagebox.showinfo("剪贴板为空", "请先复制 YouTube 链接。", parent=self.root)
            return
        self.input_value.set(value)
        self.input_entry.icursor("end")

    def _choose_local_file(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            parent=self.root,
            title="选择本地视频",
            filetypes=[
                ("视频文件", "*.mp4 *.mkv *.mov *.webm *.avi *.m4v"),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.input_value.set(path)

    def _choose_output_directory(self) -> None:
        from tkinter import filedialog

        initial = self.output_directory.get().strip() or str(default_output_directory())
        path = filedialog.askdirectory(
            parent=self.root,
            title="选择项目输出文件夹",
            initialdir=initial,
            mustexist=False,
        )
        if path:
            self.output_directory.set(path)

    def _select_subtitle_font_size(self, _event: object | None = None) -> None:
        selected = self.font_size_label.get()
        if selected in SUBTITLE_FONT_SIZES:
            self.subtitle_font_size_value.set(SUBTITLE_FONT_SIZES[selected])

    def _apply_subtitle_layout(self, x_percent: int, y_percent: int, font_size: int) -> None:
        x_percent, y_percent, font_size = clamp_subtitle_preview_values(
            x_percent, y_percent, font_size
        )
        self.subtitle_position_x.set(x_percent)
        self.subtitle_position_y.set(y_percent)
        self.subtitle_font_size_value.set(font_size)
        matching_label = next(
            (label for label, value in SUBTITLE_FONT_SIZES.items() if value == font_size),
            f"自定义（{font_size}）",
        )
        self.font_size_label.set(matching_label)
        values = list(SUBTITLE_FONT_SIZES)
        if matching_label not in values:
            values.append(matching_label)
        self.font_size_combo.configure(values=values)

    def _show_subtitle_preview(self) -> None:
        subtitle_mode = SUBTITLE_MODES[self.subtitle_label.get()]
        if subtitle_mode == "download_only":
            messagebox.showinfo("无需字幕预览", "当前为无字幕下载模式。", parent=self.root)
            return
        SubtitlePreviewDialog(
            self.root,
            subtitle_mode=subtitle_mode,
            x_percent=self.subtitle_position_x.get(),
            y_percent=self.subtitle_position_y.get(),
            font_size=self.subtitle_font_size_value.get(),
            on_apply=self._apply_subtitle_layout,
        )

    def _update_translation_fields(self) -> None:
        subtitle_mode = SUBTITLE_MODES[self.subtitle_label.get()]
        provider = TRANSLATION_MODES[self.translation_label.get()]
        download_only = subtitle_mode == "download_only"
        selection_state = "disabled" if download_only else "readonly"
        self.direction_combo.configure(state=selection_state)
        self.font_size_combo.configure(state=selection_state)
        self.preview_button.configure(state="disabled" if download_only else "normal")
        self.translation_combo.configure(state=selection_state)
        for combo in (
            self.output_quality_combo,
            self.output_fps_combo,
            self.output_height_combo,
        ):
            combo.configure(state=selection_state)
        self.start_button.configure(text="开始下载" if download_only else "开始本地化")
        self.mode_hint.set(mode_description(subtitle_mode, provider))
        if download_only:
            summary = "当前方案：最高源画质 · 最高源帧率 · 最佳音频 · 不生成字幕"
        else:
            provider_names = {
                "manual": "人工翻译",
                "offline": "本地快速翻译",
                "ollama": "本地 AI 段落翻译",
                "openai-compatible": "API 自动翻译",
            }
            summary = (
                f"当前方案：{self.direction_label.get()} · {self.subtitle_label.get()} · "
                f"{provider_names[provider]} · 自动硬件加速 · {self.output_quality_label.get()}"
            )
        queue_count = len(queue_input_values(self.input_value.get()))
        if queue_count > 1:
            summary += f" · 已排队 {queue_count} 个视频（顺序处理，安全不抢资源）"
        self.workflow_summary.set(summary)
        automatic = not download_only and provider == "openai-compatible"
        if automatic and self.settings_visible:
            self.api_frame.grid()
        else:
            self.api_frame.grid_remove()
        state = "normal" if automatic else "disabled"
        for entry in (self.endpoint_entry, self.model_entry, self.key_entry):
            entry.configure(state=state)

    def _update_output_settings(self) -> None:
        self.output_hint.set(
            "保持原始表示不降分辨率或帧率；选择 60/30 FPS 只会降低更高帧率，绝不补帧。"
        )
        self._update_output_directory_hint()
        self._update_translation_fields()

    def _update_output_directory_hint(self, *_args: object) -> None:
        raw_directory = self.output_directory.get().strip()
        if not raw_directory:
            self.output_directory_hint.set("请选择一个本地磁盘位置以保存项目和渲染文件。")
            return
        self.output_directory_hint.set(output_directory_advice(Path(raw_directory)))

    def _validate(self) -> tuple[list[list[str]], dict[str, str], str]:
        if not self.authorized.get():
            raise ValueError("开始前请确认你拥有视频或已取得所需授权。")
        subtitle_mode = SUBTITLE_MODES[self.subtitle_label.get()]
        provider = TRANSLATION_MODES[self.translation_label.get()]
        if subtitle_mode != "download_only" and (whisper_message := whisper_model_installation_message()):
            raise ValueError(whisper_message)
        values = queue_input_values(self.input_value.get())
        if not values:
            raise ValueError("请粘贴 YouTube 链接或选择本地视频文件。")
        commands = [
            build_process_command(
                value,
                subtitle_mode=subtitle_mode,
                translation_provider=provider,
                translation_direction=TRANSLATION_DIRECTIONS[self.direction_label.get()],
                subtitle_font=DEFAULT_SUBTITLE_FONT,
                subtitle_font_size=self.subtitle_font_size_value.get(),
                subtitle_position_x=self.subtitle_position_x.get(),
                subtitle_position_y=self.subtitle_position_y.get(),
                processing_profile="auto",
                output_quality=OUTPUT_QUALITIES[self.output_quality_label.get()],
                output_fps=OUTPUT_FRAME_RATES[self.output_fps_label.get()],
                output_height=OUTPUT_HEIGHTS[self.output_height_label.get()],
                output_directory=self.output_directory.get(),
                resume=self.resume.get(),
            )
            for value in values
        ]
        environment = os.environ.copy()
        if provider == "openai-compatible" and subtitle_mode != "download_only":
            endpoint = self.endpoint.get().strip()
            model = self.model.get().strip()
            api_key = self.api_key.get().strip()
            if not endpoint or not model or not api_key:
                raise ValueError("自动翻译需要填写接口地址、模型名称和 API Key。")
            environment["OPENAI_COMPATIBLE_ENDPOINT"] = endpoint
            environment["OPENAI_COMPATIBLE_MODEL"] = model
            environment["OPENAI_COMPATIBLE_API_KEY"] = api_key
        workflow = "download_only" if subtitle_mode == "download_only" else provider
        return commands, environment, workflow

    def _start(self) -> None:
        if (self.process and self.process.poll() is None) or (
            self.worker and self.worker.is_alive()
        ):
            return
        try:
            commands, environment, provider = self._validate()
        except (KeyError, ValueError) as exc:
            messagebox.showwarning("还不能开始", str(exc), parent=self.root)
            return

        self._clear_log()
        self._show_log()
        self.active_direction = TRANSLATION_DIRECTIONS[self.direction_label.get()]
        self.active_queue_index = 1
        self.active_queue_total = len(commands)
        self._append_log(
            "正在启动视频下载……\n" if provider == "download_only" else "正在启动本地化处理……\n"
        )
        if self.active_queue_total > 1:
            self._append_log(
                f"已加入 {self.active_queue_total} 个视频，将顺序处理以保护显存、CPU 和磁盘。\n\n"
            )
        self._append_log(f"项目输出位置：{self.output_directory.get().strip()}\n")
        if provider == "download_only":
            self._append_log(
                "当前为无字幕直接下载：只下载并合并最高画质视频和最高质量音频，"
                "不会运行语音识别、翻译或字幕压制。\n\n"
            )
        elif provider == "manual":
            source_name = "中文" if self.active_direction == "zh-to-en" else "英文"
            self._append_log(
                f"当前为免费模式：程序会完成下载和{source_name}字幕，然后导出等待翻译的文件。\n\n"
            )
        elif provider == "offline":
            if self.active_direction == "zh-to-en":
                self._append_log(
                    "当前为中文转英文离线模式：使用本地 Whisper 识别中文，再进行中译英。\n\n"
                )
            else:
                self._append_log(
                    "当前为英文转中文离线模式：使用本地 Whisper 识别英文，再进行英译中。\n\n"
                )
        elif provider == "ollama":
            target_name = "英文" if self.active_direction == "zh-to-en" else "简体中文"
            self._append_log(
                f"当前为本地 AI 段落翻译：会先理解完整段落，再自然翻译成{target_name}。"
                "不需要 API Key；离线安装包已内置本地模型。\n\n"
            )
        else:
            target_name = "英文" if self.active_direction == "zh-to-en" else "中文"
            self._append_log(f"当前为自动模式：完成翻译后会继续压制{target_name}字幕。\n\n")
        self._set_status("正在处理，请保持窗口打开", "active")
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(10)
        self.stop_requested = False
        self.active_provider = provider
        self._progress_value = 0.0
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.worker = threading.Thread(
            target=self._run_queue,
            args=(commands, environment, provider),
            daemon=True,
        )
        self.worker.start()

    def _run_queue(
        self,
        commands: list[list[str]],
        environment: dict[str, str],
        provider: str,
    ) -> None:
        failures = 0
        completed = 0
        total = len(commands)
        for index, command in enumerate(commands, start=1):
            if self.stop_requested:
                break
            self.events.put(("queue_item", (index, total, command[3])))
            return_code = self._run_process(command, environment)
            completed = index
            if return_code != 0:
                failures += 1
            if self.stop_requested:
                break
        self.events.put(("done", (1 if failures else 0, provider, completed, total, failures)))

    def _run_process(
        self,
        command: list[str],
        environment: dict[str, str],
    ) -> int:
        creationflags = gui_process_creationflags()
        try:
            self.process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            if self.stop_requested:
                terminate_process_tree(self.process)
            last_download_percent: float | None = None
            last_download_update = 0.0
            assert self.process.stdout is not None
            for line in self.process.stdout:
                if download := _DOWNLOAD_PROGRESS_RE.search(line):
                    percent = float(download.group(1))
                    now = time.monotonic()
                    if (
                        last_download_percent is not None
                        and percent - last_download_percent < 1.0
                        and now - last_download_update < 0.4
                    ):
                        continue
                    last_download_percent = percent
                    last_download_update = now
                self.events.put(("line", line))
            return self.process.wait()
        except OSError as exc:
            self.events.put(("line", f"\n无法启动：{exc}\n"))
            return 1

    def _stop(self) -> None:
        process = self.process
        if self.stop_requested or not process or process.poll() is not None:
            return
        if not messagebox.askyesno(
            "停止处理",
            "确定停止当前任务吗？已完成的阶段会保留，下次可继续。",
            parent=self.root,
        ):
            return
        self.stop_requested = True
        self._set_status("正在停止……")
        terminate_process_tree(process)

    def _poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "line":
                    line = str(payload)
                    self._append_log(line)
                    self._update_progress_from_output(line)
                elif event == "done":
                    return_code, provider, completed, total, failures = payload  # type: ignore[misc]
                    self._finish(
                        int(return_code),
                        str(provider),
                        completed=int(completed),
                        total=int(total),
                        failures=int(failures),
                    )
                elif event == "queue_item":
                    index, total, source = payload  # type: ignore[misc]
                    self.active_queue_index = int(index)
                    self.active_queue_total = int(total)
                    self._progress_value = 99.0 * (self.active_queue_index - 1) / self.active_queue_total
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=self._progress_value)
                    self._set_status(
                        f"任务 {self.active_queue_index}/{self.active_queue_total}：正在启动", "active"
                    )
                    self._append_log(
                        f"\n{'=' * 10} 任务 {self.active_queue_index}/{self.active_queue_total}：{source} {'=' * 10}\n"
                    )
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _update_progress_from_output(self, line: str) -> None:
        update = progress_update_from_output(line, provider=self.active_provider)
        if update is None:
            return
        value, message = update
        self.progress.stop()
        self.progress.configure(mode="determinate")
        task_progress = min(99.0, value)
        aggregate = 99.0 * (
            (self.active_queue_index - 1) + task_progress / 100
        ) / self.active_queue_total
        self._progress_value = max(self._progress_value, min(99.0, aggregate))
        self.progress.configure(value=self._progress_value)
        prefix = (
            f"任务 {self.active_queue_index}/{self.active_queue_total} · "
            if self.active_queue_total > 1
            else ""
        )
        self._set_status(prefix + message, "active")

    def _finish(
        self,
        return_code: int,
        provider: str,
        *,
        completed: int = 1,
        total: int = 1,
        failures: int = 0,
    ) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.process = None
        if self.stop_requested:
            self.stop_requested = False
            self.progress.configure(value=0)
            self._set_status("任务已停止，下次可以继续处理")
            self._append_log("\n任务已停止；已完成的阶段会保留。\n")
            return
        if return_code != 0:
            self.progress.configure(value=0)
            self._set_status(
                f"队列完成：{completed - failures}/{total} 个任务成功，请查看上方日志",
                "error",
            )
            messagebox.showerror(
                "部分任务未完成",
                f"已完成 {completed - failures}/{total} 个任务。窗口日志和所选输出文件夹内项目的 logs "
                "文件夹包含详细原因；下次启动时勾选继续处理即可续跑未完成的阶段。",
                parent=self.root,
            )
            return
        self.progress.configure(value=100)
        if provider == "download_only":
            self._set_status(f"{total} 个原视频下载完成，没有生成字幕", "success")
            messagebox.showinfo(
                "下载完成",
                f"{total} 个最高画质原视频已经保存到所选输出文件夹内项目的 source 文件夹。",
                parent=self.root,
            )
        elif provider == "manual":
            source_name = "中文" if self.active_direction == "zh-to-en" else "英文"
            target_name = "英文" if self.active_direction == "zh-to-en" else "中文"
            self._set_status(f"{total} 个任务的下载和{source_name}字幕已完成，等待人工翻译", "success")
            messagebox.showinfo(
                "第一阶段完成",
                f"{total} 个视频和{source_name}字幕已经准备好。请在所选输出文件夹内项目的 "
                "subtitles\\translation_chunks 中处理翻译文件；"
                f"导入翻译后即可压制{target_name}字幕。",
                parent=self.root,
            )
        else:
            target_name = "英文" if self.active_direction == "zh-to-en" else "中文"
            output_name = (
                "english_hardsub.mp4"
                if self.active_direction == "zh-to-en"
                else "chinese_hardsub.mp4"
            )
            self._set_status(f"本地化完成，已生成 {total} 个{target_name}字幕视频", "success")
            messagebox.showinfo(
                "本地化完成",
                f"最终视频位于所选输出文件夹内项目的 rendered\\{output_name}。已完成 {total} 个任务。",
                parent=self.root,
            )

    def _set_status(self, message: str, tone: str = "muted") -> None:
        colors = {
            "muted": MUTED,
            "active": PRIMARY,
            "success": SUCCESS,
            "error": DANGER,
        }
        self.status.set(message)
        self.status_dot.configure(foreground=colors.get(tone, MUTED))

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _open_output(self) -> None:
        output = Path(self.output_directory.get().strip() or default_output_directory()).expanduser()
        output.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(output)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(output)])
        else:
            subprocess.Popen(["xdg-open", str(output)])

    def _export_support_bundle(self) -> None:
        from tkinter import filedialog

        selected = filedialog.askdirectory(
            parent=self.root,
            title="选择需要诊断的项目文件夹",
            initialdir=self.output_directory.get().strip() or str(default_output_directory()),
            mustexist=True,
        )
        if not selected:
            return
        project = ProjectPaths(Path(selected).resolve())
        if not project.state_file.is_file():
            messagebox.showwarning(
                "不是项目文件夹",
                "请选择包含 pipeline_state.json 的项目文件夹。",
                parent=self.root,
            )
            return
        try:
            bundle = create_support_bundle(project)
        except (OSError, ValueError) as exc:
            messagebox.showerror("无法导出诊断包", str(exc), parent=self.root)
            return
        messagebox.showinfo(
            "诊断包已导出",
            f"已创建：\n{bundle}\n\n包内不含视频和字幕文本；路径、链接和凭证会被隐藏。",
            parent=self.root,
        )

    def _on_close(self) -> None:
        process_running = self.process is not None and self.process.poll() is None
        worker_running = self.worker is not None and self.worker.is_alive()
        if process_running or worker_running:
            if not messagebox.askyesno(
                "退出工具",
                "处理仍在进行。退出会停止任务，但已完成的阶段可以继续。确定退出吗？",
                parent=self.root,
            ):
                return
            self.stop_requested = True
            if self.process is not None:
                terminate_process_tree(self.process)
        self.root.destroy()


def run_gui() -> None:
    root = tk.Tk()
    LocalizerWindow(root)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
