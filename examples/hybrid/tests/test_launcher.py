"""Exercise the public entry point without desktop/LLM dependencies."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from app.hybrid_launcher import launch


def test_locked_isolated_process_and_exit_status():
    with patch("app.hybrid_launcher.shutil.which", return_value="/bin/uv"), \
         patch("app.hybrid_launcher.subprocess.run") as run:
        run.return_value.returncode = 7
        assert launch(host="127.0.0.1", port=9001) == 7
    command = run.call_args.args[0]
    assert command[:4] == ["/bin/uv", "run", "--locked", "--no-dev"]
    assert command[command.index("--port") + 1] == "9001"
    assert run.call_args.kwargs["cwd"] == ROOT / "examples" / "hybrid"
    assert "shell" not in run.call_args.kwargs


def test_invalid_port_and_missing_uv():
    with patch("app.hybrid_launcher.shutil.which", return_value=None):
        assert launch() == 2
        assert launch(port=65536) == 2


def test_entry_point_does_not_import_desktop_dependencies():
    # -S removes site-packages, so accidentally eager imports fail this test.
    script = '''
import sys
from unittest.mock import patch
sys.argv = ["jarvis", "--mode", "hybrid", "--hybrid-port", "9001"]
with patch("app.hybrid_launcher.launch", return_value=0) as launch:
    from app.main import main
    try:
        main()
    except SystemExit as exc:
        assert exc.code == 0
    launch.assert_called_once_with(host="127.0.0.1", port=9001)
assert "app.runtime" not in sys.modules
assert "app.config" not in sys.modules
'''
    subprocess.run([sys.executable, "-S", "-c", script], cwd=ROOT, check=True)
