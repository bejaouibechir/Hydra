"""`hdrctl mcp setup`: Claude Code configuration of a project (.mcp.json)."""
from __future__ import annotations

import json
import sys

import pytest
from click.testing import CliRunner

from hydra_etl.mcp import setup as S


def test_creates_mcp_json_with_the_running_python(tmp_path):
    f, state = S.write_claude_code(tmp_path)
    assert state == "created" and f == tmp_path / ".mcp.json"
    entry = json.loads(f.read_text(encoding="utf-8"))["mcpServers"]["hydra-etl"]
    assert entry == {"type": "stdio", "command": sys.executable,
                     "args": ["-m", "hydra_etl.mcp", "--workspace", str(tmp_path)]}
    assert S.write_claude_code(tmp_path)[1] == "unchanged"


def test_keeps_the_other_servers(tmp_path):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"github": {"command": "gh-mcp"}}}),
                                        encoding="utf-8")
    assert S.write_claude_code(tmp_path)[1] == "updated"
    servers = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert set(servers) == {"github", "hydra-etl"}


def test_never_overwrites_an_invalid_file(tmp_path):
    (tmp_path / ".mcp.json").write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError):
        S.write_claude_code(tmp_path)
    assert (tmp_path / ".mcp.json").read_text(encoding="utf-8") == "{ not json"


def test_project_root_is_found_from_a_subfolder(tmp_path):
    (tmp_path / ".hydra").mkdir()
    (tmp_path / "jobs" / "a").mkdir(parents=True)
    assert S.project_root(tmp_path / "jobs" / "a") == tmp_path.resolve()


def test_cli(tmp_path):
    from hydra_etl.cli.hdrctl import cli

    (tmp_path / ".hydra").mkdir()
    r = CliRunner().invoke(cli, ["mcp", "setup", "--path", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert "created" in r.output and (tmp_path / ".mcp.json").exists()
    assert "not a Hydra ETL project" not in r.output
