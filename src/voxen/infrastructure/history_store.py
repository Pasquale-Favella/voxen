from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path
from threading import RLock

from ..domain.history import TranscriptRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'auto',
    model TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transcripts_created_at ON transcripts (created_at DESC);
"""

_MAX_TEXT_CHARS = 10_000


def default_path() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Voxen"
    else:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Voxen"
    return base / "history.db"


class SqliteHistoryStore:
    """Local-first transcript history. No network, single file, WAL off.

    Thread-safe for the Voxen pattern: ``save`` is called from the STT
    worker thread, ``recent``/``search`` from the UI thread.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()
        self._lock = RLock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        conn.execute("PRAGMA journal_mode=DELETE")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        if self._initialized:
            return
        conn.executescript(_SCHEMA)
        conn.commit()
        self._initialized = True

    def save(self, text: str, *, language: str = "auto", model: str = "") -> TranscriptRecord:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Cannot save an empty transcript.")
        if len(cleaned) > _MAX_TEXT_CHARS:
            cleaned = cleaned[:_MAX_TEXT_CHARS]
        created_at = time.time()
        with self._lock:
            conn = self._connect()
            try:
                self._ensure_schema(conn)
                cursor = conn.execute(
                    "INSERT INTO transcripts (text, language, model, created_at) VALUES (?, ?, ?, ?)",
                    (cleaned, language, model, created_at),
                )
                conn.commit()
                return TranscriptRecord(
                    id=int(cursor.lastrowid or 0),
                    text=cleaned,
                    language=language,
                    model=model,
                    created_at=created_at,
                )
            finally:
                conn.close()

    def _rows_to_records(self, rows: list[tuple]) -> list[TranscriptRecord]:
        return [
            TranscriptRecord(id=int(row[0]), text=str(row[1]), language=str(row[2]), model=str(row[3]), created_at=float(row[4]))
            for row in rows
        ]

    def recent(self, limit: int = 20) -> list[TranscriptRecord]:
        limit = max(1, min(int(limit), 200))
        with self._lock:
            conn = self._connect()
            try:
                self._ensure_schema(conn)
                rows = conn.execute(
                    "SELECT id, text, language, model, created_at FROM transcripts ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                return self._rows_to_records(rows)
            finally:
                conn.close()

    def search(self, query: str, limit: int = 20) -> list[TranscriptRecord]:
        cleaned = query.strip()
        if not cleaned:
            return self.recent(limit)
        limit = max(1, min(int(limit), 200))
        with self._lock:
            conn = self._connect()
            try:
                self._ensure_schema(conn)
                escaped = cleaned.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                pattern = "%" + escaped + "%"
                rows = conn.execute(
                    "SELECT id, text, language, model, created_at FROM transcripts "
                    "WHERE text LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ?",
                    (pattern, limit),
                ).fetchall()
                return self._rows_to_records(rows)
            finally:
                conn.close()

    def delete(self, record_id: int) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                self._ensure_schema(conn)
                cursor = conn.execute("DELETE FROM transcripts WHERE id = ?", (int(record_id),))
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def clear(self) -> int:
        with self._lock:
            conn = self._connect()
            try:
                self._ensure_schema(conn)
                cursor = conn.execute("DELETE FROM transcripts")
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()

    def prune(self, keep: int = 200) -> int:
        """Keep only the newest ``keep`` rows. Returns rows removed."""
        keep = max(1, int(keep))
        with self._lock:
            conn = self._connect()
            try:
                self._ensure_schema(conn)
                cursor = conn.execute(
                    "DELETE FROM transcripts WHERE id NOT IN "
                    "(SELECT id FROM transcripts ORDER BY id DESC LIMIT ?)",
                    (keep,),
                )
                conn.commit()
                return cursor.rowcount
            finally:
                conn.close()
