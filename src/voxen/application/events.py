"""Outcomes of the dictation use case, for the presentation layer to render.

These replace the ``("kind", payload)`` string-tagged tuples that used to
travel through ``VoxenApp``'s event queue. A typo in a string tag was
silently treated as an unknown/error event; a typo in one of these class
names is a ``NameError`` at import time, and a new event type that a caller
forgets to handle is a lint/type-checker finding instead of a runtime
"unless a fallback branch happens to catch it" situation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineLoading:
    """The transcription model is being downloaded or loaded."""


@dataclass(frozen=True)
class EngineReady:
    """The transcription model finished loading and can be used."""


@dataclass(frozen=True)
class EngineFailed:
    message: str


@dataclass(frozen=True)
class AudioFailed:
    """The microphone could not be started."""

    message: str


@dataclass(frozen=True)
class AudioDropout:
    """The mic input stream reported a problem (e.g. an overflow) during a recording."""

    message: str


@dataclass(frozen=True)
class NoSpeechDetected:
    """A recording finished but produced no usable transcript."""


@dataclass(frozen=True)
class TranscriptPasted:
    text: str


@dataclass(frozen=True)
class TranscriptReady:
    """A transcript is available but automatic paste is disabled."""

    text: str


@dataclass(frozen=True)
class PasteFailed:
    message: str


@dataclass(frozen=True)
class TranscriptionFailed:
    message: str


@dataclass(frozen=True)
class UnexpectedError:
    message: str


DictationEvent = (
    EngineLoading
    | EngineReady
    | EngineFailed
    | AudioFailed
    | AudioDropout
    | NoSpeechDetected
    | TranscriptPasted
    | TranscriptReady
    | PasteFailed
    | TranscriptionFailed
    | UnexpectedError
)
