"""Microphone capture with a bounded utterance and configurable energy endpointing."""

from collections import deque
from typing import Any

from app.config import Settings
from app.exceptions import ServiceUnavailable
from app.infrastructure.worker import BlockingWorker


class MicrophoneRecorder:
    """Desktop-only half-duplex recorder; energy detection is not a wake-word engine."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.worker = BlockingWorker("microphone")

    def _record(self) -> Any:
        import numpy as np
        import sounddevice as sd

        frame_seconds = 0.1
        frame_size = int(self.settings.audio_sample_rate * frame_seconds)
        pre_roll: deque[Any] = deque(maxlen=3)
        frames: list[Any] = []
        waiting = silence = recorded = 0.0
        speaking = False
        with sd.InputStream(samplerate=self.settings.audio_sample_rate, channels=1,
                            dtype="float32", device=self.settings.audio_device,
                            blocksize=frame_size) as stream:
            while True:
                block, overflowed = stream.read(frame_size)
                if overflowed:
                    raise ServiceUnavailable("Microfone perdeu amostras. Verifique o dispositivo e a carga da máquina.")
                block = block[:, 0].copy()
                energy = float(np.sqrt(np.mean(block * block)))
                if not speaking:
                    pre_roll.append(block)
                    waiting += frame_seconds
                    if energy >= self.settings.speech_threshold:
                        speaking = True
                        frames.extend(pre_roll)
                        recorded = len(frames) * frame_seconds
                    elif waiting >= self.settings.listen_timeout:
                        return None
                else:
                    frames.append(block)
                    recorded += frame_seconds
                    silence = silence + frame_seconds if energy < self.settings.speech_threshold else 0.0
                    if silence >= self.settings.silence_seconds or recorded >= self.settings.max_record_seconds:
                        return np.concatenate(frames).astype(np.float32, copy=False)

    async def record(self) -> Any:
        """Return an utterance, or None when no speech starts before the deadline."""
        try:
            return await self.worker.run(self._record)
        except ServiceUnavailable:
            raise
        except Exception as exc:
            raise ServiceUnavailable("Microfone indisponível. Confira permissões, PortAudio e AUDIO_DEVICE.") from exc

    async def aclose(self) -> None:
        """Wait for the bounded capture operation to finish."""
        await self.worker.aclose()
