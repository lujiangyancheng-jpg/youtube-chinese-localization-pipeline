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

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SUBTITLE_MODES = {
    "仅简体中文字幕": "chinese",
    "英文在上，中文在下": "bilingual_en_zh",
    "中文在上，英文在下": "bilingual_zh_en",
}
TRANSLATION_MODES = {
    "免费模式（处理到人工翻译）": "manual",
    "本地离线翻译并压制（无需 API）": "offline",
    "自动翻译并压制字幕（需要 API）": "openai-compatible",
}


def build_process_command(
    input_value: str,
    *,
    subtitle_mode: str,
    translation_provider: str,
    prefer_youtube_chinese: bool = True,
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
    command = [
        python_executable or sys.executable,
        str(main_script or PROJECT_ROOT / "main.py"),
        "process",
        value,
        "--subtitle-mode",
        subtitle_mode,
        "--translation-provider",
        translation_provider,
        (
            "--prefer-youtube-chinese"
            if prefer_youtube_chinese
            else "--no-prefer-youtube-chinese"
        ),
    ]
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
        self.root.title("YouTube 中文本地化工具")
        self.root.geometry("840x760")
        self.root.minsize(700, 620)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.worker: threading.Thread | None = None
        self.stop_requested = False

        endpoint, model, api_key = api_configuration(os.environ)
        default_translation = "本地离线翻译并压制（无需 API）"

        self.input_value = tk.StringVar()
        self.subtitle_label = tk.StringVar(value="仅简体中文字幕")
        self.translation_label = tk.StringVar(value=default_translation)
        self.endpoint = tk.StringVar(value=endpoint or "https://api.openai.com/v1")
        self.model = tk.StringVar(value=model)
        self.api_key = tk.StringVar(value=api_key)
        self.authorized = tk.BooleanVar(value=False)
        self.prefer_youtube_chinese = tk.BooleanVar(value=True)
        self.resume = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="等待粘贴链接")

        self._configure_style()
        self._build_layout()
        self._update_translation_fields()
        self.root.after(100, self._poll_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", font=("Segoe UI", 10))
        style.configure("Action.TButton", font=("Segoe UI", 11, "bold"), padding=(14, 8))

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, padding=22)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="YouTube 中文本地化工具", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="粘贴已获授权的公开 YouTube 视频链接，自动下载并生成字幕文件。",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(4, 18))

        input_frame = ttk.LabelFrame(outer, text="1. 视频链接", padding=12)
        input_frame.pack(fill="x")
        self.input_entry = ttk.Entry(input_frame, textvariable=self.input_value, font=("Segoe UI", 11))
        self.input_entry.pack(side="left", fill="x", expand=True, ipady=5)
        ttk.Button(input_frame, text="粘贴", command=self._paste).pack(side="left", padx=(8, 0))
        ttk.Button(input_frame, text="选择本地视频", command=self._choose_local_file).pack(
            side="left", padx=(8, 0)
        )

        options = ttk.LabelFrame(outer, text="2. 输出设置", padding=12)
        options.pack(fill="x", pady=(12, 0))
        ttk.Label(options, text="字幕样式：").grid(row=0, column=0, sticky="w", pady=4)
        subtitle_combo = ttk.Combobox(
            options,
            textvariable=self.subtitle_label,
            values=list(SUBTITLE_MODES),
            state="readonly",
            width=34,
        )
        subtitle_combo.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(options, text="翻译方式：").grid(row=1, column=0, sticky="w", pady=4)
        translation_combo = ttk.Combobox(
            options,
            textvariable=self.translation_label,
            values=list(TRANSLATION_MODES),
            state="readonly",
            width=34,
        )
        translation_combo.grid(row=1, column=1, sticky="ew", pady=4)
        translation_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_translation_fields())
        ttk.Checkbutton(
            options,
            text="优先直接使用 YouTube 提供的简体中文字幕（没有时再按上方方式翻译）",
            variable=self.prefer_youtube_chinese,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 2))
        options.columnconfigure(1, weight=1)

        self.api_frame = ttk.LabelFrame(outer, text="自动翻译 API（API Key 不会保存）", padding=12)
        self.api_frame.pack(fill="x", pady=(12, 0))
        ttk.Label(self.api_frame, text="接口地址：").grid(row=0, column=0, sticky="w", pady=3)
        self.endpoint_entry = ttk.Entry(self.api_frame, textvariable=self.endpoint)
        self.endpoint_entry.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(self.api_frame, text="模型名称：").grid(row=1, column=0, sticky="w", pady=3)
        self.model_entry = ttk.Entry(self.api_frame, textvariable=self.model)
        self.model_entry.grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(self.api_frame, text="API Key：").grid(row=2, column=0, sticky="w", pady=3)
        self.key_entry = ttk.Entry(self.api_frame, textvariable=self.api_key, show="●")
        self.key_entry.grid(row=2, column=1, sticky="ew", pady=3)
        self.api_frame.columnconfigure(1, weight=1)

        confirmation = ttk.Frame(outer)
        confirmation.pack(fill="x", pady=(12, 4))
        ttk.Checkbutton(
            confirmation,
            text="我确认拥有该视频，或已取得下载、翻译和再发布所需的授权/许可。",
            variable=self.authorized,
        ).pack(anchor="w")
        ttk.Checkbutton(
            confirmation,
            text="若项目已存在，继续上次未完成的处理",
            variable=self.resume,
        ).pack(anchor="w", pady=(4, 0))

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(10, 8))
        self.start_button = ttk.Button(
            actions,
            text="开始本地化",
            style="Action.TButton",
            command=self._start,
        )
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(actions, text="停止", command=self._stop, state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="打开输出文件夹", command=self._open_output).pack(side="right")

        status_row = ttk.Frame(outer)
        status_row.pack(fill="x", pady=(2, 6))
        ttk.Label(status_row, text="状态：").pack(side="left")
        ttk.Label(status_row, textvariable=self.status).pack(side="left")

        self.log = scrolledtext.ScrolledText(
            outer,
            height=15,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
        )
        self.log.pack(fill="both", expand=True)
        self.input_entry.focus_set()

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
        automatic = TRANSLATION_MODES[self.translation_label.get()] == "openai-compatible"
        state = "normal" if automatic else "disabled"
        for entry in (self.endpoint_entry, self.model_entry, self.key_entry):
            entry.configure(state=state)

    def _validate(self) -> tuple[list[str], dict[str, str], str]:
        if not self.authorized.get():
            raise ValueError("开始前请确认你拥有视频或已取得所需授权。")
        provider = TRANSLATION_MODES[self.translation_label.get()]
        command = build_process_command(
            self.input_value.get(),
            subtitle_mode=SUBTITLE_MODES[self.subtitle_label.get()],
            translation_provider=provider,
            prefer_youtube_chinese=self.prefer_youtube_chinese.get(),
            resume=self.resume.get(),
        )
        environment = os.environ.copy()
        if provider == "openai-compatible":
            endpoint = self.endpoint.get().strip()
            model = self.model.get().strip()
            api_key = self.api_key.get().strip()
            if not endpoint or not model or not api_key:
                raise ValueError("自动翻译需要填写接口地址、模型名称和 API Key。")
            environment["OPENAI_COMPATIBLE_ENDPOINT"] = endpoint
            environment["OPENAI_COMPATIBLE_MODEL"] = model
            environment["OPENAI_COMPATIBLE_API_KEY"] = api_key
        return command, environment, provider

    def _start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        try:
            command, environment, provider = self._validate()
        except (KeyError, ValueError) as exc:
            messagebox.showwarning("还不能开始", str(exc), parent=self.root)
            return

        self._clear_log()
        self._append_log("正在启动本地化处理……\n")
        if provider == "manual":
            self._append_log(
                "当前为免费模式：程序会完成下载和英文字幕，然后导出等待翻译的文件。\n\n"
            )
        elif provider == "offline":
            self._append_log(
                "当前为本地离线模式：优先使用 YouTube 中文字幕；如需翻译，首次会下载本地模型。\n\n"
            )
        else:
            self._append_log("当前为自动模式：完成翻译后会继续压制中文字幕。\n\n")
        self.status.set("正在处理，请保持窗口打开")
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
        self.status.set("正在停止……")
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
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.process = None
        if self.stop_requested:
            self.stop_requested = False
            self.status.set("任务已停止，下次可以继续处理")
            self._append_log("\n任务已停止；已完成的阶段会保留。\n")
            return
        if return_code != 0:
            self.status.set("处理失败，请查看上方日志")
            messagebox.showerror(
                "处理未完成",
                "任务没有完成。窗口日志和 output 项目内的 logs 文件夹包含详细原因。",
                parent=self.root,
            )
            return
        if provider == "manual":
            self.status.set("下载和英文字幕已完成，等待人工翻译")
            messagebox.showinfo(
                "第一阶段完成",
                "视频和英文字幕已经准备好。请在 output 项目的 subtitles\\translation_chunks "
                "中处理翻译文件；导入翻译后即可压制中文字幕。",
                parent=self.root,
            )
        else:
            self.status.set("本地化完成，中文字幕视频已生成")
            messagebox.showinfo(
                "本地化完成",
                "最终视频位于 output 项目的 rendered\\chinese_hardsub.mp4。",
                parent=self.root,
            )

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
