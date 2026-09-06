"""Launch the hybrid service in its locked environment from a source checkout."""

import shutil
import subprocess
import sys
from pathlib import Path


def launch(*, host: str = "127.0.0.1", port: int = 8000) -> int:
    """Preserve service exit status without importing desktop or model dependencies."""
    if not 1 <= port <= 65535 or not host.strip() or host.startswith("-"):
        print("Host ou porta inválidos.", file=sys.stderr)
        return 2
    project = Path(__file__).resolve().parents[1] / "examples" / "hybrid"
    if not all((project / name).is_file() for name in ("pyproject.toml", "uv.lock")):
        print("Modo hybrid requer o checkout completo do repositório.", file=sys.stderr)
        return 2
    uv = shutil.which("uv")
    if uv is None:
        print("Instale uv==0.10.0 para executar o modo hybrid.", file=sys.stderr)
        return 2
    command = [uv, "run", "--locked", "--no-dev", "uvicorn", "hybrid.server:create_app",
               "--factory", "--host", host, "--port", str(port), "--workers", "1",
               "--ws-max-size", "8192", "--ws-max-queue", "16",
               "--limit-concurrency", "32", "--no-access-log"]
    try:
        # cwd selects the isolated project and its .env; no shell interpolation.
        return subprocess.run(command, cwd=project, check=False).returncode
    except KeyboardInterrupt:
        # Child shares the terminal process group and receives the same interrupt.
        return 130
    except OSError:
        print("Não foi possível iniciar uv. Verifique a instalação.", file=sys.stderr)
        return 1
