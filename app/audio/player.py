"""Asynchronous MP3 playback without shell interpolation or retained temporary files."""

import asyncio
import shutil

from app.exceptions import ServiceUnavailable


class AudioPlayer:
    """Use ffplay from FFmpeg and always reap the child process on cancellation."""

    def __init__(self) -> None:
        self.executable = shutil.which("ffplay")
        if self.executable is None:
            raise ServiceUnavailable("Instale FFmpeg com ffplay e adicione-o ao PATH.")

    async def play(self, audio: bytes) -> None:
        """Play one bounded MP3 buffer with a maximum playback duration."""
        process = await asyncio.create_subprocess_exec(
            self.executable, "-nodisp", "-autoexit", "-loglevel", "error", "-i", "pipe:0",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL)
        try:
            async with asyncio.timeout(300):
                await process.communicate(audio)
            if process.returncode != 0:
                raise ServiceUnavailable("Falha na reprodução. Verifique a saída de áudio.")
        finally:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
