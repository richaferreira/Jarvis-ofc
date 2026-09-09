"""Reserve a free local port before expensive startup and open only a ready server."""
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import webbrowser
from urllib.parse import urlsplit

from dotenv import set_key
from pydantic import SecretStr

from app.config import Settings
from app.exceptions import JarvisError


def reserve_port(host: str, port: int) -> socket.socket:
    """Keep the socket open to prevent a check-then-bind race."""
    for candidate in range(port, min(port + 10, 65536)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, candidate))
            sock.listen(128)
            sock.setblocking(False)
            return sock
        except OSError:
            sock.close()
    raise JarvisError("Não há porta livre no intervalo configurado. Confira API_HOST e API_PORT.")


def prepare(settings: Settings) -> None:
    """Generate the local UI token only when missing; preserve existing valid tokens."""
    if not settings.api_token or len(settings.api_token.get_secret_value()) < 32:
        token = secrets.token_urlsafe(32)
        set_key('.env', 'API_TOKEN', token)
        settings.api_token = SecretStr(token)
        print('API_TOKEN gerado e salvo no .env. Use-o para conectar ao painel.')
    if settings.llm_provider != 'omniroute':
        return
    url = urlsplit(settings.omniroute_base_url)
    if url.hostname not in ('127.0.0.1', 'localhost'):
        return
    try:
        with socket.create_connection((url.hostname, url.port or 80), timeout=1):
            return
    except OSError:
        pass
    if shutil.which('omniroute'):
        if os.name == 'nt':
            # Fixed command only: never interpolate model names, URLs or secrets into cmd.
            subprocess.Popen('omniroute serve --no-open', shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen([shutil.which('omniroute') or 'omniroute', 'serve', '--no-open'], start_new_session=True)
        print('Inicialização do OmniRoute solicitada. Confira a janela do gateway.')
    else:
        print('OmniRoute não encontrado no PATH. Inicie o gateway antes de conversar.')


def run(settings: Settings) -> None:
    import uvicorn
    from app.api.server import create_app

    prepare(settings)
    with reserve_port(settings.api_host, settings.api_port) as sock:
        port = sock.getsockname()[1]
        host = '127.0.0.1' if settings.api_host == '0.0.0.0' else settings.api_host
        url = f'http://{host}:{port}'
        print(f'Endereço reservado para o painel: {url}')
        server = uvicorn.Server(uvicorn.Config(create_app(settings), host=settings.api_host,
                                               port=port, access_log=False, limit_concurrency=16))
        stopped = threading.Event()

        def open_when_ready() -> None:
            deadline = time.monotonic() + 240
            while not stopped.wait(1) and time.monotonic() < deadline:
                if not server.started:
                    continue
                try:
                    with urllib.request.urlopen(url + '/health', timeout=2) as response:
                        if response.status == 200:
                            webbrowser.open(url)
                            return
                except OSError:
                    continue

        threading.Thread(target=open_when_ready, daemon=True).start()
        try:
            server.run(sockets=[sock])
        finally:
            stopped.set()
