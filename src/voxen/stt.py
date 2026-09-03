from __future__ import annotations


class FasterWhisperEngine:
    def __init__(self, model: str, device: str = "auto", compute_type: str = "int8") -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def load(self) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("Installa faster-whisper per usare la trascrizione locale.") from exc
        device = "cpu" if self.device == "auto" else self.device
        self._model = WhisperModel(self.model_name, device=device, compute_type=self.compute_type)

    def transcribe(self, audio, language: str = "auto") -> str:
        if self._model is None:
            self.load()
        segments, _info = self._model.transcribe(
            audio,
            language=None if language == "auto" else language,
            vad_filter=True,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def unload(self) -> None:
        self._model = None
