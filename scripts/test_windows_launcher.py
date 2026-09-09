"""Verify Windows socket reservation and non-destructive local token setup."""
import os
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api.launcher import prepare, reserve_port
from app.config import Settings

with socket.socket() as occupied:
    occupied.bind(('127.0.0.1', 0))
    occupied.listen()
    with reserve_port('127.0.0.1', occupied.getsockname()[1]) as reserved:
        assert occupied.getsockname()[1] != reserved.getsockname()[1]
print('PASS: occupied port preserved, alternative reserved')
previous = Path.cwd()
with tempfile.TemporaryDirectory() as temporary:
    try:
        os.chdir(temporary)
        Path('.env').write_text('LLM_PROVIDER=ollama\nCUSTOM_VALUE=preserved\n')
        settings = Settings(_env_file=None, api_token=None)
        prepare(settings)
        saved = Settings()
        assert len(saved.api_token.get_secret_value()) >= 32
        original = Path('.env').read_text()
        assert 'CUSTOM_VALUE=preserved' in original
        prepare(saved)
        assert Path('.env').read_text() == original
        print('PASS: local token creation preserves settings and existing token')
    finally:
        os.chdir(previous)
