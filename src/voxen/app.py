from __future__ import annotations

import queue
import time
import math
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from pathlib import Path
import sys

from .audio import AudioRecorder
from .config import AppConfig, ConfigStore
from .hotkey import GlobalHotkey
from .injector import ClipboardInjector
from .processing import ProcessingOptions, TextProcessor
from .stt import FasterWhisperEngine
from .tray import SystemTray


class VoxenApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Voxen")
        self.root.geometry("560x520")
        self.root.minsize(500, 460)
        self.root.configure(bg="#11161b")

        self.store = ConfigStore()
        self.first_launch = not self.store.path.exists()
        self.config = self.store.load()
        self.recorder = AudioRecorder(self.config.sample_rate, self.config.preroll_ms)
        self.processor = TextProcessor()
        self.injector = ClipboardInjector()
        self.engine: FasterWhisperEngine | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voxen-stt")
        self.recording = False
        self.busy = False
        self.paused = False
        self.audio_ready = False
        self.hotkey: GlobalHotkey | None = None
        self.tray: SystemTray | None = None

        self.status_var = tk.StringVar(value="Starting Voxen...")
        self.detail_var = tk.StringVar(value="Local transcription, ready when you are.")
        self.hotkey_var = tk.StringVar(value=self.config.hotkey)
        self.model_var = tk.StringVar(value=self.config.model)
        self.language_var = tk.StringVar(value=self.config.language)
        self.auto_paste_var = tk.BooleanVar(value=self.config.auto_paste)
        self.punctuation_var = tk.BooleanVar(value=self.config.punctuation)
        self.hotkey_button_var = tk.StringVar(value=self._format_hotkey(self.config.hotkey))
        self.hotkey_hint_var = tk.StringVar(value="Click the button, then press your key combination")
        self.hotkey_capture_keys: set[str] = set()
        self.hotkey_capture_binding: str | None = None
        self.capturing_hotkey = False
        self.model_combo: ttk.Combobox | None = None
        self.language_combo: ttk.Combobox | None = None
        self.overlay: tk.Toplevel | None = None
        self.overlay_var = tk.StringVar(value="Listening  •  00:00")
        self.overlay_hint_var = tk.StringVar(value="Release when you are done")
        self.overlay_level_var = tk.StringVar(value="MIC ACTIVE")
        self.overlay_canvas: tk.Canvas | None = None
        self.overlay_animation_id: str | None = None
        self.overlay_phase = 0.0
        self.overlay_mode = "listening"
        self.started_at = 0.0

        self._build_ui()
        self._build_overlay()
        self.root.withdraw()
        self._start_services()
        self.root.after(100, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._hide_settings)

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        self.combo_popup_font = tkfont.Font(self.root, family="Segoe UI", size=10)
        self.root.option_add("*TCombobox*Listbox.background", "#24353d")
        self.root.option_add("*TCombobox*Listbox.foreground", "#f1f7f4")
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#72e0ae")
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#102019")
        self.root.option_add("*TCombobox*Listbox.font", str(self.combo_popup_font))
        style.configure(
            "Voxen.TCombobox",
            fieldbackground="#24353d",
            background="#24353d",
            foreground="#f1f7f4",
            arrowcolor="#72e0ae",
            bordercolor="#527080",
            lightcolor="#527080",
            darkcolor="#11181e",
            padding=(10, 7),
            arrowsize=15,
            font=("Segoe UI", 10),
        )
        style.map(
            "Voxen.TCombobox",
            fieldbackground=[("readonly", "#24353d"), ("active", "#2e4650")],
            foreground=[("readonly", "#f1f7f4")],
            selectbackground=[("readonly", "#72e0ae")],
            selectforeground=[("readonly", "#102019")],
        )
        style.configure("Voxen.TCheckbutton", background="#11181e", foreground="#b8c7cf", font=("Segoe UI", 9))

        container = tk.Frame(self.root, bg="#11181e")
        container.pack(fill="both", expand=True)
        content = tk.Frame(container, bg="#11181e")
        content.pack(fill="both", expand=True, padx=30, pady=28)

        header = tk.Frame(content, bg="#11181e")
        header.pack(fill="x")
        try:
            from PIL import Image, ImageTk
            asset_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
            brand_image = Image.open(asset_root / "assets" / "voxen-mark.png").resize((42, 42), Image.Resampling.LANCZOS)
            self.brand_photo = ImageTk.PhotoImage(brand_image)
            brand = tk.Label(header, image=self.brand_photo, bg="#11181e", borderwidth=0)
        except (ImportError, FileNotFoundError):
            brand = tk.Canvas(header, width=42, height=42, bg="#11181e", highlightthickness=0)
            brand.create_oval(3, 3, 39, 39, fill="#72e0ae", outline="")
            brand.create_oval(14, 14, 28, 28, fill="#11181e", outline="")
        brand.pack(side="left", padx=(0, 12))
        title_block = tk.Frame(header, bg="#11181e")
        title_block.pack(side="left")
        tk.Label(title_block, text="Voxen", bg="#11181e", fg="#f1f7f4", font=("Segoe UI", 25, "bold")).pack(anchor="w")
        tk.Label(title_block, text="Your voice, anywhere you type", bg="#11181e", fg="#81909b", font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(header, text="LOCAL MODE", bg="#163027", fg="#72e0ae", font=("Segoe UI", 8, "bold"), padx=10, pady=5).pack(side="right", anchor="n", pady=4)

        status_card = tk.Frame(content, bg="#14241f", highlightbackground="#28483a", highlightthickness=1)
        status_card.pack(fill="x", pady=(18, 12))
        status_inner = tk.Frame(status_card, bg="#14241f")
        status_inner.pack(fill="x", padx=14, pady=10)
        status_indicator = tk.Canvas(status_inner, width=14, height=14, bg="#14241f", highlightthickness=0)
        status_indicator.pack(side="left", padx=(0, 8))
        status_indicator.create_oval(2, 2, 12, 12, fill="#72e0ae", outline="")
        status_text = tk.Frame(status_inner, bg="#14241f")
        status_text.pack(side="left", fill="x", expand=True)
        tk.Label(status_text, textvariable=self.status_var, bg="#14241f", fg="#72e0ae", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(status_text, textvariable=self.detail_var, bg="#14241f", fg="#9db2a8", font=("Segoe UI", 8)).pack(anchor="w", pady=(1, 0))
        tk.Label(status_inner, textvariable=self.hotkey_var, bg="#14241f", fg="#78958a", font=("Consolas", 8, "bold")).pack(side="right")

        controls = tk.Frame(content, bg="#17232b", highlightbackground="#263843", highlightthickness=1)
        controls.pack(fill="x", pady=(0, 18))
        controls.columnconfigure(1, weight=1)
        tk.Label(controls, text="QUICK SETTINGS", bg="#17232b", fg="#72e0ae", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 8))
        tk.Label(controls, text="Hotkey", bg="#17232b", fg="#a7b7bf", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", padx=16, pady=5)
        hotkey_area = tk.Frame(controls, bg="#17232b")
        hotkey_area.grid(row=1, column=1, sticky="ew", padx=(20, 16), pady=5)
        hotkey_area.columnconfigure(0, weight=1)
        self.hotkey_button = tk.Button(hotkey_area, textvariable=self.hotkey_button_var, command=self._start_hotkey_capture, bg="#25343d", fg="#e2ece9", activebackground="#334b57", activeforeground="#ffffff", relief="flat", cursor="hand2", font=("Consolas", 10, "bold"), padx=12, pady=7)
        self.hotkey_button.grid(row=0, column=0, sticky="ew")
        tk.Label(hotkey_area, textvariable=self.hotkey_hint_var, bg="#17232b", fg="#6f838e", font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=(4, 0))
        for row, label, variable, values, attribute in (
            (2, "Model", self.model_var, ("tiny", "base", "small"), "model_combo"),
            (3, "Language", self.language_var, ("auto", "it", "en", "ja", "fr", "de", "es"), "language_combo"),
        ):
            tk.Label(controls, text=label, bg="#17232b", fg="#a7b7bf", font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", padx=16, pady=5)
            combo = ttk.Combobox(
                controls,
                textvariable=variable,
                values=values,
                state="readonly",
                takefocus=True,
                style="Voxen.TCombobox",
            )
            combo.bind("<<ComboboxSelected>>", self._on_combo_selected)
            setattr(self, attribute, combo)
            combo.grid(row=row, column=1, sticky="ew", padx=(20, 16), pady=5)
        ttk.Checkbutton(controls, text="Paste into active app", variable=self.auto_paste_var, style="Voxen.TCheckbutton").grid(row=4, column=0, sticky="w", padx=16, pady=(9, 14))
        ttk.Checkbutton(controls, text="Final punctuation", variable=self.punctuation_var, style="Voxen.TCheckbutton").grid(row=4, column=1, sticky="w", padx=(20, 16), pady=(9, 14))

        actions = tk.Frame(content, bg="#11181e")
        actions.pack(fill="x", pady=(16, 0))
        tk.Button(actions, text="SAVE SETTINGS", command=self._save_settings, bg="#72e0ae", fg="#102019", activebackground="#9af0c5", activeforeground="#102019", relief="flat", cursor="hand2", font=("Segoe UI", 9, "bold"), padx=15, pady=8).pack(side="left")
        tk.Label(content, text="Voxen stays local  ·  model downloads only on first use", bg="#11181e", fg="#62727d", font=("Segoe UI", 8)).pack(anchor="w", pady=(13, 0))

    @staticmethod
    def _format_hotkey(hotkey: str) -> str:
        return " + ".join(part.strip().upper() for part in hotkey.split("+") if part.strip())

    def _on_combo_selected(self, _event: tk.Event) -> None:
        self.detail_var.set("Selection updated. Click SAVE SETTINGS to keep it.")

    def _start_hotkey_capture(self) -> None:
        if self.hotkey is not None:
            self.hotkey.stop()
        self.hotkey_capture_keys = set()
        self.capturing_hotkey = True
        self.hotkey_button_var.set("PRESS YOUR COMBINATION")
        self.hotkey_hint_var.set("For example: hold Ctrl and press Space")
        self.hotkey_button.configure(bg="#d9a441", fg="#1e1910", activebackground="#f0c86b", activeforeground="#1e1910")
        self.hotkey_button.focus_set()
        self.hotkey_capture_binding = self.hotkey_button.bind("<KeyPress>", self._capture_hotkey, add="+")

    def _capture_hotkey(self, event) -> str:
        key = event.keysym.lower()
        modifier_names = {
            "control_l": "ctrl",
            "control_r": "ctrl",
            "shift_l": "shift",
            "shift_r": "shift",
            "alt_l": "alt",
            "alt_r": "alt",
            "win_l": "win",
            "win_r": "win",
        }
        modifier = modifier_names.get(key)
        if modifier is not None:
            self.hotkey_capture_keys.add(modifier)
            return "break"
        key_names = {"return": "enter", "escape": "esc", "prior": "pageup", "next": "pagedown"}
        key = key_names.get(key, key)
        order = ("ctrl", "alt", "shift", "win")
        parts = [name for name in order if name in self.hotkey_capture_keys]
        parts.append(key)
        self.hotkey_var.set("+".join(parts))
        self.hotkey_button_var.set(self._format_hotkey(self.hotkey_var.get()))
        self.hotkey_hint_var.set("Hotkey updated. Save settings to keep it.")
        self._finish_hotkey_capture()
        return "break"

    def _finish_hotkey_capture(self) -> None:
        self.capturing_hotkey = False
        if self.hotkey_capture_binding is not None:
            self.hotkey_button.unbind("<KeyPress>", self.hotkey_capture_binding)
            self.hotkey_capture_binding = None
        self.hotkey_button.configure(bg="#25343d", fg="#e2ece9", activebackground="#334b57", activeforeground="#ffffff")
        try:
            self._restart_hotkey(self.hotkey_var.get())
        except (RuntimeError, ValueError) as exc:
            self.detail_var.set(str(exc))

    def _restart_hotkey(self, hotkey: str) -> None:
        if self.hotkey is not None:
            self.hotkey.stop()
        self.hotkey = GlobalHotkey(hotkey, self._request_recording_start, self._request_recording_stop)
        self.hotkey.start()

    def _build_overlay(self) -> None:
        self.overlay = tk.Toplevel(self.root)
        self.overlay.withdraw()
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg="#0f191d")
        shell = tk.Frame(self.overlay, bg="#16252a", highlightbackground="#31544b", highlightthickness=1)
        shell.pack(padx=2, pady=2)
        header = tk.Frame(shell, bg="#16252a")
        header.pack(fill="x", padx=15, pady=(12, 2))
        mic = tk.Canvas(header, width=22, height=22, bg="#16252a", highlightthickness=0)
        mic.pack(side="left", padx=(0, 9))
        mic.create_oval(3, 3, 19, 19, fill="#72e0ae", outline="")
        mic.create_oval(8, 8, 14, 14, fill="#16252a", outline="")
        tk.Label(header, textvariable=self.overlay_var, bg="#16252a", fg="#f1f8f5", font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(header, textvariable=self.overlay_level_var, bg="#16252a", fg="#72e0ae", font=("Consolas", 8, "bold")).pack(side="right")
        self.overlay_canvas = tk.Canvas(shell, width=300, height=38, bg="#16252a", highlightthickness=0)
        self.overlay_canvas.pack(padx=15, pady=(5, 2))
        tk.Label(shell, textvariable=self.overlay_hint_var, bg="#16252a", fg="#91a9a5", font=("Segoe UI", 8)).pack(anchor="w", padx=18, pady=(0, 12))

    def _start_services(self) -> None:
        try:
            self.recorder.start()
            self.audio_ready = True
            self.status_var.set("Ready")
        except RuntimeError as exc:
            self.detail_var.set(str(exc))
        try:
            self.hotkey = GlobalHotkey(self.config.hotkey, self._request_recording_start, self._request_recording_stop)
            self.hotkey.start()
            if self.audio_ready:
                self.detail_var.set(f"Hold {self.config.hotkey} to dictate.")
        except RuntimeError as exc:
            self.detail_var.set(str(exc))
        try:
            self.tray = SystemTray(
                self._request_show_settings,
                self._request_toggle_pause,
                self._request_quit,
            )
            self.tray.start()
        except RuntimeError as exc:
            self._show_settings()
            self.detail_var.set(str(exc))
        self._show_settings()
        self.executor.submit(self._warm_engine)

    def _warm_engine(self) -> None:
        try:
            self.engine = FasterWhisperEngine(
                self.config.model,
                self.config.device,
                self.config.compute_type,
            )
            self.engine.load()
            self.events.put(("engine_ready", None))
        except Exception as exc:
            self.events.put(("model_error", str(exc)))

    def _request_show_settings(self) -> None:
        self.root.after(0, self._show_settings)

    def _request_toggle_pause(self) -> None:
        self.root.after(0, self._toggle_pause)

    def _request_quit(self) -> None:
        self.root.after(0, self.close)

    def _show_settings(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _hide_settings(self) -> None:
        if self.capturing_hotkey:
            self._cancel_hotkey_capture()
        self.root.withdraw()

    def _toggle_pause(self) -> None:
        if self.recording:
            self._stop_recording()
        self.paused = not self.paused
        self.status_var.set("Paused" if self.paused else "Ready")
        self.detail_var.set("Resume from the Voxen tray icon." if self.paused else f"Hold {self.config.hotkey} to dictate.")

    def _request_recording_start(self) -> None:
        self.root.after(0, self._start_recording)

    def _request_recording_stop(self) -> None:
        self.root.after(0, self._stop_recording)

    def _start_recording(self) -> None:
        if self.paused or not self.audio_ready or self.recording or self.busy:
            return
        self.recorder.begin()
        self.recording = True
        self.started_at = time.monotonic()
        self.status_var.set("Listening...")
        self.detail_var.set("Release the hotkey when you finish speaking.")
        self.overlay_var.set("Listening  •  00:00")
        self.overlay_hint_var.set("Release when you are done speaking")
        self.overlay_level_var.set("MIC ACTIVE")
        self.overlay_mode = "listening"
        self._show_overlay()
        self._update_overlay_clock()

    def _stop_recording(self) -> None:
        if not self.recording:
            return
        self.recording = False
        audio = self.recorder.end()
        self.busy = True
        self.overlay_var.set("Processing locally  •  Whisper")
        self.overlay_hint_var.set("Turning your words into text")
        self.overlay_level_var.set("PROCESSING")
        self.overlay_mode = "processing"
        self.status_var.set("Processing...")
        self.detail_var.set("Whisper is transcribing locally.")
        self._show_overlay()
        self.executor.submit(self._transcribe, audio)

    def _transcribe(self, audio) -> None:
        try:
            if self.engine is None or self.engine.model_name != self.config.model:
                self.engine = FasterWhisperEngine(self.config.model, self.config.device, self.config.compute_type)
            raw_text = self.engine.transcribe(audio, self.config.language)
            self.events.put(("transcript", raw_text))
        except Exception as exc:  # worker errors must return to the UI thread
            self.events.put(("error", str(exc)))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "transcript":
                    self._finish_transcript(str(payload))
                elif kind == "engine_ready":
                    if not self.recording and not self.busy and not self.paused:
                        self.status_var.set("Ready")
                        self.detail_var.set(f"Hold {self.config.hotkey} to dictate.")
                elif kind == "model_error":
                    self.detail_var.set(f"Model not ready: {payload}")
                else:
                    self.busy = False
                    self._hide_overlay()
                    self.status_var.set("Error")
                    self.detail_var.set(str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _finish_transcript(self, raw_text: str) -> None:
        options = ProcessingOptions(capitalization=True, punctuation=self.config.punctuation)
        text = self.processor.process(raw_text, options)
        self.busy = False
        if not text:
            self._hide_overlay()
            self.status_var.set("Ready")
            self.detail_var.set("No speech detected.")
            return
        if self.config.auto_paste:
            try:
                self.injector.inject(text)
                self.detail_var.set("Text pasted into the active application.")
            except RuntimeError as exc:
                self.detail_var.set(str(exc))
        else:
            self.detail_var.set("Transcript ready. Automatic paste is disabled.")
        self._hide_overlay()
        self.status_var.set("Ready")

    def _update_overlay_clock(self) -> None:
        if not self.recording:
            return
        elapsed = int(time.monotonic() - self.started_at)
        self.overlay_var.set(f"Listening  •  {elapsed // 60:02d}:{elapsed % 60:02d}")
        self.root.after(250, self._update_overlay_clock)

    def _show_overlay(self) -> None:
        if self.overlay is None:
            return
        self.overlay.update_idletasks()
        width = self.overlay.winfo_width()
        height = self.overlay.winfo_height()
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, self.root.winfo_screenheight() - height - 90)
        self.overlay.geometry(f"+{x}+{y}")
        self.overlay.deiconify()
        if self.overlay_animation_id is None:
            self._animate_overlay()

    def _animate_overlay(self) -> None:
        if self.overlay is None or self.overlay_canvas is None or not self.overlay.winfo_viewable():
            self.overlay_animation_id = None
            return
        self.overlay_canvas.delete("wave")
        bar_count = 30
        center_y = 19
        for index in range(bar_count):
            wave = abs(math.sin(self.overlay_phase + index * 0.62))
            if self.overlay_mode == "processing":
                height = 4 + wave * 7
                color = "#55a98a"
            else:
                level = max(0.18, self.recorder.level)
                height = 4 + wave * (7 + level * 16)
                color = "#72e0ae" if index % 3 else "#b5f4d4"
            x = 5 + index * 10
            self.overlay_canvas.create_line(x, center_y - height / 2, x, center_y + height / 2, fill=color, width=3, capstyle="round", tags="wave")
        self.overlay_phase += 0.28
        self.overlay_animation_id = self.root.after(55, self._animate_overlay)

    def _hide_overlay(self) -> None:
        if self.overlay is not None:
            self.overlay.withdraw()
        if self.overlay_animation_id is not None:
            self.root.after_cancel(self.overlay_animation_id)
            self.overlay_animation_id = None

    def _save_settings(self) -> None:
        if self.capturing_hotkey:
            self._finish_hotkey_capture()
        self.config.hotkey = self.hotkey_var.get().strip() or "ctrl+space"
        self.config.model = self.model_var.get()
        self.config.language = self.language_var.get()
        self.config.auto_paste = self.auto_paste_var.get()
        self.config.punctuation = self.punctuation_var.get()
        self.store.save(self.config)
        self.detail_var.set(f"Settings saved. Hold {self.config.hotkey} to dictate.")

    def _cancel_hotkey_capture(self) -> None:
        self.capturing_hotkey = False
        if self.hotkey_capture_binding is not None:
            self.hotkey_button.unbind("<KeyPress>", self.hotkey_capture_binding)
            self.hotkey_capture_binding = None
        self.hotkey_capture_keys = set()
        self.hotkey_var.set(self.config.hotkey)
        self.hotkey_button_var.set(self._format_hotkey(self.config.hotkey))
        self.hotkey_hint_var.set("Click the button, then press your key combination")
        self.hotkey_button.configure(bg="#25343d", fg="#e2ece9", activebackground="#334b57", activeforeground="#ffffff")
        try:
            self._restart_hotkey(self.config.hotkey)
        except (RuntimeError, ValueError) as exc:
            self.detail_var.set(str(exc))

    def close(self) -> None:
        if self.recording:
            self.recorder.end()
        if self.hotkey is not None:
            self.hotkey.stop()
        if self.tray is not None:
            self.tray.stop()
        self.recorder.close()
        if self.engine is not None:
            self.engine.unload()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    VoxenApp(root)
    root.mainloop()
