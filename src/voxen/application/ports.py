"""Ports the dictation use case depends on.

``DictationService`` (dictation.py) is written against these Protocols, not
against ``AudioRecorder``/``ModelManager``/``TextProcessor``/``ClipboardInjector``
directly. Those infrastructure classes already happen to satisfy them
structurally, so nothing about their implementation has to change — but the
application layer no longer imports a single concrete infrastructure class,
which is what lets it be unit-tested with five small fakes and no Tkinter,
no microphone, and no Whisper model.
"""

from __future__ import annotations

from typing import Protocol


class AudioSource(Protocol):
    level: float

    def start(self) -> None: ...

    def begin(self) -> None: ...

    def end(self) -> object: ...

    def close(self) -> None: ...

    @property
    def last_status(self) -> str | None: ...


class Transcriber(Protocol):
    def warm(self, config: object) -> None: ...

    def transcribe(self, audio: object, config: object, language: str) -> str: ...

    def cancel(self) -> None: ...

    def unload(self) -> None: ...


class TextNormalizer(Protocol):
    def process(self, text: str, options: object) -> str: ...


class TextInjector(Protocol):
    def inject(self, text: str) -> None: ...
