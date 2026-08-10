from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from collections.abc import Mapping
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from .resources import ollama_executable

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
SUBTITLE_FONTS = {
    "Noto Sans CJK SC（现代无衬线，推荐）": "Noto Sans CJK SC",
    "Noto Serif CJK SC（典雅宋体）": "Noto Serif CJK SC",
    "霞鹜文楷（自然手写）": "LXGW WenKai",
    "微软雅黑（系统字体）": "Microsoft YaHei",
}


PROCESSING_PROFILES = {
    "快速（更少等待，适合预览）": "fast",
    "均衡（推荐，GPU 编码优先）": "balanced",
    "精品（更细致的识别与成片）": "quality",
    "CPU 安全（低压力，避免占满电脑）": "safe_cpu",
}


def local_ai_available() -> bool:
    return ollama_executable() is not None


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


def profile_description(profile: str) -> str:
    descriptions = {
        "fast": "快速：Small Whisper、快速识别、优先使用显卡编码；适合先出结果。",
        "balanced": "均衡：Medium Whisper、稳定断句、优先使用显卡编码；适合大多数视频。",
        "quality": "精品：Medium Whisper 加强搜索与更高码率成片；更慢，但更适合正式发布。",
        "safe_cpu": "CPU 安全：限制为低压力 CPU 处理，不会与其他显卡任务争抢资源。",
    }
    return descriptions.get(profile, "选择性能预设后即可开始。")


def build_process_command(
    input_value: str,
    *,
    subtitle_mode: str,
    translation_provider: str,
    translation_direction: str = "en-to-zh",
    subtitle_font: str = "Noto Sans CJK SC",
    processing_profile: str | None = None,
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
    if processing_profile is not None and processing_profile not in PROCESSING_PROFILES.values():
        raise ValueError("Unknown processing profile.")
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
    if processing_profile:
        command.extend(["--processing-profile", processing_profile])
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
        self.font_label = tk.StringVar(value="Noto Sans CJK SC（现代无衬线，推荐）")
        self.profile_label = tk.StringVar(value="均衡（推荐，GPU 编码优先）")
        self.endpoint = tk.StringVar(value=endpoint or "https://api.openai.com/v1")
        self.model = tk.StringVar(value=model)
        self.api_key = tk.StringVar(value=api_key)
        self.authorized = tk.BooleanVar(value=False)
        self.resume = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="等待粘贴链接")
        self.mode_hint = tk.StringVar()
        self.profile_hint = tk.StringVar()
        self.workflow_summary = tk.StringVar()
        self.settings_visible = False
        self.log_visible = False

        self._configure_style()
        self._build_layout()
        self._update_translation_fields()
        self._update_processing_profile()
        self.input_value.trace_add("write", self._update_input_state)
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
            text="添加一个视频链接",
            background=APP_BACKGROUND,
            foreground=TEXT,
            font=(UI_FONT, 16, "bold"),
        ).pack()
        ttk.Label(
            empty_content,
            text="复制 YouTube 链接，然后点击上方“粘贴链接”",
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
        ttk.Label(options, text="字幕字体", style="Field.TLabel").grid(
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
        self.font_combo = ttk.Combobox(
            options,
            textvariable=self.font_label,
            values=list(SUBTITLE_FONTS),
            state="readonly",
            style="Modern.TCombobox",
        )
        self.font_combo.grid(row=1, column=3, sticky="ew", padx=(6, 0))
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
            row=2, column=0, columnspan=4, sticky="w", pady=(9, 0)
        )

        ttk.Label(options, text="性能与画质", style="Field.TLabel").grid(
            row=3, column=0, sticky="w", pady=(12, 5), padx=(0, 6)
        )
        self.profile_combo = ttk.Combobox(
            options,
            textvariable=self.profile_label,
            values=list(PROCESSING_PROFILES),
            state="readonly",
            style="Modern.TCombobox",
        )
        self.profile_combo.grid(row=3, column=1, columnspan=2, sticky="ew", padx=6)
        self.profile_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._update_processing_profile()
        )
        ttk.Label(options, textvariable=self.profile_hint, style="Muted.TLabel").grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(5, 0)
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
        if self.process and self.process.poll() is None:
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

    def _update_translation_fields(self) -> None:
        subtitle_mode = SUBTITLE_MODES[self.subtitle_label.get()]
        provider = TRANSLATION_MODES[self.translation_label.get()]
        download_only = subtitle_mode == "download_only"
        selection_state = "disabled" if download_only else "readonly"
        self.direction_combo.configure(state=selection_state)
        self.font_combo.configure(state=selection_state)
        self.translation_combo.configure(state=selection_state)
        self.start_button.configure(text="开始下载" if download_only else "开始本地化")
        self.mode_hint.set(mode_description(subtitle_mode, provider))
        if download_only:
            self.workflow_summary.set("当前方案：最高画质原视频 · 最佳音频 · 不生成字幕")
        else:
            provider_names = {
                "manual": "人工翻译",
                "offline": "本地快速翻译",
                "ollama": "本地 AI 段落翻译",
                "openai-compatible": "API 自动翻译",
            }
            self.workflow_summary.set(
                f"当前方案：{self.direction_label.get()} · {self.subtitle_label.get()} · "
                f"{provider_names[provider]} · {self.profile_label.get()}"
            )
        automatic = not download_only and provider == "openai-compatible"
        if automatic and self.settings_visible:
            self.api_frame.grid()
        else:
            self.api_frame.grid_remove()
        state = "normal" if automatic else "disabled"
        for entry in (self.endpoint_entry, self.model_entry, self.key_entry):
            entry.configure(state=state)

    def _update_processing_profile(self) -> None:
        profile = PROCESSING_PROFILES[self.profile_label.get()]
        self.profile_hint.set(profile_description(profile))
        self._update_translation_fields()

    def _validate(self) -> tuple[list[str], dict[str, str], str]:
        if not self.authorized.get():
            raise ValueError("开始前请确认你拥有视频或已取得所需授权。")
        subtitle_mode = SUBTITLE_MODES[self.subtitle_label.get()]
        provider = TRANSLATION_MODES[self.translation_label.get()]
        command = build_process_command(
            self.input_value.get(),
            subtitle_mode=subtitle_mode,
            translation_provider=provider,
            translation_direction=TRANSLATION_DIRECTIONS[self.direction_label.get()],
            subtitle_font=SUBTITLE_FONTS[self.font_label.get()],
            processing_profile=PROCESSING_PROFILES[self.profile_label.get()],
            resume=self.resume.get(),
        )
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
        return command, environment, workflow

    def _start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        try:
            command, environment, provider = self._validate()
        except (KeyError, ValueError) as exc:
            messagebox.showwarning("还不能开始", str(exc), parent=self.root)
            return

        self._clear_log()
        self._show_log()
        self.active_direction = TRANSLATION_DIRECTIONS[self.direction_label.get()]
        self._append_log(
            "正在启动视频下载……\n" if provider == "download_only" else "正在启动本地化处理……\n"
        )
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
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.worker = threading.Thread(
            target=self._run_process,
            args=(command, environment, provider),
            daemon=True,
        )
        self.worker.start()

    def _run_process(
        self,
        command: list[str],
        environment: dict[str, str],
        provider: str,
    ) -> None:
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
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
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.events.put(("line", line))
            return_code = self.process.wait()
            self.events.put(("done", (return_code, provider)))
        except OSError as exc:
            self.events.put(("error", str(exc)))

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
                    self._append_log(str(payload))
                elif event == "done":
                    return_code, provider = payload  # type: ignore[misc]
                    self._finish(int(return_code), str(provider))
                elif event == "error":
                    self._append_log(f"\n无法启动：{payload}\n")
                    self._finish(1, "")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _finish(self, return_code: int, provider: str) -> None:
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
            self._set_status("处理失败，请查看上方日志", "error")
            messagebox.showerror(
                "处理未完成",
                "任务没有完成。窗口日志和 output 项目内的 logs 文件夹包含详细原因。",
                parent=self.root,
            )
            return
        self.progress.configure(value=100)
        if provider == "download_only":
            self._set_status("原视频下载完成，没有生成字幕", "success")
            messagebox.showinfo(
                "下载完成",
                "最高画质原视频已经保存到 output 项目的 source 文件夹。",
                parent=self.root,
            )
        elif provider == "manual":
            source_name = "中文" if self.active_direction == "zh-to-en" else "英文"
            target_name = "英文" if self.active_direction == "zh-to-en" else "中文"
            self._set_status(f"下载和{source_name}字幕已完成，等待人工翻译", "success")
            messagebox.showinfo(
                "第一阶段完成",
                f"视频和{source_name}字幕已经准备好。请在 output 项目的 "
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
            self._set_status(f"本地化完成，{target_name}字幕视频已生成", "success")
            messagebox.showinfo(
                "本地化完成",
                f"最终视频位于 output 项目的 rendered\\{output_name}。",
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
        output = PROJECT_ROOT / "output"
        output.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(output)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(output)])
        else:
            subprocess.Popen(["xdg-open", str(output)])

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
