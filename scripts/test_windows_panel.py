"""Execute the actual batch parser on Windows, including checkout paths with spaces."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    if os.name != "nt":
        raise SystemExit("This test requires Windows cmd.exe.")
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="jarvis panel ") as temporary:
        checkout = Path(temporary) / "Jarvis & Home (local)"
        checkout.mkdir()
        shutil.copyfile(root / "JARVIS.bat", checkout / "JARVIS.bat")
        (checkout / "app").mkdir()
        (checkout / "app" / "main.py").touch()
        for argument, expected, marker in (
            ("--help", 0, "Uso:"),
            ("--check", 0, "diagnostico concluido"),
            ("--invalid", 2, "Argumento invalido"),
        ):
            result = subprocess.run(
                [os.environ["COMSPEC"], "/d", "/c", "JARVIS.bat", argument],
                cwd=checkout, capture_output=True, text=True, timeout=60,
            )
            assert result.returncode == expected, (argument, result.stdout, result.stderr)
            assert marker in result.stdout, result.stdout
            assert "unexpected" not in result.stderr.lower(), result.stderr
            print(f"PASS: {argument} in path with spaces and metacharacters")
        (checkout / "app" / "main.py").unlink()
        result = subprocess.run(
            [os.environ["COMSPEC"], "/d", "/c", "JARVIS.bat", "--check"],
            cwd=checkout, capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 2
        assert "checkout completo" in result.stdout
        print("PASS: missing checkout fails clearly")


if __name__ == "__main__":
    main()
