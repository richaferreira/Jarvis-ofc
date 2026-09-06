import asyncio
import threading
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from pydantic import SecretStr

from app.audio.recorder import MicrophoneRecorder
from app.audio.stt import WhisperSTT
from app.audio.tts import ElevenLabsProvider
from app.exceptions import ServiceUnavailable
from app.infrastructure.http_client import HttpClient
from app.main import console_input


async def test_stt_passes_local_language_and_rejects_invalid_audio(settings):
    calls = []

    def transcribe(audio, **kwargs):
        calls.append(kwargs)
        return {"text": " Olá mundo "}

    stt = WhisperSTT(settings)
    stt.model = SimpleNamespace(transcribe=transcribe)
    try:
        assert await stt.transcribe(np.ones(1600, dtype=np.float32)) == "Olá mundo"
        assert calls[0]["language"] == "pt"
        assert calls[0]["fp16"] is False
        with pytest.raises(ServiceUnavailable):
            await stt.transcribe(np.array([np.nan], dtype=np.float32))
    finally:
        await stt.aclose()


async def test_recorder_stops_at_silence_and_returns_none_without_speech(settings, monkeypatch):
    import sys

    blocks = []

    class Stream:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            amplitude = blocks.pop(0) if blocks else 0.0
            return np.full((size, 1), amplitude, dtype=np.float32), False

    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(InputStream=Stream))
    settings.listen_timeout = 1
    settings.silence_seconds = 0.3
    recorder = MicrophoneRecorder(settings)
    try:
        assert await recorder.record() is None
        blocks.extend([0, 0.1, 0.1, 0, 0, 0, 0])
        waveform = await recorder.record()
        assert waveform.ndim == 1
        assert 1600 <= waveform.size < 16000
    finally:
        await recorder.aclose()


async def test_elevenlabs_sends_fixed_voice_and_reads_audio(settings):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, content=b"fake-mp3", headers={"content-type": "audio/mpeg"})

    settings.elevenlabs_api_key = SecretStr("fake-secret")
    settings.elevenlabs_voice_id = "testvoice"
    http = HttpClient(2, httpx.MockTransport(handle))
    try:
        assert await ElevenLabsProvider(settings, http).synthesize("Olá") == b"fake-mp3"
        assert len(calls) == 1
        assert calls[0].url.path == "/v1/text-to-speech/testvoice"
        assert calls[0].headers["xi-api-key"] == "fake-secret"
    finally:
        await http.aclose()


async def test_console_cancel_does_not_wait_for_enter(monkeypatch):
    started, finish = threading.Event(), threading.Event()

    def fake_input(prompt):
        started.set()
        finish.wait(2)
        return "ignored"

    monkeypatch.setattr("builtins.input", fake_input)
    task = asyncio.create_task(console_input("test"))
    await asyncio.to_thread(started.wait, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    finish.set()
    await asyncio.sleep(0.01)
