"""
`hdrctl mcp setup` — connects an AI assistant to the Hydra ETL MCP server of a project.

For Claude Code, it writes `.mcp.json` at the root of the project (the project scope
of Claude Code): the command is the Python that runs `hdrctl`, so the server starts
with the Hydra ETL that is installed, whatever is on the PATH. The other servers of
an existing `.mcp.json` are kept.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SERVER_NAME = "hydra-etl"


def project_root(start: Path) -> Path:
    """The Hydra ETL project that holds `start` (the folder with .hydra/), or `start` itself."""
    from hydra_etl.workflow.project import find_project_root

    start = Path(start).resolve()
    return find_project_root(start) or start


def server_entry(project: Path, python: str) -> Dict:
    return {
        "type": "stdio",
        "command": python,
        "args": ["-m", "hydra_etl.mcp", "--workspace", str(project)],
    }


def mcp_sdk_installed() -> bool:
    return importlib.util.find_spec("mcp") is not None


def write_claude_code(project: Path, python: Optional[str] = None) -> Tuple[Path, str]:
    """Writes or updates <project>/.mcp.json. Returns (file, "created" | "updated" | "unchanged").

    Raises ValueError when an existing .mcp.json is not valid JSON: it is never overwritten.
    """
    python = python or sys.executable
    f = Path(project) / ".mcp.json"
    doc: Dict = {}
    if f.exists():
        try:
            doc = json.loads(f.read_text(encoding="utf-8-sig") or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError(f"{f} is not valid JSON ({exc}); fix it or remove it, nothing was changed") from exc
        if not isinstance(doc, dict) or not isinstance(doc.get("mcpServers", {}), dict):
            raise ValueError(f"{f} has no mcpServers object; nothing was changed")
    servers = doc.setdefault("mcpServers", {})
    entry = server_entry(Path(project), python)
    if servers.get(SERVER_NAME) == entry:
        return f, "unchanged"
    state = "updated" if f.exists() else "created"
    servers[SERVER_NAME] = entry
    f.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f, state


def notes(project: Path) -> List[str]:
    """What the user should know after the setup."""
    out = []
    if not any((project / d).is_dir() for d in (".hydra", "jobs", "workflows")):
        out.append(f"{project} is not a Hydra ETL project yet (no .hydra/, jobs/ or workflows/): "
                   f"`hdrctl init` makes it one. The server works anyway, inside this folder.")
    gi = project / ".gitignore"
    if gi.exists() and ".mcp.json" not in gi.read_text(encoding="utf-8", errors="replace"):
        out.append(".mcp.json holds paths of this computer: add it to .gitignore if the project is shared; "
                   "each person runs `hdrctl mcp setup` once.")
    return out
