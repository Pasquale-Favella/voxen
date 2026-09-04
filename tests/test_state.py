import pytest

from voxen.state import AppState, AppStateMachine, InvalidStateTransitionError


def test_app_state_contains_the_application_lifecycle() -> None:
    assert {state.name for state in AppState} == {
        "STARTING",
        "READY",
        "RECORDING",
        "PROCESSING",
        "PAUSED",
        "ERROR",
        "CLOSING",
    }


def test_state_machine_allows_the_recording_lifecycle() -> None:
    machine = AppStateMachine()

    machine.transition(AppState.READY)
    machine.transition(AppState.RECORDING)
    machine.transition(AppState.PROCESSING)
    machine.transition(AppState.READY)

    assert machine.current is AppState.READY


def test_state_machine_rejects_invalid_transitions() -> None:
    machine = AppStateMachine()

    with pytest.raises(InvalidStateTransitionError):
        machine.transition(AppState.PROCESSING)