from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from voxen.application import events as ev
from voxen.application.dictation import DictationService
from voxen.config import AppConfig
from voxen.domain.state import AppState, AppStateMachine


class FakeAudio:
    def __init__(self, audio=None, start_error: Exception | None = None) -> None:
        self.audio = audio if audio is not None else [1.0]
        self.start_error = start_error
        self.level = 0.0
        self.last_status = None
        self.start_calls = 0
        self.begin_calls = 0
        self.end_calls = 0
        self.close_calls = 0

    def start(self) -> None:
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error

    def begin(self) -> None:
        self.begin_calls += 1

    def end(self):
        self.end_calls += 1
        return self.audio

    def close(self) -> None:
        self.close_calls += 1


class FakeExecutor:
    def __init__(self) -> None:
        self.submissions: list[tuple] = []
        self.shutdown_calls: list[dict] = []

    def submit(self, function, *args):
        self.submissions.append((function, args))
        return None

    def shutdown(self, **kwargs) -> None:
        self.shutdown_calls.append(kwargs)

    def run_next(self) -> None:
        function, args = self.submissions.pop(0)
        function(*args)


class FakeTranscriber:
    def __init__(self, text: str = "ciao", error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.warm_calls = 0
        self.cancel_calls = 0
        self.unload_calls = 0

    def warm(self, config) -> None:
        self.warm_calls += 1
        if self.error is not None:
            raise self.error

    def transcribe(self, audio, config, language) -> str:
        if self.error is not None:
            raise self.error
        return self.text

    def cancel(self) -> None:
        self.cancel_calls += 1

    def unload(self) -> None:
        self.unload_calls += 1


class FakeProcessor:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def process(self, text, _options) -> str:
        if self.error is not None:
            raise self.error
        return text.strip()


class FakeInjector:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.texts: list[str] = []

    def inject(self, text: str) -> None:
        if self.error is not None:
            raise self.error
        self.texts.append(text)


def make_service(
    *,
    initial_state: AppState = AppState.READY,
    audio: FakeAudio | None = None,
    transcriber: FakeTranscriber | None = None,
    processor: FakeProcessor | None = None,
    injector: FakeInjector | None = None,
    executor: FakeExecutor | None = None,
    config: AppConfig | None = None,
) -> tuple[DictationService, FakeAudio, FakeExecutor, FakeInjector]:
    audio = audio or FakeAudio()
    transcriber = transcriber or FakeTranscriber()
    processor = processor or FakeProcessor()
    injector = injector or FakeInjector()
    executor = executor or FakeExecutor()
    config = config or AppConfig(language="it")
    service = DictationService(
        audio=audio,
        transcriber=transcriber,
        processor=processor,
        injector=injector,
        executor=executor,
        config=config,
    )
    service._state_machine = AppStateMachine(initial_state)
    return service, audio, executor, injector


def test_begin_recording_transitions_to_recording() -> None:
    service, audio, _executor, _injector = make_service()

    assert service.begin_recording() is True

    assert service.state is AppState.RECORDING
    assert audio.start_calls == 1
    assert audio.begin_calls == 1


def test_begin_recording_is_ignored_outside_ready() -> None:
    service, _audio, _executor, _injector = make_service(initial_state=AppState.PAUSED)

    assert service.begin_recording() is False
    assert service.state is AppState.PAUSED


def test_stop_recording_surfaces_an_audio_dropout() -> None:
    audio = FakeAudio()
    audio.last_status = "input overflow"
    service, _audio, _executor, _injector = make_service(initial_state=AppState.RECORDING, audio=audio)

    service.stop_recording()
    events = service.drain_events()

    assert ev.AudioDropout("input overflow") in events


def test_stop_recording_submits_transcription_and_moves_to_processing() -> None:
    service, audio, executor, _injector = make_service(initial_state=AppState.RECORDING)

    assert service.stop_recording() is True

    assert service.state is AppState.PROCESSING
    assert audio.end_calls == 1
    assert len(executor.submissions) == 1


def test_transcript_is_pasted_and_service_returns_to_ready() -> None:
    service, _audio, executor, injector = make_service(
        initial_state=AppState.RECORDING,
        transcriber=FakeTranscriber(text="  ciao mondo  "),
    )
    service.stop_recording()

    executor.run_next()
    events = service.drain_events()

    assert events == [ev.TranscriptPasted("ciao mondo")]
    assert injector.texts == ["ciao mondo"]
    assert service.state is AppState.READY


def test_no_speech_detected_returns_to_ready_without_injecting() -> None:
    service, _audio, executor, injector = make_service(
        initial_state=AppState.RECORDING,
        transcriber=FakeTranscriber(text="   "),
    )
    service.stop_recording()

    executor.run_next()
    events = service.drain_events()

    assert events == [ev.NoSpeechDetected()]
    assert injector.texts == []
    assert service.state is AppState.READY


def test_transcript_ready_event_when_auto_paste_disabled() -> None:
    service, _audio, executor, injector = make_service(
        initial_state=AppState.RECORDING,
        config=AppConfig(auto_paste=False),
    )
    service.stop_recording()

    executor.run_next()
    events = service.drain_events()

    assert events == [ev.TranscriptReady("ciao")]
    assert injector.texts == []
    assert service.state is AppState.READY


def test_paste_failure_is_reported_but_still_returns_to_ready() -> None:
    service, _audio, executor, _injector = make_service(
        initial_state=AppState.RECORDING,
        injector=FakeInjector(error=RuntimeError("clipboard busy")),
    )
    service.stop_recording()

    executor.run_next()
    events = service.drain_events()

    assert events == [ev.PasteFailed("clipboard busy")]
    assert service.state is AppState.READY


def test_transcription_failure_enters_error_state() -> None:
    service, _audio, executor, _injector = make_service(
        initial_state=AppState.RECORDING,
        transcriber=FakeTranscriber(error=RuntimeError("model crashed")),
    )
    service.stop_recording()

    executor.run_next()
    events = service.drain_events()

    assert events == [ev.TranscriptionFailed("model crashed")]
    assert service.state is AppState.ERROR


def test_engine_ready_moves_starting_to_ready_but_not_other_states() -> None:
    service, _audio, executor, _injector = make_service(initial_state=AppState.STARTING)
    service.start()

    executor.run_next()  # warm engine: EngineLoading + EngineReady
    events = service.drain_events()

    assert ev.EngineReady() in events
    assert service.state is AppState.READY


def test_engine_failure_enters_error_state() -> None:
    service, _audio, executor, _injector = make_service(
        initial_state=AppState.STARTING,
        transcriber=FakeTranscriber(error=RuntimeError("no GPU")),
    )
    service.start()

    executor.run_next()
    events = service.drain_events()

    assert events == [ev.EngineLoading(), ev.EngineFailed("no GPU")]
    assert service.state is AppState.ERROR


def test_audio_start_failure_is_reported_when_recording_begins() -> None:
    service, audio, executor, _injector = make_service(
        initial_state=AppState.READY,
        audio=FakeAudio(start_error=RuntimeError("no microphone")),
    )
    assert service.begin_recording() is False

    assert audio.start_calls == 1
    assert service.state is AppState.ERROR
    assert service.drain_events() == [ev.AudioFailed("no microphone")]


def test_start_only_warms_the_engine_without_opening_audio() -> None:
    service, audio, executor, _injector = make_service(initial_state=AppState.STARTING)
    service.start()

    assert audio.start_calls == 0
    assert len(executor.submissions) == 1


def test_pause_toggles_only_between_ready_and_paused() -> None:
    service, _audio, _executor, _injector = make_service(initial_state=AppState.READY)

    assert service.toggle_pause() is True
    assert service.state is AppState.PAUSED

    assert service.toggle_pause() is True
    assert service.state is AppState.READY


def test_pause_is_a_no_op_while_processing_or_in_error() -> None:
    service, _audio, _executor, _injector = make_service(initial_state=AppState.PROCESSING)
    assert service.toggle_pause() is False
    assert service.state is AppState.PROCESSING

    service, _audio, _executor, _injector = make_service(initial_state=AppState.ERROR)
    assert service.toggle_pause() is False
    assert service.state is AppState.ERROR


def test_drain_events_ignores_events_once_closing() -> None:
    service, _audio, executor, _injector = make_service(initial_state=AppState.RECORDING)
    service.stop_recording()
    service._state_machine = AppStateMachine(AppState.CLOSING)

    executor.run_next()
    assert service.drain_events() == []


def test_shutdown_is_idempotent_and_cancels_pending_work() -> None:
    service, audio, executor, _injector = make_service(initial_state=AppState.READY)

    service.shutdown()
    service.shutdown()

    assert service.state is AppState.CLOSING
    assert audio.close_calls == 1
    assert executor.shutdown_calls == [{"wait": False, "cancel_futures": True}]


def test_shutdown_does_not_wait_for_an_active_transcription() -> None:
    started = threading.Event()
    release = threading.Event()

    class BlockingTranscriber(FakeTranscriber):
        def transcribe(self, audio, config, language) -> str:
            started.set()
            release.wait(timeout=2)
            return "done"

    service, _audio, _executor, _injector = make_service(
        initial_state=AppState.PROCESSING,
        transcriber=BlockingTranscriber(),
        executor=ThreadPoolExecutor(max_workers=1),
    )
    service._submit(service._transcribe, [], None, "auto")
    assert started.wait(timeout=1)

    started_closing = time.monotonic()
    service.shutdown()
    close_duration = time.monotonic() - started_closing

    assert close_duration < 0.5
    assert service.state is AppState.CLOSING
    assert service._transcriber.unload_calls == 0

    release.set()
