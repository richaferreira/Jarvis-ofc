from app.audio.tts import SpeechSynthesizer
from app.infrastructure.audio_cache import AudioCache
from app.memory.conversation import ConversationBuffer
from app.memory.memory import MemoryService


def test_history_evicts_whole_turns_and_expires(monkeypatch):
    buffer = ConversationBuffer(2, 2, 20, 60)
    buffer.append("a", "s", "hello", "world")
    buffer.append("a", "s", "hello2", "world2")
    assert len(buffer.messages("a", "s")) == 2
    assert not buffer.messages("b", "s")
    from app.memory import conversation

    now = conversation.time.monotonic()
    monkeypatch.setattr(conversation.time, "monotonic", lambda: now + 100)
    assert buffer.messages("a", "s") == []


async def test_tts_cache_includes_voice_and_provider(settings, tmp_path):
    class Provider:
        calls = 0

        async def synthesize(self, text):
            self.calls += 1
            return b"test-audio"

    provider = Provider()
    cache = AudioCache(tmp_path / "cache", 8, 60)
    try:
        speech = SpeechSynthesizer(settings, cache, provider)
        assert await speech.synthesize("Olá") == b"test-audio"
        await speech.synthesize("Olá")
        assert provider.calls == 1
        settings.edge_voice = "pt-BR-FranciscaNeural"
        await speech.synthesize("Olá")
        assert provider.calls == 2
    finally:
        await cache.aclose()


async def test_memory_supplies_explicit_owner_filter(settings):
    calls = []

    class Embeddings:
        def encode(self, text):
            return [1.0, 0.0]

    class Collection:
        def query(self, **kwargs):
            calls.append(kwargs)
            return {"documents": [["Prefiro português"]]}

    memory = MemoryService(settings)
    memory._ready = True
    memory.embeddings = Embeddings()
    memory.collection = Collection()
    try:
        assert await memory.recall("owner-1", "idioma") == ["Prefiro português"]
        assert calls[0]["where"] == {"owner": "owner-1"}
    finally:
        await memory.aclose()
