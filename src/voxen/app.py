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
from .injector import ClipboardInjector
from .presentation import theme
from .presentation.hotkey_capture import HotkeyCapture
from .presentation.overlay import RecordingOverlay
from .presentation.shapes import RoundedButton
from .stt import ModelManager, is_parakeet_model
from .tray import SystemTray

EVENT_POLL_MS = 25
MIN_WIDTH = 500
MIN_HEIGHT = 220
MODEL_LABELS = dict(zip(SUPPORTED_MODELS, ("Whisper Tiny", "Whisper Base", "Whisper Small", "Parakeet v3"), strict=True))
LANGUAGE_LABELS = dict(zip(SUPPORTED_LANGUAGES, ("Auto", "Italian", "English", "Japanese", "French", "German", "Spanish"), strict=True))

logger = logging.getLogger(__name__)


class VoxenApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Voxen")
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.root.configure(bg=theme.BACKGROUND)
        theme.enable_light_titlebar(self.root)

        self.store = ConfigStore()
        self.config = self.store.load()
        self.dictation = DictationService(
            audio=AudioRecorder(self.config.sample_rate),
            transcriber=ModelManager(),
            processor=TextProcessor(),
            injector=ClipboardInjector(),
            executor=ThreadPoolExecutor(max_workers=1, thread_name_prefix="voxen-stt"),
            config=self.config,
        )
        self.audio_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voxen-audio")
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
        self.hotkey_hint_var = tk.StringVar(value="Click shortcut to change it")
        self.model_display_var = tk.StringVar(value=MODEL_LABELS[self.config.model])
        self.language_display_var = tk.StringVar(value=LANGUAGE_LABELS[self.config.language])
        self.model_combo: ttk.Combobox | None = None
        self.language_combo: ttk.Combobox | None = None
        self.started_at = 0.0

        self._build_ui()
        self.model_var.trace_add("write", self._update_language_control)
        self._update_language_control()
        self._fit_window_to_content()
        self.overlay = RecordingOverlay(self.root, level_provider=lambda: self.dictation.audio_level)
        self.root.withdraw()
        self._start_services()
        self.root.after(EVENT_POLL_MS, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._hide_settings)

    @property
    def state(self) -> AppState:
        return self.dictation.state

    def _update_language_control(self, *_args) -> None:
        if self.language_combo is not None:
            automatic = is_parakeet_model(self.model_var.get())
            self.language_combo.configure(state="disabled" if automatic else "readonly")
            if automatic:
                self.language_var.set("auto")
            self.language_display_var.set(LANGUAGE_LABELS[self.language_var.get()])

    def _build_ui(self) -> None:
        self.combo_popup_font = theme.apply(self.root)
        content = tk.Frame(self.root, bg=theme.SURFACE)
        content.pack(fill="both", expand=True, padx=28, pady=24)

        tk.Label(content, text="Voxen", bg=theme.SURFACE, fg=theme.TEXT_PRIMARY,
                 font=(theme.FONT_FAMILY, 28, "bold")).pack(anchor="w")
        tk.Label(content, text="Your voice, anywhere you type.", bg=theme.SURFACE,
                 fg=theme.TEXT_SECONDARY, font=(theme.FONT_FAMILY, 10)).pack(anchor="w", pady=(0, 22))

        controls = tk.Frame(content, bg=theme.SURFACE)
        controls.pack(fill="x")
        controls.columnconfigure(1, weight=1)
        self.hotkey_button = RoundedButton(
            controls, textvariable=self.hotkey_button_var, command=self._start_hotkey_capture,
            bg=theme.BUTTON_BG, fg=theme.BUTTON_FG, active_bg=theme.BUTTON_ACTIVE_BG,
            parent_bg=theme.SURFACE, width=158, height=38, radius=9,
            font=(theme.FONT_FAMILY, 9, "bold"),
        )
        self.hotkey_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.hotkey_capture = HotkeyCapture(self.hotkey_button, self.hotkey_var, self.hotkey_button_var,
                                            self.hotkey_hint_var, self._on_hotkey_captured)
        self.hotkey_button_var.trace_add("write", self._resize_hotkey_button)

        self.model_combo = ttk.Combobox(
            controls, textvariable=self.model_display_var, values=tuple(MODEL_LABELS.values()),
            state="readonly", width=15, style="Voxen.TCombobox",
        )
        self.model_combo.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.model_combo.bind("<<ComboboxSelected>>", self._on_combo_selected)
        self.language_combo = ttk.Combobox(
            controls, textvariable=self.language_display_var, values=tuple(LANGUAGE_LABELS.values()),
            state="readonly", width=8, style="Voxen.TCombobox",
        )
        self.language_combo.grid(row=0, column=2, sticky="ew", padx=(0, 8))
        self.language_combo.bind("<<ComboboxSelected>>", self._on_combo_selected)

        # Secondary preferences stay out of the default layout; no settings page.
        more = ttk.Menubutton(controls, text="…", style="Voxen.TMenubutton", width=3, takefocus=True)
        self.preferences_menu = tk.Menu(more, tearoff=False, bg=theme.SURFACE,
                                        fg=theme.TEXT_PRIMARY, activebackground=theme.BUTTON_BG,
                                        activeforeground=theme.TEXT_PRIMARY)
        self.preferences_menu.add_checkbutton(label="Paste into active app", variable=self.auto_paste_var,
                                               command=self._mark_settings_changed)
        self.preferences_menu.add_checkbutton(label="Final punctuation", variable=self.punctuation_var,
                                               command=self._mark_settings_changed)
        more.configure(menu=self.preferences_menu)
        more.grid(row=0, column=3, sticky="ns")

        tk.Label(content, textvariable=self.hotkey_hint_var, bg=theme.SURFACE, fg=theme.TEXT_MUTED,
                 font=(theme.FONT_FAMILY, 8), wraplength=440, justify="left").pack(anchor="w", pady=(5, 0))
        self._divider(content, pady=(15, 12))

        footer = tk.Frame(content, bg=theme.SURFACE)
        footer.pack(fill="x")
        footer.columnconfigure(0, weight=1)
        state = tk.Frame(footer, bg=theme.SURFACE)
        state.grid(row=0, column=0, sticky="w")
        self.status_indicator = tk.Canvas(state, width=9, height=9, bg=theme.SURFACE, highlightthickness=0)
        self.status_indicator.pack(side="left", padx=(0, 6))
        self.status_dot = self.status_indicator.create_oval(1, 1, 8, 8, outline="", fill=theme.TEXT_MUTED)
        tk.Label(state, textvariable=self.status_var, bg=theme.SURFACE, fg=theme.TEXT_PRIMARY,
                 font=(theme.FONT_FAMILY, 9, "bold")).pack(side="left")
        tk.Label(state, text="·  Local inference", bg=theme.SURFACE, fg=theme.TEXT_MUTED,
                 font=(theme.FONT_FAMILY, 9)).pack(side="left", padx=(5, 0))
        self.status_var.trace_add("write", self._update_status_indicator)
        self._update_status_indicator()

        self.save_button = ttk.Button(footer, text="Save settings", command=self._save_settings, style="Voxen.TButton")
        self.save_button.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(12, 0))
        detail = tk.Label(footer, textvariable=self.detail_var, bg=theme.SURFACE, fg=theme.STATUS_DETAIL,
                          font=(theme.FONT_FAMILY, 8), wraplength=315, justify="left")
        detail.grid(row=1, column=0, sticky="w", pady=(3, 0))
        # Error messages may be longer than the normal one-line status.
        self.detail_var.trace_add("write", self._schedule_layout_fit)
        self.hotkey_hint_var.trace_add("write", self._schedule_layout_fit)

    def _update_status_indicator(self, *_args) -> None:
        color = {"Ready": theme.SUCCESS, "Error": theme.ERROR}.get(self.status_var.get(), theme.TEXT_MUTED)
        self.status_indicator.itemconfigure(self.status_dot, fill=color)

    def _resize_hotkey_button(self, *_args) -> None:
        from tkinter import font

        width = max(158, font.Font(root=self.root, font=(theme.FONT_FAMILY, 9, "bold")).measure(self.hotkey_button_var.get()) + 24)
        self.hotkey_button.configure(width=width)
        self._schedule_layout_fit()

    def _schedule_layout_fit(self, *_args) -> None:
        self.root.after_idle(self._grow_window_to_content)

    def _grow_window_to_content(self) -> None:
        self.root.update_idletasks()
        width = min(max(self.root.winfo_width(), self.root.winfo_reqwidth()), self.root.winfo_screenwidth())
        height = min(max(self.root.winfo_height(), self.root.winfo_reqheight()), int(self.root.winfo_screenheight() * 0.92))
        if (width, height) != (self.root.winfo_width(), self.root.winfo_height()):
            self.root.geometry(f"{width}x{height}")

    def _fit_window_to_content(self) -> None:
        """Size the dashboard to its content instead of a hardcoded rect.

        A fixed geometry breaks as soon as fonts/DPI change: once the
        process correctly declares per-monitor DPI awareness, Tk renders at
        true size and 520px no longer fits the Save button. Fitting to the
        requested size keeps every control visible on any scale factor,
        clamped to the screen so small displays stay usable.
        """
        try:
            self.root.update_idletasks()
            width = min(max(self.root.winfo_reqwidth(), MIN_WIDTH), self.root.winfo_screenwidth())
            height = min(max(self.root.winfo_reqheight(), MIN_HEIGHT), int(self.root.winfo_screenheight() * 0.92))
            self.root.geometry(f"{width}x{height}")
        except tk.TclError:
            self.root.geometry("540x260")

    @staticmethod
    def _divider(parent: tk.Widget, *, pady) -> tk.Frame:
        line = tk.Frame(parent, bg=theme.DIVIDER, height=1)
        line.pack(fill="x", pady=pady)
        return line

    def _on_combo_selected(self, event: tk.Event) -> None:
        if event.widget is self.model_combo:
            self.model_var.set(SUPPORTED_MODELS[self.model_combo.current()])
        elif event.widget is self.language_combo:
            self.language_var.set(SUPPORTED_LANGUAGES[self.language_combo.current()])
        self._mark_settings_changed()

    def _mark_settings_changed(self) -> None:
        self.detail_var.set("Unsaved changes. Save settings to apply.")

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
        # dictation.start() only queues the warm-up; the engine reports back
        # via EngineReady/EngineFailed events, so always show "Starting..."
        # here and let _on_engine_ready replace it.
        self.status_var.set("Starting...")
        self.detail_var.set("Loading the local transcription model.")
        try:
            self.hotkey = GlobalHotkey(self.config.hotkey, self._request_recording_start, self._request_recording_stop)
            self.hotkey.start()
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
        if was_recording:
            self.audio_executor.submit(self._stop_recording_from_pause)
            return
        changed = self.dictation.toggle_pause()
        if not changed:
            return
        if self.state is AppState.READY:
            self.status_var.set("Ready")
            self.detail_var.set(f"Hold {self.config.hotkey} to dictate.")
        elif self.state is AppState.PAUSED:
            self.status_var.set("Paused")
            self.detail_var.set("Resume from the Voxen tray icon.")

    def _request_recording_start(self) -> None:
        if self.dictation.begin_recording():
            self.events.put(("recording_started", None))

    def _request_recording_stop(self) -> None:
        if self.dictation.stop_recording():
            self.events.put(("recording_stopped", None))

    def _stop_recording_from_pause(self) -> None:
        self._request_recording_stop()

    def _show_recording_started(self) -> None:
        self.started_at = time.monotonic()
        self.status_var.set("Listening...")
        self.detail_var.set("Release the hotkey when you finish speaking.")
        self.overlay.show("listening")
        self._update_overlay_clock()

    def _show_recording_stopped(self) -> None:
        self.status_var.set("Processing...")
        self.detail_var.set("Transcribing locally...")
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
                    elif kind == "recording_started":
                        self._show_recording_started()
                    elif kind == "recording_stopped":
                        self._show_recording_stopped()
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
        self.detail_var.set(f"Model not ready: {event.message} Fix the issue, then click Save settings to retry.")

    def _on_audio_failed(self, event: ev.AudioFailed) -> None:
        self.overlay.hide()
        self.status_var.set("Error")
        self.detail_var.set(event.message)

    def _on_audio_dropout(self, event: ev.AudioDropout) -> None:
        self.detail_var.set(f"Unstable audio during recording: {event.message}")

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
        self.detail_var.set(f"{event.message} Click Save settings to retry.")

    def _on_unexpected_error(self, event: ev.UnexpectedError) -> None:
        self.overlay.hide()
        self.status_var.set("Error")
        self.detail_var.set(f"{event.message} Click Save settings to retry.")

    def _retry_engine(self) -> bool:
        """Leave ERROR by re-warming the model. Returns True if a retry started."""
        if self.dictation.retry():
            self.status_var.set("Starting...")
            self.detail_var.set("Downloading or loading the local transcription model.")
            return True
        return False

    def _save_settings(self) -> None:
        if self.hotkey_capture is not None and self.hotkey_capture.capturing:
            self.hotkey_capture.finish()
        try:
            HotkeyCapture.display_text(self.hotkey_var.get().strip() or "ctrl+space")
        except ValueError as exc:
            self.detail_var.set(str(exc))
            return
        previous_model = (self.config.model, self.config.device, self.config.compute_type)
        self.config.hotkey = self.hotkey_var.get().strip() or "ctrl+space"
        self.config.model = self.model_var.get()
        self.config.language = self.language_var.get()
        self.config.auto_paste = self.auto_paste_var.get()
        self.config.punctuation = self.punctuation_var.get()
        try:
            self.store.save(self.config)
        except OSError as exc:
            self.detail_var.set(f"Could not save settings: {exc}")
            return
        if self.state is AppState.ERROR:
            self._retry_engine()
            return
        current_model = (self.config.model, self.config.device, self.config.compute_type)
        if current_model != previous_model and self.dictation.rewarm():
            self.detail_var.set("Settings saved. Loading the new model in the background.")
            return
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
            self.audio_executor.shutdown(wait=True, cancel_futures=False)
        except Exception:
            logger.exception("Failed to shut down the audio worker")
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
    from .infrastructure.dpi import ensure_awareness
    from .infrastructure.logging_setup import configure as configure_logging

    try:
        configure_logging()
    except OSError as exc:
        logger.warning("Failed to set up file logging: %s", exc)

    # Must run before tk.Tk(): awareness can only be set once per process,
    # and every Win32 metric read afterwards depends on it (see dpi.py).
    try:
        ensure_awareness()
    except Exception:
        logger.warning("Failed to set DPI awareness", exc_info=True)

    root = tk.Tk()
    VoxenApp(root)
    root.mainloop()
