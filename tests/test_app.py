from __future__ import annotations

import queue
from types import SimpleNamespace

from voxen.app import VoxenApp
from voxen.state import AppState, AppStateMachine


class FakeVar:
    def __init__(self, value="") -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class FakeRecorder:
    level = 0.0

    def __init__(self, audio=None) -> None:
        self.audio = audio if audio is not None else [1.0]
        self.begin_calls = 0
        self.end_calls = 0
        self.close_calls = 0

    def begin(self) -> None:
        self.begin_calls += 1

    def end(self):
        self.end_calls += 1
        return self.audio

    def close(self) -> None:
        self.close_calls += 1


class FakeExecutor:
    def __init__(self) -> None:
        self.submissions = []
        self.shutdown_calls = []

    def submit(self, function, *args) -> None:
        self.submissions.append((function, args))

    def shutdown(self, **kwargs) -> None:
        self.shutdown_calls.append(kwargs)


class FakeProcessor:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def process(self, text, _options) -> str:
        if self.error is not None:
            raise self.error
        return text.strip()


class FakeInjector:
    def __init__(self) -> None:
        self.texts = []

    def inject(self, text: str) -> None:
        self.texts.append(text)


class FakeRoot:
    def __init__(self) -> None:
        self.scheduled = []
        self.destroy_calls = 0

    def after(self, delay, callback):
        self.scheduled.append((delay, callback))
        return len(self.scheduled)

    def destroy(self) -> None:
        self.destroy_calls += 1


class FakeLifecycleService:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


def make_app(initial_state: AppState = AppState.READY) -> VoxenApp:
    app = object.__new__(VoxenApp)
    app._state_machine = AppStateMachine(initial_state)
    app.config = SimpleNamespace(
        hotkey="ctrl+space",
        model="base",
        device="auto",
        compute_type="int8",
        language="it",
        punctuation=True,
        auto_paste=True,
    )
    app.recorder = FakeRecorder()
    app.executor = FakeExecutor()
    app.root = FakeRoot()
    app.processor = FakeProcessor()
    app.injector = FakeInjector()
    app.events = queue.Queue()
    app.status_var = FakeVar()
    app.detail_var = FakeVar()
    app.overlay_var = FakeVar()
    app.overlay_hint_var = FakeVar()
    app.overlay_level_var = FakeVar()
    app.overlay_mode = "listening"
    app.started_at = 0.0
    app.overlay_animation_id = None
    app.capturing_hotkey = False
    app.hotkey_capture_binding = None
    app.hotkey = None
    app.tray = None
    app.model_manager = SimpleNamespace(cancel=lambda: None, unload=lambda: None)
    app._show_overlay = lambda: None
    app._hide_overlay = lambda: None
    return app


def test_app_transitions_from_ready_to_recording_to_processing() -> None:
    app = make_app()

    app._start_recording()
    assert app.state is AppState.RECORDING
    assert app.recorder.begin_calls == 1

    app._stop_recording()
    assert app.state is AppState.PROCESSING
    assert app.recorder.end_calls == 1
    assert len(app.executor.submissions) == 1


def test_app_finishes_transcript_and_returns_to_ready() -> None:
    app = make_app(AppState.PROCESSING)
    app._finish_transcript("  hello  ")

    assert app.state is AppState.READY
    assert app.injector.texts == ["hello"]


def test_app_pause_toggles_only_from_ready() -> None:
    app = make_app()

    app._toggle_pause()
    assert app.state is AppState.PAUSED

    app._toggle_pause()
    assert app.state is AppState.READY


def test_app_drains_transcript_event_on_ui_thread() -> None:
    app = make_app(AppState.PROCESSING)
    app.events.put(("transcript", "queued text"))

    app._drain_events()

    assert app.state is AppState.READY
    assert app.injector.texts == ["queued text"]
    assert app.root.scheduled


def test_app_stays_starting_while_model_is_loading() -> None:
    app = make_app(AppState.STARTING)
    app.events.put(("model_loading", None))

    app._drain_events()

    assert app.state is AppState.STARTING
    assert app.status_var.value == "Starting..."


def test_app_enters_error_when_model_loading_fails() -> None:
    app = make_app(AppState.STARTING)
    app.events.put(("model_error", "download failed"))

    app._drain_events()

    assert app.state is AppState.ERROR
    assert "download failed" in app.detail_var.value


def test_app_enters_error_when_processing_fails() -> None:
    app = make_app(AppState.PROCESSING)
    app.processor = FakeProcessor(RuntimeError("processor failed"))
    app.events.put(("transcript", "hello"))

    app._drain_events()

    assert app.state is AppState.ERROR
    assert app.detail_var.value == "processor failed"


def test_app_ignores_recording_start_while_paused_or_processing() -> None:
    app = make_app()

    app.state = AppState.PAUSED
    app._start_recording()
    processing_app = make_app(AppState.PROCESSING)
    processing_app._start_recording()

    assert app.recorder.begin_calls == 0
    assert processing_app.recorder.begin_calls == 0


def test_app_shutdown_is_ordered_and_idempotent() -> None:
    app = make_app()
    app.hotkey = FakeLifecycleService()
    app.tray = FakeLifecycleService()

    app.close()
    app.close()

    assert app.state is AppState.CLOSING
    assert app.recorder.close_calls == 1
    assert app.hotkey.stop_calls == 1
    assert app.tray.stop_calls == 1
    assert app.executor.shutdown_calls == [{"wait": True, "cancel_futures": True}]
    assert app.root.destroy_calls == 1
