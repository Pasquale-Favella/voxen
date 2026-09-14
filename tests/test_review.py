"""Review draft + history: the PROCESSING -> REVIEWING -> READY loop."""

from __future__ import annotations

from test_dictation import FakeAudio, FakeExecutor, FakeInjector, FakeProcessor, FakeTranscriber

from voxen.application import events as ev
from voxen.config import AppConfig
from voxen.domain.history import NullHistoryStore
from voxen.domain.state import AppState
from voxen.infrastructure.history_store import SqliteHistoryStore


def make_review_service(*, text: str = "ciao mondo", paste_mode: str = "review", tmp_path=None, history=None):
    from voxen.application.dictation import DictationService
    from voxen.domain.state import AppStateMachine

    config = AppConfig(language="it", paste_mode=paste_mode)
    if history is None:
        history = SqliteHistoryStore(tmp_path / "history.db") if tmp_path is not None else NullHistoryStore()
    audio = FakeAudio()
    executor = FakeExecutor()
    injector = FakeInjector()
    service = DictationService(
        audio=audio,
        transcriber=FakeTranscriber(text=text),
        processor=FakeProcessor(),
        injector=injector,
        executor=executor,
        config=config,
        history=history,
    )
    service._state_machine = AppStateMachine(AppState.RECORDING)
    return service, audio, executor, injector, history


def test_review_mode_holds_draft_instead_of_pasting() -> None:
    service, _audio, executor, injector, _history = make_review_service(paste_mode="review")

    assert service.stop_recording() is True
    executor.run_next()
    events = service.drain_events()

    assert events == [ev.TranscriptDraft("ciao mondo")]
    assert service.state is AppState.REVIEWING
    assert service.draft == "ciao mondo"
    assert injector.texts == []


def test_confirm_draft_pastes_and_returns_to_ready() -> None:
    service, _audio, executor, injector, _history = make_review_service(paste_mode="review")
    service.stop_recording()
    executor.run_next()
    service.drain_events()

    assert service.confirm_draft() is True
    events = service.drain_events()

    assert events == [ev.TranscriptPasted("ciao mondo")]
    assert injector.texts == ["ciao mondo"]
    assert service.state is AppState.READY
    assert service.draft is None


def test_confirm_draft_applies_edits() -> None:
    service, _audio, executor, injector, _history = make_review_service(paste_mode="review")
    service.stop_recording()
    executor.run_next()
    service.drain_events()

    assert service.confirm_draft("ciao mondo corretto") is True

    assert injector.texts == ["ciao mondo corretto"]
    assert service.drain_events() == [ev.TranscriptPasted("ciao mondo corretto")]


def test_discard_draft_returns_to_ready_without_pasting() -> None:
    service, _audio, executor, injector, _history = make_review_service(paste_mode="review")
    service.stop_recording()
    executor.run_next()
    service.drain_events()

    assert service.discard_draft() is True
    assert service.drain_events() == [ev.DraftDiscarded()]
    assert injector.texts == []
    assert service.state is AppState.READY


def test_auto_mode_still_pastes_immediately() -> None:
    service, _audio, executor, injector, _history = make_review_service(paste_mode="auto")

    service.stop_recording()
    executor.run_next()

    assert service.drain_events() == [ev.TranscriptPasted("ciao mondo")]
    assert service.state is AppState.READY


def test_smart_mode_reviews_only_long_drafts() -> None:
    short, _, executor, _, _ = make_review_service(text="ok", paste_mode="smart")
    short.stop_recording()
    executor.run_next()
    assert short.drain_events() == [ev.TranscriptPasted("ok")]

    long_text = "x" * 120
    long_service, _, long_executor, _, _ = make_review_service(text=long_text, paste_mode="smart")
    long_service.stop_recording()
    long_executor.run_next()
    assert long_service.drain_events() == [ev.TranscriptDraft(long_text)]
    assert long_service.state is AppState.REVIEWING


def test_begin_recording_is_blocked_while_reviewing() -> None:
    service, _audio, _executor, _injector, _history = make_review_service(paste_mode="review")

    assert service.stop_recording() is True
    service._finish_transcript("ciao")
    service.drain_events()
    assert service.state is AppState.REVIEWING
    assert service.begin_recording() is False


def test_transcript_is_saved_to_history(tmp_path) -> None:
    service, _audio, executor, _injector, history = make_review_service(paste_mode="auto", tmp_path=tmp_path)

    service.stop_recording()
    executor.run_next()
    service.drain_events()

    assert [r.text for r in history.recent()] == ["ciao mondo"]


def test_draft_is_saved_to_history_before_review(tmp_path) -> None:
    service, _audio, executor, _injector, history = make_review_service(paste_mode="review", tmp_path=tmp_path)

    service.stop_recording()
    executor.run_next()
    service.drain_events()

    assert service.state is AppState.REVIEWING
    assert [r.text for r in history.recent()] == ["ciao mondo"]


def test_history_failure_never_breaks_dictation() -> None:
    class BoomHistory(NullHistoryStore):
        def save(self, text, *, language, model):
            raise OSError("disk full")

    service, _audio, executor, injector, _history = make_review_service(paste_mode="auto", history=BoomHistory())

    service.stop_recording()
    executor.run_next()

    assert service.drain_events() == [ev.TranscriptPasted("ciao mondo")]
    assert injector.texts == ["ciao mondo"]


def test_repaste_from_history_works_in_ready() -> None:
    service, _audio, _executor, injector, _history = make_review_service(paste_mode="auto")
    service._state_machine.current = AppState.READY

    assert service.repaste("vecchio testo") is True
    assert injector.texts == ["vecchio testo"]
    assert service.drain_events() == [ev.TranscriptPasted("vecchio testo")]


def test_repaste_is_blocked_while_reviewing() -> None:
    service, _audio, executor, _injector, _history = make_review_service(paste_mode="review")
    service.stop_recording()
    executor.run_next()
    service.drain_events()
    assert service.state is AppState.REVIEWING

    assert service.repaste("altro") is False


# -- presentation wiring (no Tk): VoxenApp handlers ------------------------


class _FakeVar:
    def __init__(self, value="") -> None:
        self.value = value

    def get(self):
        return self.value

    def set(self, value) -> None:
        self.value = value


class _FakeOverlay:
    def __init__(self) -> None:
        self.hide_calls = 0

    def hide(self) -> None:
        self.hide_calls += 1


class _FakeReviewWindow:
    def __init__(self) -> None:
        self.shown: list[str] = []
        self.hide_calls = 0

    def show(self, draft: str) -> None:
        self.shown.append(draft)

    def hide(self) -> None:
        self.hide_calls += 1


class _FakeListbox:
    def __init__(self) -> None:
        self.items: list[str] = []
        self.selected: tuple = ()

    def delete(self, _a, _b) -> None:
        self.items = []

    def insert(self, _index, text: str) -> None:
        self.items.append(text)

    def curselection(self):
        return self.selected


class _FakeAppDictation:
    def __init__(self) -> None:
        self.confirmed: list[str] = []
        self.discarded = 0
        self.repasted: list[str] = []
        self._history = [("primo",), ("secondo",)]

    def confirm_draft(self, text: str) -> bool:
        self.confirmed.append(text)
        return True

    def discard_draft(self) -> bool:
        self.discarded += 1
        return True

    def repaste(self, text: str) -> bool:
        self.repasted.append(text)
        return True

    def recent_history(self, limit: int = 30):
        from voxen.domain.history import TranscriptRecord

        return [
            TranscriptRecord(id=i + 1, text=t[0], language="it", model="base", created_at=0.0)
            for i, t in enumerate(self._history)
        ]


def _make_wired_app():
    import queue as _queue

    from voxen.app import VoxenApp

    app = object.__new__(VoxenApp)
    app.dictation = _FakeAppDictation()
    app.status_var = _FakeVar()
    app.detail_var = _FakeVar()
    app.overlay = _FakeOverlay()
    app.review_window = _FakeReviewWindow()
    app.history_list = _FakeListbox()
    app._history_cache = []
    app.events = _queue.Queue()
    return app


def test_draft_event_shows_review_window() -> None:
    app = _make_wired_app()

    app._on_transcript_draft(ev.TranscriptDraft("bozza da rivedere"))

    assert app.review_window.shown == ["bozza da rivedere"]
    assert app.status_var.value == "Review"


def test_draft_event_without_window_auto_confirms() -> None:
    app = _make_wired_app()
    app.review_window = None

    app._on_transcript_draft(ev.TranscriptDraft("auto"))

    assert app.dictation.confirmed == ["auto"]


def test_confirm_review_forwards_edits() -> None:
    app = _make_wired_app()

    app._confirm_review("testo corretto")

    assert app.dictation.confirmed == ["testo corretto"]
    assert app.review_window.hide_calls == 1


def test_refresh_history_fills_listbox() -> None:
    app = _make_wired_app()

    app._refresh_history()

    assert app.history_list.items == ["primo", "secondo"]


def test_repaste_selected_uses_cache() -> None:
    app = _make_wired_app()
    app._refresh_history()
    app.history_list.selected = (1,)

    app._repaste_selected()

    assert app.dictation.repasted == ["secondo"]


def test_repaste_without_selection_hints() -> None:
    app = _make_wired_app()
    app._refresh_history()
    app.history_list.selected = ()

    app._repaste_selected()

    assert "Select" in app.detail_var.value


def test_paste_failed_with_text_points_to_history() -> None:
    app = _make_wired_app()

    app._on_paste_failed(ev.PasteFailed("clipboard busy", "testo perso? no"))

    assert "History" in app.detail_var.value
