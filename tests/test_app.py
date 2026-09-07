from __future__ import annotations

import queue
from types import SimpleNamespace

import voxen.app as app_module
from voxen.app import VoxenApp
from voxen.application import events as ev
from voxen.config import AppConfig
from voxen.domain.state import AppState


class FakeVar:
    def __init__(self, value="") -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class FakeRoot:
    def __init__(self) -> None:
        self.scheduled = []
        self.destroy_calls = 0

    def after(self, delay, callback):
        self.scheduled.append((delay, callback))
        return len(self.scheduled)

    def withdraw(self) -> None:
        pass

    def deiconify(self) -> None:
        pass

    def lift(self) -> None:
        pass

    def focus_force(self) -> None:
        pass

    def destroy(self) -> None:
        self.destroy_calls += 1


class FakeOverlay:
    def __init__(self) -> None:
        self.show_calls: list[str] = []
        self.hide_calls = 0
        self.elapsed: list[int] = []

    def show(self, mode: str) -> None:
        self.show_calls.append(mode)

    def hide(self) -> None:
        self.hide_calls += 1

    def set_elapsed_seconds(self, seconds: int) -> None:
        self.elapsed.append(seconds)


class FakeLifecycleService:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


class FailingLifecycleService(FakeLifecycleService):
    def stop(self) -> None:
        self.stop_calls += 1
        raise RuntimeError("service shutdown failed")


class FakeHotkeyCapture:
    def __init__(self) -> None:
        self.capturing = False
        self.begin_calls = 0
        self.cancel_calls: list[str] = []

    def begin(self) -> None:
        self.begin_calls += 1
        self.capturing = True

    def cancel(self, revert_to: str) -> None:
        self.cancel_calls.append(revert_to)
        self.capturing = False

    def finish(self) -> None:
        self.capturing = False


class FakeDictationService:
    """Stands in for DictationService: VoxenApp should only ever call
    this narrow interface, never reach past it into audio/model/injector."""

    def __init__(self, initial_state: AppState = AppState.READY) -> None:
        self.state = initial_state
        self.audio_level = 0.0
        self.start_calls = 0
        self.begin_calls = 0
        self.stop_calls = 0
        self.shutdown_calls = 0
        self.begin_recording_result = True
        self.stop_recording_result = True
        self.toggle_result = True
        self._pending_events: list[ev.DictationEvent] = []

    def start(self) -> None:
        self.start_calls += 1

    def begin_recording(self) -> bool:
        self.begin_calls += 1
        if self.begin_recording_result:
            self.state = AppState.RECORDING
        return self.begin_recording_result

    def stop_recording(self) -> bool:
        self.stop_calls += 1
        if self.stop_recording_result:
            self.state = AppState.PROCESSING
        return self.stop_recording_result

    def toggle_pause(self) -> bool:
        if self.state is AppState.RECORDING:
            self.state = AppState.PROCESSING
            return True
        if not self.toggle_result:
            return False
        if self.state is AppState.READY:
            self.state = AppState.PAUSED
            return True
        if self.state is AppState.PAUSED:
            self.state = AppState.READY
            return True
        return False

    def drain_events(self) -> list[ev.DictationEvent]:
        events, self._pending_events = self._pending_events, []
        return events

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        self.state = AppState.CLOSING


def make_app(dictation: FakeDictationService | None = None) -> VoxenApp:
    app = object.__new__(VoxenApp)
    app.dictation = dictation or FakeDictationService()
    app.root = FakeRoot()
    app.events = queue.Queue()
    app.status_var = FakeVar()
    app.detail_var = FakeVar()
    app.overlay = FakeOverlay()
    app.hotkey = None
    app.tray = None
    app.hotkey_capture = None
    app.config = SimpleNamespace(hotkey="ctrl+space")
    app.started_at = 0.0
    return app


def test_start_recording_shows_listening_overlay_when_dictation_accepts() -> None:
    app = make_app()

    app._start_recording()

    assert app.dictation.begin_calls == 1
    assert app.overlay.show_calls == ["listening"]
    assert app.status_var.value == "Listening..."


def test_start_recording_does_nothing_when_dictation_declines() -> None:
    app = make_app()
    app.dictation.begin_recording_result = False

    app._start_recording()

    assert app.overlay.show_calls == []


def test_stop_recording_shows_processing_overlay() -> None:
    app = make_app(FakeDictationService(AppState.RECORDING))

    app._stop_recording()

    assert app.dictation.stop_calls == 1
    assert app.overlay.show_calls == ["processing"]
    assert app.status_var.value == "Processing..."


def test_toggle_pause_from_ready_to_paused() -> None:
    app = make_app()

    app._toggle_pause()

    assert app.dictation.state is AppState.PAUSED
    assert app.status_var.value == "Paused"


def test_toggle_pause_from_paused_to_ready() -> None:
    app = make_app(FakeDictationService(AppState.PAUSED))

    app._toggle_pause()

    assert app.dictation.state is AppState.READY
    assert app.status_var.value == "Ready"


def test_toggle_pause_while_recording_finishes_the_recording_instead() -> None:
    app = make_app(FakeDictationService(AppState.RECORDING))

    app._toggle_pause()

    assert app.dictation.state is AppState.PROCESSING
    assert app.overlay.show_calls == ["processing"]


def test_toggle_pause_is_a_no_op_outside_ready_paused_recording() -> None:
    app = make_app(FakeDictationService(AppState.ERROR))

    app._toggle_pause()

    assert app.status_var.value == ""


def test_request_helpers_enqueue_ui_commands() -> None:
    app = make_app()

    app._request_show_settings()
    app._request_toggle_pause()
    app._request_quit()
    app._request_recording_start()
    app._request_recording_stop()

    kinds = []
    while not app.events.empty():
        kinds.append(app.events.get_nowait()[0])
    assert kinds == ["show_settings", "toggle_pause", "quit", "recording_start", "recording_stop"]


def test_drain_events_dispatches_queued_recording_start_command() -> None:
    app = make_app()
    app.events.put(("recording_start", None))

    app._drain_events()

    assert app.dictation.begin_calls == 1
    assert app.root.scheduled  # rescheduled itself


def test_drain_events_dispatches_quit_and_stops_early() -> None:
    app = make_app()
    app.events.put(("quit", None))

    app._drain_events()

    assert app.dictation.shutdown_calls == 1
    assert app.root.destroy_calls == 1
    assert app.root.scheduled == []  # close() returned before rescheduling


def test_drain_events_is_a_no_op_once_closing() -> None:
    app = make_app(FakeDictationService(AppState.CLOSING))
    app.events.put(("recording_start", None))
    app.dictation._pending_events = [ev.EngineReady()]

    app._drain_events()

    assert app.dictation.begin_calls == 0
    assert app.root.scheduled == []


def test_engine_loading_updates_status_while_starting() -> None:
    app = make_app(FakeDictationService(AppState.STARTING))
    app.dictation._pending_events = [ev.EngineLoading()]

    app._drain_events()

    assert app.status_var.value == "Starting..."


def test_engine_ready_updates_status_when_ready() -> None:
    app = make_app(FakeDictationService(AppState.READY))
    app.dictation._pending_events = [ev.EngineReady()]

    app._drain_events()

    assert app.status_var.value == "Ready"
    assert "ctrl+space" in app.detail_var.value


def test_engine_failed_shows_error() -> None:
    app = make_app()
    app.dictation._pending_events = [ev.EngineFailed("no gpu")]

    app._drain_events()

    assert app.status_var.value == "Error"
    assert "no gpu" in app.detail_var.value


def test_audio_failed_shows_error() -> None:
    app = make_app()
    app.dictation._pending_events = [ev.AudioFailed("no microphone")]

    app._drain_events()

    assert app.status_var.value == "Error"
    assert app.detail_var.value == "no microphone"


def test_audio_dropout_is_noted_without_changing_state() -> None:
    app = make_app()
    app.dictation._pending_events = [ev.AudioDropout("input overflow")]

    app._drain_events()

    assert "input overflow" in app.detail_var.value
    assert app.status_var.value == ""


def test_transcript_pasted_hides_overlay_and_returns_to_ready() -> None:
    app = make_app()
    app.dictation._pending_events = [ev.TranscriptPasted("ciao")]

    app._drain_events()

    assert app.overlay.hide_calls == 1
    assert app.status_var.value == "Ready"
    assert app.detail_var.value == "Text pasted into the active application."


def test_no_speech_detected_message() -> None:
    app = make_app()
    app.dictation._pending_events = [ev.NoSpeechDetected()]

    app._drain_events()

    assert app.overlay.hide_calls == 1
    assert app.detail_var.value == "No speech detected."


def test_transcript_ready_message_when_auto_paste_disabled() -> None:
    app = make_app()
    app.dictation._pending_events = [ev.TranscriptReady("ciao")]

    app._drain_events()

    assert app.detail_var.value == "Transcript ready. Automatic paste is disabled."


def test_paste_failed_still_returns_to_ready() -> None:
    app = make_app()
    app.dictation._pending_events = [ev.PasteFailed("clipboard busy")]

    app._drain_events()

    assert app.status_var.value == "Ready"
    assert app.detail_var.value == "clipboard busy"


def test_transcription_failed_shows_error() -> None:
    app = make_app()
    app.dictation._pending_events = [ev.TranscriptionFailed("model crashed")]

    app._drain_events()

    assert app.status_var.value == "Error"
    assert app.detail_var.value == "model crashed"


def test_close_stops_services_in_order_and_is_idempotent() -> None:
    service = FakeDictationService(AppState.READY)
    app = make_app(service)
    app.hotkey = FakeLifecycleService()
    app.tray = FakeLifecycleService()

    app.close()
    app.close()

    assert service.shutdown_calls == 1
    assert app.hotkey.stop_calls == 1
    assert app.tray.stop_calls == 1
    assert app.root.destroy_calls == 1


def test_close_continues_when_a_service_fails() -> None:
    service = FakeDictationService(AppState.READY)
    app = make_app(service)
    app.hotkey = FailingLifecycleService()
    app.tray = FakeLifecycleService()

    app.close()

    assert app.tray.stop_calls == 1
    assert service.shutdown_calls == 1
    assert app.root.destroy_calls == 1


def test_save_settings_updates_config_and_persists() -> None:
    app = make_app()
    app.config = AppConfig()
    saved = []
    app.store = SimpleNamespace(save=lambda cfg: saved.append(cfg))
    app.hotkey_var = FakeVar("ctrl+shift+space")
    app.model_var = FakeVar("small")
    app.language_var = FakeVar("en")
    app.auto_paste_var = FakeVar(False)
    app.punctuation_var = FakeVar(False)

    app._save_settings()

    assert app.config.hotkey == "ctrl+shift+space"
    assert app.config.model == "small"
    assert app.config.language == "en"
    assert app.config.auto_paste is False
    assert app.config.punctuation is False
    assert saved == [app.config]
    assert "ctrl+shift+space" in app.detail_var.value


def test_save_settings_finishes_an_in_progress_capture_first() -> None:
    app = make_app()
    app.config = AppConfig()
    app.store = SimpleNamespace(save=lambda cfg: None)
    app.hotkey_var = FakeVar("ctrl+space")
    app.model_var = FakeVar(app.config.model)
    app.language_var = FakeVar(app.config.language)
    app.auto_paste_var = FakeVar(app.config.auto_paste)
    app.punctuation_var = FakeVar(app.config.punctuation)
    app.hotkey_capture = FakeHotkeyCapture()
    app.hotkey_capture.capturing = True

    app._save_settings()

    assert app.hotkey_capture.capturing is False


def test_start_hotkey_capture_stops_listener_and_begins_capture() -> None:
    app = make_app()
    app.hotkey = FakeLifecycleService()
    app.hotkey_capture = FakeHotkeyCapture()

    app._start_hotkey_capture()

    assert app.hotkey.stop_calls == 1
    assert app.hotkey_capture.begin_calls == 1


def test_hide_settings_cancels_an_in_progress_capture() -> None:
    app = make_app()
    app.hotkey_capture = FakeHotkeyCapture()
    app.hotkey_capture.capturing = True

    app._hide_settings()

    assert app.hotkey_capture.cancel_calls == ["ctrl+space"]


def test_on_hotkey_captured_restarts_the_listener(monkeypatch) -> None:
    created = []

    class FakeHotkey:
        def __init__(self, hotkey, on_press, on_release) -> None:
            self.hotkey = hotkey
            self.start_calls = 0
            created.append(self)

        def start(self) -> None:
            self.start_calls += 1

        def stop(self) -> None:
            pass

    monkeypatch.setattr(app_module, "GlobalHotkey", FakeHotkey)
    app = make_app()
    app.hotkey = None

    app._on_hotkey_captured("ctrl+alt+space")

    assert created[-1].hotkey == "ctrl+alt+space"
    assert created[-1].start_calls == 1
    assert app.hotkey is created[-1]


def test_on_hotkey_captured_reports_an_invalid_combination(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise ValueError("bad combo")

    monkeypatch.setattr(app_module, "GlobalHotkey", boom)
    app = make_app()

    app._on_hotkey_captured("")

    assert "bad combo" in app.detail_var.value
