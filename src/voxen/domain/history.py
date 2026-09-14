from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranscriptRecord:
    """One saved dictation result.

    ``id`` is the storage row id (0 when not yet persisted).
    ``created_at`` is seconds since the epoch (UTC).
    """

    id: int
    text: str
    language: str
    model: str
    created_at: float


class HistoryStore(Protocol):
    """Persistence port for past transcripts.

    ``DictationService`` depends on this Protocol, not on sqlite.
    Implementations must never raise for empty queries; persistence
    failures are reported by raising ``OSError`` from ``save`` only —
    the service treats those as best-effort and keeps dictating.
    """

    def save(self, text: str, *, language: str, model: str) -> TranscriptRecord: ...
    def recent(self, limit: int = 20) -> list[TranscriptRecord]: ...
    def search(self, query: str, limit: int = 20) -> list[TranscriptRecord]: ...
    def delete(self, record_id: int) -> bool: ...
    def clear(self) -> int: ...


class NullHistoryStore:
    """No-op history used when persistence is disabled or unavailable."""

    def save(self, text: str, *, language: str, model: str) -> TranscriptRecord:
        import time

        return TranscriptRecord(id=0, text=text, language=language, model=model, created_at=time.time())

    def recent(self, limit: int = 20) -> list[TranscriptRecord]:
        return []

    def search(self, query: str, limit: int = 20) -> list[TranscriptRecord]:
        return []

    def delete(self, record_id: int) -> bool:
        return False

    def clear(self) -> int:
        return 0
