"""rollback: true (étape 5a du fallback) : un workflow qui échoue défait ses
steps déjà faits, du dernier au premier ; actions : `undo:`."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli
from hydra_etl.workflow.models import WorkflowDef
from hydra_etl.workflow.parser import load_workflow, validate_workflow
from hydra_etl.workflow.rollback import journal_path, rollback_problems
from hydra_etl.workflow.runner import WorkflowRunner


def job(root: Path, name: str, out: str, mode: str = "replace", src: str = "in.csv",
        dest_type: str = "csv", key: str = "") -> None:
    d = root / "jobs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "sources.yaml").write_text(textwrap.dedent(f"""\
        sources:
          src:
            type: csv
            extract:
              table: ../../data/{src}
        """), encoding="utf-8")
    (d / "destinations.yaml").write_text(textwrap.dedent(f"""\
        destinations:
          dst:
            type: {dest_type}
            load:
              table: ../../data/{out}
              mode: {mode}
        """) + (f"      key: [{key}]\n" if key else ""), encoding="utf-8")
    (d / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")


def workflow(root: Path, body: str, rollback: bool = True) -> Path:
    p = root / "workflows" / "wf.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("workflow:\n  name: wf\n" + (f"  rollback: true\n" if rollback else "")
                 + "  steps:\n" + textwrap.indent(textwrap.dedent(body), "    "), encoding="utf-8")
    return p


def py(code: str) -> str:
    return json.dumps(code)


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / "p"
    (root / ".hydra").mkdir(parents=True)
    data = root / "data"
    data.mkdir()
    (data / "in.csv").write_text("id,v\n1,a\n2,b\n", encoding="utf-8")
    (data / "out1.csv").write_text("id,v\nold,1\n", encoding="utf-8")
    (data / "out2.csv").write_text("id,v\nold,2\n", encoding="utf-8")
    job(root, "j1", "out1.csv", "replace")
    job(root, "j2", "out2.csv", "append")
    job(root, "broken", "out3.csv", "replace", src="missing.csv")
    return root


def steps(marker: Path, last: str = "broken") -> str:
    m = marker.as_posix()
    return f"""\
        - name: load1
          type: job
          job: ../jobs/j1
        - name: touch
          type: action
          action: python
          params:
            script: {py(f"open(r'{m}', 'w').write('x')")}
          undo:
            action: python
            params:
              script: {py(f"import os; os.remove(r'{m}')")}
          depends_on: [load1]
        - name: load2
          type: job
          job: ../jobs/j2
          depends_on: [touch]
        - name: last
          type: job
          job: ../jobs/{last}
          depends_on: [load2]
        """


def run(path: Path):
    wf = load_workflow(path)
    return WorkflowRunner(wf, base_dir=path.parent).run()


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_failure_undoes_every_step_last_first(proj):
    marker = proj / "data" / "marker.txt"
    r = run(workflow(proj, steps(marker)))
    assert not r.success and "changes undone" in r.error
    assert r.rollback["status"] == "done"
    assert [s["step"] for s in r.rollback["steps"]] == ["load2", "touch", "load1"]
    assert read(proj / "data" / "out1.csv") == "id,v\nold,1\n"
    assert read(proj / "data" / "out2.csv") == "id,v\nold,2\n"
    assert not marker.exists()
    assert not journal_path(proj, "wf").exists()
    assert not list((proj / "data").glob(".*hydra-*"))
    assert [s.undo_of for s in r.steps if s.undo_of] == ["load2", "touch", "load1"]


def test_success_keeps_the_data_and_drops_the_backups(proj):
    marker = proj / "data" / "marker.txt"
    r = run(workflow(proj, steps(marker, last="j1")))
    assert r.success and r.rollback is None
    assert read(proj / "data" / "out1.csv").splitlines() == ["id,v", "1,a", "2,b"]
    assert read(proj / "data" / "out2.csv").splitlines() == ["id,v", "old,2", "1,a", "2,b"]
    assert marker.exists()
    assert not list((proj / "data").glob(".*hydra-*"))
    assert not journal_path(proj, "wf").exists()


def test_without_rollback_nothing_is_undone(proj):
    r = run(workflow(proj, steps(proj / "data" / "m.txt"), rollback=False))
    assert not r.success and r.rollback is None
    assert read(proj / "data" / "out1.csv").splitlines()[1] == "1,a"


def test_changed_destination_is_not_undone_and_the_journal_stays(proj):
    m = (proj / "data" / "out1.csv").as_posix()
    append_line = py("open(r'" + m + "', 'a').write('9,z' + chr(10))")
    body = f"""\
        - name: load1
          type: job
          job: ../jobs/j1
        - name: someone_else
          type: action
          action: python
          params:
            script: {append_line}
          undo: none
          depends_on: [load1]
        - name: last
          type: job
          job: ../jobs/broken
          depends_on: [someone_else]
        """
    path = workflow(proj, body)
    r = run(path)
    assert r.rollback["status"] == "failed"
    assert "changed after this run wrote it" in r.rollback["steps"][-1]["message"]
    assert "hdrctl workflow undo wf" in r.error
    assert read(proj / "data" / "out1.csv").endswith("9,z\n")          # rien d'effacé
    assert journal_path(proj, "wf").exists()
    r2 = run(path)                                                      # refuse de relancer
    assert not r2.success and "stopped before undoing" in r2.error and not r2.steps


def test_cli_undo_finishes_a_stopped_rollback(proj, monkeypatch):
    flag = proj / "data" / "allow.txt"
    f = flag.as_posix()
    body = f"""\
        - name: act
          type: action
          action: python
          params:
            script: "print('done')"
          undo:
            action: python
            params:
              script: {py(f"import os, sys; sys.exit(0 if os.path.exists(r'{f}') else 3)")}
        - name: last
          type: job
          job: ../jobs/broken
          depends_on: [act]
        """
    path = workflow(proj, body)
    r = run(path)
    assert r.rollback["status"] == "failed" and journal_path(proj, "wf").exists()
    monkeypatch.chdir(proj)
    res = CliRunner().invoke(cli, ["workflow", "undo", "wf", "--lang", "en"])
    assert res.exit_code == 1 and "undo stopped at 'act'" in res.output
    flag.write_text("ok")
    res = CliRunner().invoke(cli, ["workflow", "undo", "wf", "--lang", "en"])
    assert res.exit_code == 0, res.output
    assert "1 step(s) undone" in res.output and not journal_path(proj, "wf").exists()
    res = CliRunner().invoke(cli, ["workflow", "undo", "wf", "--lang", "en"])
    assert "Nothing to undo" in res.output


def test_problems_are_reported_before_running(proj):
    job(proj, "jdb", "t", "append", dest_type="postgresql")
    job(proj, "jjson", "x.json", "replace", dest_type="json")
    body = """\
        - name: db
          type: job
          job: ../jobs/jdb
        - name: js
          type: job
          job: ../jobs/jjson
        - name: hook
          type: action
          action: webhook
          params:
            url: http://example.invalid
        - name: note
          type: action
          action: log
          params:
            message: hi
        """
    path = workflow(proj, body)
    probs = rollback_problems(load_workflow(path), path.parent)
    assert len(probs) == 3
    assert "needs load.key" in probs[0] and "json destination cannot be undone" in probs[1]
    assert "add undo:" in probs[2]
    ok, msg = validate_workflow(path)
    assert not ok and "cannot be undone" in msg
    r = run(path)
    assert not r.success and not r.steps and "cannot be undone" in r.error
    job(proj, "jdb", "t", "append", dest_type="postgresql", key="id")
    assert len(rollback_problems(load_workflow(path), path.parent)) == 2


def test_undo_is_only_for_actions_and_is_validated():
    with pytest.raises(ValueError, match="'undo' applies to type=action"):
        WorkflowDef(name="w", steps=[{"name": "j", "type": "job", "job": "x", "undo": "none"}])
    with pytest.raises(ValueError, match="unknown action"):
        WorkflowDef(name="w", steps=[{"name": "a", "type": "action", "action": "log",
                                      "undo": {"action": "nope"}}])
    w = WorkflowDef(name="w", rollback=True, steps=[
        {"name": "a", "type": "action", "action": "bash", "params": {"command": "x"},
         "undo": {"action": "bash", "params": {"command": "y"}}}])
    assert w.steps[0].undo.action == "bash"


# ── écriture préalable du journal : arrêt brutal pendant la publication ────────
class _Killed(BaseException):
    """Simule un arrêt brutal (SIGKILL) : rien ne s'exécute après, pas même les except Exception."""


def _kill_at_first_rename(monkeypatch, *, after_the_move: bool) -> None:
    import os as _os
    real = _os.replace
    calls = []

    def fake(src, dst, *a, **kw):
        if ".hydra-bak-" in str(dst) and not calls:   # le renommage de l'ancien fichier en .hydra-bak
            calls.append((src, dst))
            if after_the_move:
                real(src, dst, *a, **kw)
            raise _Killed()
        return real(src, dst, *a, **kw)               # y compris l'écriture du journal lui-même

    monkeypatch.setattr(_os, "replace", fake)


@pytest.mark.parametrize("after_the_move", [True, False])
def test_kill_during_publication_leaves_a_journal_that_undo_can_finish(proj, monkeypatch, after_the_move):
    """Avant : un arrêt entre le renommage de l'ancien fichier et l'écriture du journal ne
    laissait aucun journal (et un .hydra-bak orphelin). Maintenant le journal est écrit avant."""
    body = """\
        - name: load1
          type: job
          job: ../jobs/j1
        """
    path = workflow(proj, body)
    with monkeypatch.context() as m:
        _kill_at_first_rename(m, after_the_move=after_the_move)
        with pytest.raises(_Killed):
            run(path)
    jp = journal_path(proj, "wf")
    assert jp.exists(), "the journal must exist before the file is moved"
    entry = json.loads(jp.read_text(encoding="utf-8"))["entries"][0]
    assert entry["pending"] is True and entry["record"]["kind"] == "file"
    out1 = proj / "data" / "out1.csv"
    assert out1.exists() is (not after_the_move)          # déplacé, ou intact

    r = run(path)                                          # le run suivant refuse de repartir
    assert not r.success and "stopped before undoing" in r.error

    monkeypatch.chdir(proj)
    res = CliRunner().invoke(cli, ["workflow", "undo", "wf", "--lang", "en"])
    assert res.exit_code == 0, res.output
    assert read(out1) == "id,v\nold,1\n"                   # l'ancien fichier est revenu, ou n'a pas bougé
    assert not jp.exists()
    assert not list((proj / "data").glob(".*hydra-bak*"))


def test_successful_run_leaves_no_pending_entry(proj):
    r = run(workflow(proj, "        - name: load1\n          type: job\n          job: ../jobs/j1\n"))
    assert r.success and not journal_path(proj, "wf").exists()
    assert read(proj / "data" / "out1.csv").splitlines() == ["id,v", "1,a", "2,b"]
