"""Local Whisper transcription in a bounded background worker."""

from typing import Any

from app.config import Settings
from app.exceptions import ServiceUnavailable
from app.infrastructure.worker import BlockingWorker


class WhisperSTT:
    """Load one base/small model and serialize inference calls."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.worker = BlockingWorker("whisper")
        self.model: Any = None

    def _load(self) -> None:
        import whisper

        self.model = whisper.load_model(self.settings.whisper_model,
            device=self.settings.whisper_device,
            download_root=str(self.settings.data_dir / "models" / "whisper"))

    async def initialize(self) -> None:
        """Download weights if necessary and warm the model before listening."""
        try:
            await self.worker.run(self._load)
        except Exception as exc:
            raise ServiceUnavailable("Whisper não iniciou. Verifique os pesos, PyTorch e o dispositivo CPU/CUDA.") from exc

    def _transcribe(self, audio: Any) -> str:
        import numpy as np

        if self.model is None:
            raise RuntimeError("Whisper não inicializado.")
        waveform = np.asarray(audio, dtype=np.float32)
        if waveform.ndim != 1 or not np.isfinite(waveform).all():
            raise ValueError("Áudio deve ser mono, float32 e finito.")
        if waveform.size == 0:
            return ""
        if waveform.size > self.settings.audio_sample_rate * self.settings.max_record_seconds + 1600:
            raise ValueError("Áudio excedeu a duração máxima.")
        result = self.model.transcribe(waveform, language=self.settings.whisper_language,
            task="transcribe", fp16=self.settings.whisper_device == "cuda",
            condition_on_previous_text=False, verbose=None)
        return str(result.get("text", "")).strip()

    async def transcribe(self, audio: Any) -> str:
        """Transcribe a bounded utterance; caller timeouts do not spawn new native jobs."""
        try:
            return await self.worker.run(self._transcribe, audio)
        except Exception as exc:
            raise ServiceUnavailable("Não foi possível transcrever o áudio.") from exc

    async def aclose(self) -> None:
        """Drain pending inference before releasing the process."""
        await self.worker.aclose()
