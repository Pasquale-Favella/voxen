"""The dictation use case: hold hotkey -> speak -> release -> text pasted.

Before this module existed, this flow was spread across five private
methods of ``VoxenApp`` (``_start_recording``, ``_stop_recording``,
``_transcribe``, ``_drain_events``, ``_finish_transcript``), interleaved
with Tkinter ``StringVar`` mutations and only reachable in tests via
``object.__new__(VoxenApp)`` plus manually injecting two dozen private
attributes. ``DictationService`` is the same orchestration with no Tkinter,
no thread affinity requirements beyond "call ``drain_events`` from whichever
thread owns the clipboard/paste side effects" (the UI thread, in practice),
and it is constructible with five small fakes.
"""

from __future__ import annotations

import logging
import queue
from collections.abc import Callable
from threading import Lock

from ..config import AppConfig
from ..domain.state import AppState, AppStateMachine
from ..domain.text import ProcessingOptions
from ..stt import ModelConfig
from . import events as ev
from .ports import AudioSource, TextInjector, TextNormalizer, Transcriber

logger = logging.getLogger(__name__)


class DictationService:
    def __init__(
        self,
        *,
        audio: AudioSource,
        transcriber: Transcriber,
        processor: TextNormalizer,
        injector: TextInjector,
        executor,
        config: AppConfig,
    ) -> None:
        self._audio = audio
        self._transcriber = transcriber
        self._processor = processor
        self._injector = injector
        self._executor = executor
        self._config = config
        self._state_machine = AppStateMachine()
        self._events: queue.Queue[ev.DictationEvent] = queue.Queue()
        self._pending_futures: set = set()
        self._future_lock = Lock()
        self._unload_started = False

    @property
    def state(self) -> AppState:
        return self._state_machine.current

    @property
    def audio_level(self) -> float:
        return self._audio.level

    @property
    def audio_status(self) -> str | None:
        return self._audio.last_status

    def _model_config(self) -> ModelConfig:
        return ModelConfig(self._config.model, self._config.device, self._config.compute_type)

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        self._submit(self._warm_engine)

    def shutdown(self) -> None:
        if self.state is AppState.CLOSING:
            return
        if self.state is AppState.RECORDING:
            self._run_step("end the active recording", self._audio.end)
        self._state_machine.transition(AppState.CLOSING)
        for description, step in (
            ("cancel the transcriber", self._transcriber.cancel),
            ("shut down the worker pool", lambda: self._executor.shutdown(wait=False, cancel_futures=True)),
            ("close the audio stream", self._audio.close),
            ("unload the model", self._unload_model_if_ready),
        ):
            self._run_step(description, step)

    @staticmethod
    def _run_step(description: str, step: Callable[[], None]) -> None:
        try:
            step()
        except Exception:
            logger.exception("Failed to %s during shutdown", description)

    # -- recording -------------------------------------------------------

    def begin_recording(self) -> bool:
        if self.state is not AppState.READY:
            return False
        try:
            self._audio.start()
            self._audio.begin()
        except Exception as exc:
            self._run_step("close the audio stream after recording start failure", self._audio.close)
            self._state_machine.transition(AppState.ERROR)
            self._events.put(ev.AudioFailed(str(exc)))
            return False
        self._state_machine.transition(AppState.RECORDING)
        return True

    def stop_recording(self) -> bool:
        if self.state is not AppState.RECORDING:
            return False
        self._state_machine.transition(AppState.PROCESSING)
        try:
            audio = self._audio.end()
        except Exception as exc:
            self._state_machine.transition(AppState.ERROR)
            self._events.put(ev.AudioFailed(str(exc)))
            return False
        status = self._audio.last_status
        if status is not None:
            self._events.put(ev.AudioDropout(status))
        self._submit(self._transcribe, audio, self._model_config(), self._config.language)
        return True

    def toggle_pause(self) -> bool:
        if self.state is AppState.RECORDING:
            self.stop_recording()
        if self.state is AppState.READY:
            self._state_machine.transition(AppState.PAUSED)
            return True
        if self.state is AppState.PAUSED:
            self._state_machine.transition(AppState.READY)
            return True
        return False

    # -- background work --------------------------------------------------

    def _submit(self, function, *args) -> None:
        future = self._executor.submit(function, *args)
        if future is None:
            return
        with self._future_lock:
            self._pending_futures.add(future)
        future.add_done_callback(self._future_finished)

    def _future_finished(self, future) -> None:
        with self._future_lock:
            self._pending_futures.discard(future)
        self._unload_model_if_ready()

    def _unload_model_if_ready(self) -> None:
        with self._future_lock:
            if self.state is not AppState.CLOSING or self._pending_futures or self._unload_started:
                return
            self._unload_started = True
        self._transcriber.unload()

    def _warm_engine(self) -> None:
        try:
            self._events.put(ev.EngineLoading())
            self._transcriber.warm(self._model_config())
            self._events.put(ev.EngineReady())
        except Exception as exc:
            self._events.put(ev.EngineFailed(str(exc)))

    def _transcribe(self, audio, model_config: ModelConfig, language: str) -> None:
        try:
            raw_text = self._transcriber.transcribe(audio, model_config, language)
            self._finish_transcript(raw_text)
        except Exception as exc:
            self._events.put(ev.TranscriptionFailed(str(exc)))

    def _finish_transcript(self, raw_text: str) -> None:
        options = ProcessingOptions(capitalization=True, punctuation=self._config.punctuation)
        text = self._processor.process(raw_text, options)
        if not text:
            self._events.put(ev.NoSpeechDetected())
            return
        if not self._config.auto_paste:
            self._events.put(ev.TranscriptReady(text))
            return
        try:
            self._injector.inject(text)
            self._events.put(ev.TranscriptPasted(text))
        except RuntimeError as exc:
            self._events.put(ev.PasteFailed(str(exc)))

    # -- event draining (call from the thread that owns paste side effects) --

    def drain_events(self) -> list[ev.DictationEvent]:
        if self.state is AppState.CLOSING:
            return []
        drained: list[ev.DictationEvent] = []
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            drained.append(event)
            self._apply(event)
        return drained

    def _apply(self, event: ev.DictationEvent) -> None:
        try:
            if isinstance(event, ev.EngineReady) and self.state is AppState.STARTING:
                self._state_machine.transition(AppState.READY)
            elif isinstance(event, ev.EngineFailed):
                self._state_machine.transition(AppState.ERROR)
            elif isinstance(event, ev.TranscriptionFailed):
                self._state_machine.transition(AppState.ERROR)
            elif isinstance(event, (ev.NoSpeechDetected, ev.TranscriptPasted, ev.TranscriptReady, ev.PasteFailed)):
                if self.state is AppState.PROCESSING:
                    self._state_machine.transition(AppState.READY)
        except Exception as exc:
            logger.exception("Failed to apply dictation event %r", event)
            self._events.put(ev.UnexpectedError(str(exc)))
            try:
                self._state_machine.transition(AppState.ERROR)
            except Exception:
                pass
