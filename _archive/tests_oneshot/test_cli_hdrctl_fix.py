"""Script temporaire pour compléter test_cli_hdrctl.py tronqué."""
from pathlib import Path

TARGET = Path(__file__).parent / "test_cli_hdrctl.py"
content = TARGET.read_bytes()

suffix = (
    b'= runner.invoke(cli, ["run", str(job), "-v"])\r\n'
    b'        assert result.exit_code == 0\r\n'
    b'\r\n'
    b'\r\n'
    b'class TestErrors:\r\n'
    b'\r\n'
    b'    def test_run_missing_dir(self, runner):\r\n'
    b'        result = runner.invoke(cli, ["run", "/nonexistent/path"])\r\n'
    b'        assert result.exit_code != 0\r\n'
    b'\r\n'
    b'    def test_validate_missing_dir(self, runner):\r\n'
    b'        result = runner.invoke(cli, ["validate", "/nonexistent/path"])\r\n'
    b'        assert result.exit_code != 0\r\n'
    b'\r\n'
    b'    def test_list_missing_dir(self, runner):\r\n'
    b'        result = runner.invoke(cli, ["list", "/nonexistent/path"])\r\n'
    b'        assert result.exit_code != 0\r\n'
)

fixed = content + suffix
TARGET.write_bytes(fixed)
print("Done, size:", len(fixed))
