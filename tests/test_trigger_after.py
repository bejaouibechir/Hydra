"""Déclencheurs after_project : fins de projet notées et suivies (0.19, lot 2.6)."""
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hydra_etl.triggers.core import FireResult, read_ends, record_end
from hydra_etl.triggers.engine import TriggerEngine

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def _project(base: Path, name: str, triggers: str = "", script: str = 'print("ok")') -> Path:
    root = base / name
    (root / ".hydra").mkdir(parents=True)
    (root / ".hydra" / "project.json").write_text(json.dumps({"id": name, "name": name}))
    (root / "workflows").mkdir()
    (root / "workflows" / "main.yaml").write_text(
        "workflow:\n  name: main\n  steps:\n    - name: s\n      type: action\n      action: python\n"
        f"      params:\n        script: '{script}'\n")
    (root / "workflows" / "thread.yaml").write_text(
        "thread:\n  - mode: sequential\n    workflows:\n      - name: main\n")
    if triggers:
        (root / "triggers.yaml").write_text(triggers)
    return root


def test_record_and_read_ends(tmp_path):
    root = _project(tmp_path, "a")
    t = time.time()
    record_end(root, True, ["main"], 1.2, "prod")
    record_end(root, False, ["main"], 0.5)
    ends = read_ends(root)
    assert [e["status"] for e in ends] == ["success", "failed"] and ends[0]["env"] == "prod"
    assert read_ends(root, ends[0]["ts"]) == ends[1:]
    assert (root / ".hydra" / "triggers" / ".gitignore").read_text().strip() == "*"
    assert read_ends(tmp_path / "none", t) == []


def test_project_runner_records_its_end(tmp_path):
    from hydra_etl.workflow.project import ProjectRunner, prepare_project
    ok = _project(tmp_path, "ok")
    ko = _project(tmp_path, "ko", script="raise SystemExit(2)")
    assert ProjectRunner(prepare_project(ok)).run().success
    assert not ProjectRunner(prepare_project(ko)).run().success
    assert read_ends(ok)[-1]["status"] == "success" and read_ends(ok)[-1]["workflows"] == ["main"]
    assert read_ends(ko)[-1]["status"] == "failed"


class FakeFire:
    def __init__(self):
        self.calls, self.gate = [], threading.Event()
        self.gate.set()

    def __call__(self, root, trig, **kw):
        self.calls.append((trig.name, kw.get("extra_params")))
        self.gate.wait(5)
        return FireResult(trig.name, "success", None, [], 0.1)


def _poll(eng, k):
    """Passe au-delà de l'intervalle de relecture (5 s) à chaque appel."""
    eng.tick(T0 + timedelta(seconds=6 * k))
    for th in list(eng._runs):
        th.join(5)


def test_after_project_filters_on_status(tmp_path):
    crm = _project(tmp_path, "crm")
    record_end(crm, True, ["main"], 1)                      # avant le démarrage : ignorée
    master = _project(tmp_path, "master", triggers=(
        "triggers:\n"
        "  - {name: ok, type: after_project, project: ../crm}\n"
        "  - {name: ko, type: after_project, project: ../crm, 'on': failure}\n"
        "  - {name: all, type: after_project, project: ../crm, 'on': any}\n"))
    fake = FakeFire()
    eng = TriggerEngine(fire_fn=fake, clock=lambda: T0)
    eng.add_project(master)
    _poll(eng, 1)
    assert fake.calls == []
    time.sleep(0.01)
    record_end(crm, True, ["main"], 1)
    _poll(eng, 2)
    assert sorted(n for n, _ in fake.calls) == ["all", "ok"]
    assert dict(fake.calls)["ok"] == {"trigger.project": "crm", "trigger.status": "success"}
    fake.calls.clear()
    time.sleep(0.01)
    record_end(crm, False, ["main"], 1)
    _poll(eng, 3)
    assert sorted(n for n, _ in fake.calls) == ["all", "ko"]


def test_ends_during_a_run_give_one_more_run(tmp_path):
    crm = _project(tmp_path, "crm")
    master = _project(tmp_path, "master", triggers="triggers:\n  - {name: a, type: after_project, project: ../crm, 'on': any}\n")
    fake = FakeFire()
    eng = TriggerEngine(fire_fn=fake, clock=lambda: T0)
    eng.add_project(master)
    time.sleep(0.01)
    record_end(crm, True, ["main"], 1)
    fake.gate.clear()
    eng.tick(T0 + timedelta(seconds=6))                     # run 1 (bloqué)
    for ok in (False, True):
        time.sleep(0.01)
        record_end(crm, ok, ["main"], 1)
    eng.tick(T0 + timedelta(seconds=12))                    # deux fins pendant le run
    assert len(fake.calls) == 1
    fake.gate.set()
    for th in list(eng._runs):
        th.join(5)
    _poll(eng, 3)
    assert len(fake.calls) == 2 and fake.calls[1][1]["trigger.status"] == "success"   # la plus récente
    _poll(eng, 4)
    assert len(fake.calls) == 2


def test_unknown_project_is_reported(tmp_path):
    master = _project(tmp_path, "master", triggers="triggers:\n  - {name: a, type: after_project, project: ../ghost}\n")
    eng = TriggerEngine(fire_fn=FakeFire(), clock=lambda: T0)
    eng.add_project(master)
    assert "ghost" in eng.status()[0]["note"]
