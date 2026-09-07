from enum import Enum, auto


class AppState(Enum):
    STARTING = auto()
    READY = auto()
    RECORDING = auto()
    PROCESSING = auto()
    PAUSED = auto()
    ERROR = auto()
    CLOSING = auto()


class InvalidStateTransitionError(RuntimeError):
    pass


class AppStateMachine:
    _transitions = {
        AppState.STARTING: {AppState.READY, AppState.ERROR, AppState.CLOSING},
        AppState.READY: {AppState.RECORDING, AppState.PAUSED, AppState.ERROR, AppState.CLOSING},
        AppState.RECORDING: {AppState.PROCESSING, AppState.ERROR, AppState.CLOSING},
        AppState.PROCESSING: {AppState.READY, AppState.ERROR, AppState.CLOSING},
        AppState.PAUSED: {AppState.READY, AppState.ERROR, AppState.CLOSING},
        AppState.ERROR: {AppState.STARTING, AppState.READY, AppState.CLOSING},
        AppState.CLOSING: set(),
    }

    def __init__(self, initial: AppState = AppState.STARTING) -> None:
        self.current = initial

    def transition(self, next_state: AppState) -> None:
        if next_state is self.current:
            return
        if next_state not in self._transitions[self.current]:
            raise InvalidStateTransitionError(
                f"Transizione non valida: {self.current.name} -> {next_state.name}."
            )
        self.current = next_state