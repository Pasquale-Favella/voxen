from __future__ import annotations

import logging
import queue
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk

from .application import events as ev
from .application.dictation import DictationService
from .audio import AudioRecorder
from .config import SUPPORTED_LANGUAGES, SUPPORTED_MODELS, ConfigStore
from .domain.state import AppState
from .domain.text import TextProcessor
from .hotkey import GlobalHotkey
from .infrastructure.resources import asset_path
from .injector import ClipboardInjector
from .presentation import theme
from .presentation.hotkey_capture import HotkeyCapture
from .presentation.overlay import RecordingOverlay
from .presentation.shapes import Checkbox, RoundedButton
from .stt import ModelManager
from .tray import SystemTray

EVENT_POLL_MS = 25

logger = logging.getLogger(__name__)


class VoxenApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Voxen")
        self.root.geometry("560x520")
        self.root.minsize(500, 460)
        self.root.configure(bg=theme.BACKGROUND)
        theme.enable_dark_titlebar(self.root)

        self.store = ConfigStore()
        self.config = self.store.load()
        self.dictation = DictationService(
            audio=AudioRecorder(self.config.sample_rate, self.config.preroll_ms),
            transcriber=ModelManager(),
            processor=TextProcessor(),
            injector=ClipboardInjector(),
            executor=ThreadPoolExecutor(max_workers=1, thread_name_prefix="voxen-stt"),
            config=self.config,
        )
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.hotkey: GlobalHotkey | None = None
        self.tray: SystemTray | None = None
        self.hotkey_capture: HotkeyCapture | None = None

        self.status_var = tk.StringVar(value="Starting Voxen...")
        self.detail_var = tk.StringVar(value="Local transcription, ready when you are.")
        self.hotkey_var = tk.StringVar(value=self.config.hotkey)
        self.model_var = tk.StringVar(value=self.config.model)
        self.language_var = tk.StringVar(value=self.config.language)
        self.auto_paste_var = tk.BooleanVar(value=self.config.auto_paste)
        self.punctuation_var = tk.BooleanVar(value=self.config.punctuation)
        self.hotkey_button_var = tk.StringVar(value=HotkeyCapture.display_text(self.config.hotkey))
        self.hotkey_hint_var = tk.StringVar(value="Click the button, then press your key combination")
        self.model_combo: ttk.Combobox | None = None
        self.language_combo: ttk.Combobox | None = None
        self.started_at = 0.0

        self._build_ui()
        self.overlay = RecordingOverlay(self.root, level_provider=lambda: self.dictation.audio_level)
        self.root.withdraw()
        self._start_services()
        self.root.after(EVENT_POLL_MS, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._hide_settings)

    @property
    def state(self) -> AppState:
        return self.dictation.state

    def _build_ui(self) -> None:
        self.combo_popup_font = theme.apply(self.root)

        container = tk.Frame(self.root, bg=theme.SURFACE)
        container.pack(fill="both", expand=True)
        content = tk.Frame(container, bg=theme.SURFACE)
        content.pack(fill="both", expand=True, padx=32, pady=30)

        header = tk.Frame(content, bg=theme.SURFACE)
        header.pack(fill="x")
        try:
            from PIL import Image, ImageTk
            brand_image = Image.open(asset_path("voxen-mark.png")).resize((36, 36), Image.Resampling.LANCZOS)
            self.brand_photo = ImageTk.PhotoImage(brand_image)
            brand = tk.Label(header, image=self.brand_photo, bg=theme.SURFACE, borderwidth=0)
        except (ImportError, FileNotFoundError):
            brand = tk.Canvas(header, width=36, height=36, bg=theme.SURFACE, highlightthickness=0)
            brand.create_oval(3, 3, 33, 33, fill=theme.ACCENT, outline="")
            brand.create_oval(13, 13, 23, 23, fill=theme.SURFACE, outline="")
        brand.pack(side="left", padx=(0, 12))
        title_block = tk.Frame(header, bg=theme.SURFACE)
        title_block.pack(side="left")
        tk.Label(title_block, text="Voxen", bg=theme.SURFACE, fg=theme.TEXT_PRIMARY, font=(theme.FONT_FAMILY, 22, "bold")).pack(anchor="w")
        tk.Label(title_block, text="Local · private · your voice anywhere you type", bg=theme.SURFACE, fg=theme.TEXT_SECONDARY, font=(theme.FONT_FAMILY, 9)).pack(anchor="w")

        self._divider(content, pady=(22, 16))

        status_row = tk.Frame(content, bg=theme.SURFACE)
        status_row.pack(fill="x")
        status_indicator = tk.Canvas(status_row, width=10, height=10, bg=theme.SURFACE, highlightthickness=0)
        status_indicator.pack(side="left", padx=(0, 10))
        status_indicator.create_oval(1, 1, 9, 9, fill=theme.ACCENT, outline="")
        status_text = tk.Frame(status_row, bg=theme.SURFACE)
        status_text.pack(side="left", fill="x", expand=True)
        tk.Label(status_text, textvariable=self.status_var, bg=theme.SURFACE, fg=theme.TEXT_PRIMARY, font=(theme.FONT_FAMILY, 12, "bold")).pack(anchor="w")
        tk.Label(status_text, textvariable=self.detail_var, bg=theme.SURFACE, fg=theme.STATUS_DETAIL, font=(theme.FONT_FAMILY, 9)).pack(anchor="w", pady=(1, 0))
        tk.Label(status_row, textvariable=self.hotkey_var, bg=theme.SURFACE, fg=theme.HOTKEY_LABEL, font=(theme.MONO_FAMILY, 8)).pack(side="right")

        self._divider(content, pady=(18, 20))

        controls = tk.Frame(content, bg=theme.SURFACE)
        controls.pack(fill="x")
        controls.columnconfigure(1, weight=1)
        tk.Label(controls, text="QUICK SETTINGS", bg=theme.SURFACE, fg=theme.TEXT_MUTED, font=(theme.FONT_FAMILY, 8, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        tk.Label(controls, text="Hotkey", bg=theme.SURFACE, fg=theme.LABEL_MUTED, font=(theme.FONT_FAMILY, 9)).grid(row=1, column=0, sticky="w", pady=8)
        hotkey_area = tk.Frame(controls, bg=theme.SURFACE)
        hotkey_area.grid(row=1, column=1, sticky="ew", pady=8)
        hotkey_area.columnconfigure(0, weight=1)
        self.hotkey_button = RoundedButton(
            hotkey_area,
            textvariable=self.hotkey_button_var,
            command=self._start_hotkey_capture,
            bg=theme.BUTTON_BG,
            fg=theme.BUTTON_FG,
            active_bg=theme.BUTTON_ACTIVE_BG,
            parent_bg=theme.SURFACE,
            width=220,
            height=36,
            font=(theme.MONO_FAMILY, 10, "bold"),
        )
        self.hotkey_button.grid(row=0, column=0, sticky="ew")
        tk.Label(hotkey_area, textvariable=self.hotkey_hint_var, bg=theme.SURFACE, fg=theme.HINT_MUTED, font=(theme.FONT_FAMILY, 8)).grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.hotkey_capture = HotkeyCapture(self.hotkey_button, self.hotkey_var, self.hotkey_button_var, self.hotkey_hint_var, self._on_hotkey_captured)

        model_lang_row = tk.Frame(controls, bg=theme.SURFACE)
        model_lang_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)
        model_lang_row.columnconfigure(1, weight=1)
        model_lang_row.columnconfigure(3, weight=1)
        for column, label, variable, values, attribute in (
            (0, "Model", self.model_var, SUPPORTED_MODELS, "model_combo"),
            (2, "Language", self.language_var, SUPPORTED_LANGUAGES, "language_combo"),
        ):
            tk.Label(model_lang_row, text=label, bg=theme.SURFACE, fg=theme.LABEL_MUTED, font=(theme.FONT_FAMILY, 9)).grid(row=0, column=column, sticky="w", padx=(0 if column == 0 else 24, 10))
            combo = ttk.Combobox(
                model_lang_row,
                textvariable=variable,
                values=values,
                state="readonly",
                takefocus=True,
                style="Voxen.TCombobox",
            )
            combo.bind("<<ComboboxSelected>>", self._on_combo_selected)
            setattr(self, attribute, combo)
            combo.grid(row=0, column=column + 1, sticky="ew")
        checks = tk.Frame(controls, bg=theme.SURFACE)
        checks.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        for text, variable in (
            ("Paste into active app", self.auto_paste_var),
            ("Final punctuation", self.punctuation_var),
        ):
            Checkbox(
                checks,
                text=text,
                variable=variable,
                accent=theme.ACCENT,
                text_fg=theme.LABEL_MUTED,
                box_off_bg=theme.SURFACE,
                box_border=theme.COMBO_BORDER,
                check_fg=theme.ACCENT_DARK,
                parent_bg=theme.SURFACE,
            ).pack(side="left", padx=(0, 24))

        self._divider(content, pady=(22, 18))

        actions = tk.Frame(content, bg=theme.SURFACE)
        actions.pack(fill="x")
        RoundedButton(
            actions,
            text="Save settings",
            command=self._save_settings,
            bg=theme.ACCENT,
            fg=theme.ACCENT_DARK,
            active_bg=theme.ACCENT_SOFT,
            parent_bg=theme.SURFACE,
            width=150,
            height=38,
            font=(theme.FONT_FAMILY, 10, "bold"),
        ).pack(side="left")
        tk.Label(content, text="Model downloads only on first use — inference stays on this machine", bg=theme.SURFACE, fg=theme.TEXT_MUTED, font=(theme.FONT_FAMILY, 8)).pack(anchor="w", pady=(14, 0))

    @staticmethod
    def _divider(parent: tk.Widget, *, pady) -> tk.Frame:
        line = tk.Frame(parent, bg=theme.DIVIDER, height=1)
        line.pack(fill="x", pady=pady)
        return line

    def _on_combo_selected(self, _event: tk.Event) -> None:
        self.detail_var.set("Selection updated. Click SAVE SETTINGS to keep it.")

    def _start_hotkey_capture(self) -> None:
        if self.hotkey is not None:
            self.hotkey.stop()
        self.hotkey_capture.begin()

    def _on_hotkey_captured(self, hotkey: str) -> None:
        try:
            self._restart_hotkey(hotkey)
        except (RuntimeError, ValueError) as exc:
            self.detail_var.set(str(exc))

    def _restart_hotkey(self, hotkey: str) -> None:
        if self.hotkey is not None:
            self.hotkey.stop()
        self.hotkey = GlobalHotkey(hotkey, self._request_recording_start, self._request_recording_stop)
        self.hotkey.start()

    def _start_services(self) -> None:
        self.dictation.start()
        if self.state is not AppState.ERROR:
            self.status_var.set("Starting...")
            self.detail_var.set("Loading the local transcription model.")
        try:
            self.hotkey = GlobalHotkey(self.config.hotkey, self._request_recording_start, self._request_recording_stop)
            self.hotkey.start()
            if self.state is AppState.READY:
                self.detail_var.set(f"Hold {self.config.hotkey} to dictate.")
        except Exception as exc:
            logger.warning("Failed to start the global hotkey listener: %s", exc)
            self.detail_var.set(str(exc))
        try:
            self.tray = SystemTray(
                self._request_show_settings,
                self._request_toggle_pause,
                self._request_quit,
            )
            self.tray.start()
        except Exception as exc:
            logger.warning("Failed to start the system tray icon: %s", exc)
            self._show_settings()
            self.detail_var.set(str(exc))
        self._show_settings()

    def _request_show_settings(self) -> None:
        self.events.put(("show_settings", None))

    def _request_toggle_pause(self) -> None:
        self.events.put(("toggle_pause", None))

    def _request_quit(self) -> None:
        self.events.put(("quit", None))

    def _show_settings(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _hide_settings(self) -> None:
        if self.hotkey_capture is not None and self.hotkey_capture.capturing:
            self._cancel_hotkey_capture()
        self.root.withdraw()

    def _toggle_pause(self) -> None:
        was_recording = self.state is AppState.RECORDING
        changed = self.dictation.toggle_pause()
        if was_recording:
            # Pausing mid-recording finishes the recording (it gets
            # transcribed) rather than pausing mid-capture.
            self.status_var.set("Processing...")
            self.detail_var.set("Whisper is transcribing locally.")
            self.overlay.show("processing")
            return
        if not changed:
            return
        if self.state is AppState.READY:
            self.status_var.set("Ready")
            self.detail_var.set(f"Hold {self.config.hotkey} to dictate.")
        elif self.state is AppState.PAUSED:
            self.status_var.set("Paused")
            self.detail_var.set("Resume from the Voxen tray icon.")

    def _request_recording_start(self) -> None:
        self.events.put(("recording_start", None))

    def _request_recording_stop(self) -> None:
        self.events.put(("recording_stop", None))

    def _start_recording(self) -> None:
        if not self.dictation.begin_recording():
            return
        self.started_at = time.monotonic()
        self.status_var.set("Listening...")
        self.detail_var.set("Release the hotkey when you finish speaking.")
        self.overlay.show("listening")
        self._update_overlay_clock()

    def _stop_recording(self) -> None:
        if not self.dictation.stop_recording():
            return
        self.status_var.set("Processing...")
        self.detail_var.set("Whisper is transcribing locally.")
        self.overlay.show("processing")

    def _update_overlay_clock(self) -> None:
        if self.state is not AppState.RECORDING:
            return
        elapsed = int(time.monotonic() - self.started_at)
        self.overlay.set_elapsed_seconds(elapsed)
        self.root.after(250, self._update_overlay_clock)

    def _drain_events(self) -> None:
        if self.state is AppState.CLOSING:
            return
        try:
            while True:
                try:
                    kind, payload = self.events.get_nowait()
                    if kind == "show_settings":
                        self._show_settings()
                    elif kind == "toggle_pause":
                        self._toggle_pause()
                    elif kind == "quit":
                        self.close()
                        return
                    elif kind == "recording_start":
                        self._start_recording()
                    elif kind == "recording_stop":
                        self._stop_recording()
                    else:
                        logger.warning("Unknown UI command: %s", kind)
                except queue.Empty:
                    raise
                except Exception as exc:
                    logger.exception("Failed to handle UI command %s", kind)
                    self.status_var.set("Error")
                    self.detail_var.set(str(exc))
        except queue.Empty:
            pass
        for event in self.dictation.drain_events():
            self._handle_dictation_event(event)
        if self.state is not AppState.CLOSING:
            self.root.after(EVENT_POLL_MS, self._drain_events)

    def _handle_dictation_event(self, event: ev.DictationEvent) -> None:
        handler = _EVENT_HANDLERS.get(type(event))
        if handler is None:
            logger.warning("No handler registered for dictation event %r", event)
            return
        handler(self, event)

    def _on_engine_loading(self, _event: ev.EngineLoading) -> None:
        if self.state is AppState.STARTING:
            self.status_var.set("Starting...")
            self.detail_var.set("Downloading or loading the local transcription model.")

    def _on_engine_ready(self, _event: ev.EngineReady) -> None:
        if self.state is AppState.READY:
            self.status_var.set("Ready")
            self.detail_var.set(f"Hold {self.config.hotkey} to dictate.")

    def _on_engine_failed(self, event: ev.EngineFailed) -> None:
        self.status_var.set("Error")
        self.detail_var.set(f"Model not ready: {event.message}")

    def _on_audio_failed(self, event: ev.AudioFailed) -> None:
        self.status_var.set("Error")
        self.detail_var.set(event.message)

    def _on_audio_dropout(self, event: ev.AudioDropout) -> None:
        self.detail_var.set(f"Audio non stabile durante la registrazione: {event.message}")

    def _on_no_speech_detected(self, _event: ev.NoSpeechDetected) -> None:
        self.overlay.hide()
        self.status_var.set("Ready")
        self.detail_var.set("No speech detected.")

    def _on_transcript_pasted(self, _event: ev.TranscriptPasted) -> None:
        self.overlay.hide()
        self.status_var.set("Ready")
        self.detail_var.set("Text pasted into the active application.")

    def _on_transcript_ready(self, _event: ev.TranscriptReady) -> None:
        self.overlay.hide()
        self.status_var.set("Ready")
        self.detail_var.set("Transcript ready. Automatic paste is disabled.")

    def _on_paste_failed(self, event: ev.PasteFailed) -> None:
        self.overlay.hide()
        self.status_var.set("Ready")
        self.detail_var.set(event.message)

    def _on_transcription_failed(self, event: ev.TranscriptionFailed) -> None:
        self.overlay.hide()
        self.status_var.set("Error")
        self.detail_var.set(event.message)

    def _on_unexpected_error(self, event: ev.UnexpectedError) -> None:
        self.overlay.hide()
        self.status_var.set("Error")
        self.detail_var.set(event.message)

    def _save_settings(self) -> None:
        if self.hotkey_capture is not None and self.hotkey_capture.capturing:
            self.hotkey_capture.finish()
        self.config.hotkey = self.hotkey_var.get().strip() or "ctrl+space"
        self.config.model = self.model_var.get()
        self.config.language = self.language_var.get()
        self.config.auto_paste = self.auto_paste_var.get()
        self.config.punctuation = self.punctuation_var.get()
        self.store.save(self.config)
        self.detail_var.set(f"Settings saved. Hold {self.config.hotkey} to dictate.")

    def _cancel_hotkey_capture(self) -> None:
        self.hotkey_capture.cancel(self.config.hotkey)

    def close(self) -> None:
        if self.state is AppState.CLOSING:
            return
        try:
            if self.hotkey is not None:
                self.hotkey.stop()
        except Exception:
            logger.exception("Failed to stop the global hotkey listener during shutdown")
        try:
            if self.tray is not None:
                self.tray.stop()
        except Exception:
            logger.exception("Failed to stop the system tray icon during shutdown")
        try:
            self.dictation.shutdown()
        except Exception:
            logger.exception("Failed to shut down the dictation service")
        try:
            self.root.destroy()
        except Exception:
            logger.exception("Failed to destroy the root window during shutdown")


_EVENT_HANDLERS = {
    ev.EngineLoading: VoxenApp._on_engine_loading,
    ev.EngineReady: VoxenApp._on_engine_ready,
    ev.EngineFailed: VoxenApp._on_engine_failed,
    ev.AudioFailed: VoxenApp._on_audio_failed,
    ev.AudioDropout: VoxenApp._on_audio_dropout,
    ev.NoSpeechDetected: VoxenApp._on_no_speech_detected,
    ev.TranscriptPasted: VoxenApp._on_transcript_pasted,
    ev.TranscriptReady: VoxenApp._on_transcript_ready,
    ev.PasteFailed: VoxenApp._on_paste_failed,
    ev.TranscriptionFailed: VoxenApp._on_transcription_failed,
    ev.UnexpectedError: VoxenApp._on_unexpected_error,
}


def main() -> None:
    from .infrastructure.logging_setup import configure as configure_logging

    try:
        configure_logging()
    except OSError as exc:
        logger.warning("Failed to set up file logging: %s", exc)

    root = tk.Tk()
    VoxenApp(root)
    root.mainloop()
