from __future__ import annotations

import pytest

from voxen.domain.history import NullHistoryStore
from voxen.infrastructure.history_store import SqliteHistoryStore


def test_save_and_recent_round_trip(tmp_path) -> None:
    store = SqliteHistoryStore(tmp_path / "history.db")

    first = store.save("ciao mondo", language="it", model="base")
    second = store.save("secondo testo", language="it", model="base")

    assert first.id > 0
    assert second.id > first.id

    records = store.recent(10)
    assert [r.text for r in records] == ["secondo testo", "ciao mondo"]
    assert records[0].language == "it"


def test_search_matches_substrings_and_empty_query_returns_recent(tmp_path) -> None:
    store = SqliteHistoryStore(tmp_path / "history.db")
    store.save("appuntamento dal dentista", language="it", model="base")
    store.save("comprare il latte", language="it", model="base")

    assert [r.text for r in store.search("dentista")] == ["appuntamento dal dentista"]
    assert len(store.search("")) == 2
    assert store.search("inesistente") == []


def test_delete_and_clear(tmp_path) -> None:
    store = SqliteHistoryStore(tmp_path / "history.db")
    record = store.save("da cancellare", language="it", model="base")
    store.save("da tenere", language="it", model="base")

    assert store.delete(record.id) is True
    assert store.delete(999999) is False
    assert [r.text for r in store.recent()] == ["da tenere"]

    assert store.clear() == 1
    assert store.recent() == []


def test_save_rejects_empty_text(tmp_path) -> None:
    store = SqliteHistoryStore(tmp_path / "history.db")
    with pytest.raises(ValueError):
        store.save("   ", language="it", model="base")


def test_prune_keeps_newest_rows(tmp_path) -> None:
    store = SqliteHistoryStore(tmp_path / "history.db")
    for index in range(5):
        store.save(f"text {index}", language="it", model="base")

    assert store.prune(keep=2) == 3
    assert [r.text for r in store.recent()] == ["text 4", "text 3"]


def test_null_store_never_persists() -> None:
    store = NullHistoryStore()
    record = store.save("ciao", language="it", model="base")

    assert record.text == "ciao"
    assert store.recent() == []
    assert store.search("ciao") == []
    assert store.delete(1) is False
    assert store.clear() == 0
