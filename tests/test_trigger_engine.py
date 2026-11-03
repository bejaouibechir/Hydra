"""Moteur des déclencheurs et cron (0.19, lot 2.2) — horloge et lancement simulés."""
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hydra_etl.triggers.core import FireResult, read_history
from hydra_etl.triggers.cron import next_run, parse_cron
from hydra_etl.triggers.engine import TriggerEngine

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


# ── cron ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("expr, after, expected", [
    ("0 2 * * *", datetime(2026, 11, 2, 18, 0), datetime(2026, 11, 3, 2, 0)),
    ("*/15 * * * *", datetime(2026, 11, 2, 18, 7), datetime(2026, 11, 2, 18, 15)),
    ("30 8 * * mon-fri", datetime(2026, 11, 6, 9, 0), datetime(2026, 11, 9, 8, 30)),   # vendredi → lundi
    ("0 9 1 * mon", datetime(2026, 11, 2, 10, 0), datetime(2026, 11, 9, 9, 0)),        # jour OU semaine
    ("0 0 * * 7", datetime(2026, 11, 2, 0, 0), datetime(2026, 11, 8, 0, 0)),           # 7 = dimanche
    ("0 0 29 feb *", datetime(2026, 3, 1, 0, 0), datetime(2028, 2, 29, 0, 0)),
    ("0 12 * jan,jul *", datetime(2026, 11, 2, 0, 0), datetime(2027, 1, 1, 12, 0)),
])
def test_cron_next(expr, after, expected):
    assert parse_cron(expr).next_after(after) == expected


@pytest.mark.parametrize("expr, msg", [
    ("61 * * * *", "out of range"), ("* * *", "5 fields"), ("0 0 30 2 *", "never matches"),
    ("a * * * *", "not a number"), ("5-1 * * * *", "backwards"), ("*/0 * * * *", "invalid step"),
])
def test_cron_invalid(expr, msg):
    with pytest.raises(ValueError, match=msg):
        parse_cron(expr)


def test_cron_timezone():
    nxt = next_run("0 2 * * *", datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc), "Europe/Paris")
    assert nxt.astimezone(timezone.utc) == datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="unknown timezone"):
        next_run("0 2 * * *", T0, "Mars/Olympus")


# ── moteur ────────────────────────────────────────────────────────────────

def _project(base: Path, triggers: str) -> Path:
    root = base / "p"
    (root / ".hydra").mkdir(parents=True)
    (root / ".hydra" / "project.json").write_text(json.dumps({"id": "p", "name": "p"}))
    (root / "workflows").mkdir()
    (root / "workflows" / "main.yaml").write_text(
        "workflow:\n  name: main\n  steps:\n    - {name: s, type: action, action: log, params: {message: hi}}\n")
    (root / "workflows" / "thread.yaml").write_text(
        "thread:\n  - mode: sequential\n    workflows:\n      - name: main\n")
    (root / "triggers.yaml").write_text(triggers)
    return root


class FakeFire:
    """Remplace core.fire : note les lancements ; `gate` retient le run."""

    def __init__(self, status="success"):
        self.calls, self.status, self.gate = [], status, threading.Event()
        self.gate.set()

    def __call__(self, root, trig, **kw):
        self.calls.append((trig.name, kw.get("origin"), kw.get("env")))
        self.gate.wait(5)
        return FireResult(trig.name, self.status, None, [], 0.1)


def _engine(root, fake, events=None, env=None):
    eng = TriggerEngine(env=env, fire_fn=fake, clock=lambda: T0,
                        on_event=(events.append if events is not None else None))
    eng.add_project(root)
    return eng


def _wait(eng):
    for th in list(eng._runs):
        th.join(5)


def test_interval_runs_when_due(tmp_path):
    root = _project(tmp_path, "triggers:\n  - {name: q, type: interval, every: 10m}\n")
    fake = FakeFire()
    eng = _engine(root, fake, env="prod")
    assert eng.tick(T0 + timedelta(minutes=9)) == []
    assert eng.tick(T0 + timedelta(minutes=10)) == ["q"]
    _wait(eng)
    assert fake.calls == [("q", "watch", "prod")]
    nxt = eng.status()[0]["next"]
    assert nxt == T0 + timedelta(minutes=20)


def test_cron_runs_at_its_minute(tmp_path):
    root = _project(tmp_path, "triggers:\n  - {name: c, type: cron, cron: '30 12 * * *', timezone: UTC}\n")
    fake = FakeFire()
    eng = _engine(root, fake)
    assert eng.status()[0]["next"] == datetime(2026, 11, 2, 12, 30, tzinfo=timezone.utc)
    assert eng.tick(T0 + timedelta(minutes=29)) == []
    assert eng.tick(T0 + timedelta(minutes=30, seconds=1)) == ["c"]
    _wait(eng)
    assert eng.status()[0]["next"] == datetime(2026, 11, 3, 12, 30, tzinfo=timezone.utc)


def test_running_trigger_is_not_started_twice(tmp_path):
    root = _project(tmp_path, "triggers:\n  - {name: q, type: interval, every: 1m}\n")
    fake = FakeFire()
    fake.gate.clear()
    eng = _engine(root, fake)
    assert eng.tick(T0 + timedelta(minutes=1)) == ["q"]
    assert eng.tick(T0 + timedelta(minutes=2)) == []          # encore en cours
    fake.gate.set()
    _wait(eng)
    h = read_history(root)
    assert h[-1]["status"] == "skipped" and "still running" in h[-1]["error"]
    assert eng.tick(T0 + timedelta(minutes=3)) == ["q"]
    _wait(eng)


def test_other_types_and_disabled_are_reported(tmp_path):
    root = _project(tmp_path, "triggers:\n"
                              "  - {name: f, type: webhook, token: '${SECRET:trigger.f.token}'}\n"
                              "  - {name: d, type: interval, every: 1m, enabled: false}\n"
                              "  - {name: w, type: interval, every: 1m, workflows: [nope]}\n")
    eng = _engine(root, FakeFire())
    notes = {s["trigger"]: s["note"] for s in eng.status()}
    assert "called through hdrctl serve" in notes["f"]
    assert "disabled" in notes["d"]
    assert "not found" in notes["w"]
    assert eng.tick(T0 + timedelta(hours=1)) == []


def test_reload_keeps_or_recomputes_the_next_run(tmp_path):
    root = _project(tmp_path, "triggers:\n  - {name: q, type: interval, every: 10m}\n"
                              "  - {name: r, type: interval, every: 10m}\n")
    events = []
    eng = _engine(root, FakeFire(), events)
    later = T0 + timedelta(minutes=5)
    (root / "triggers.yaml").write_text("triggers:\n  - {name: q, type: interval, every: 10m}\n"
                                        "  - {name: r, type: interval, every: 30m}\n")
    os.utime(root / "triggers.yaml", (time.time() + 5, time.time() + 5))
    eng.tick(later)
    nxt = {s["trigger"]: s["next"] for s in eng.status()}
    assert nxt["q"] == T0 + timedelta(minutes=10)               # inchangé : même échéance
    assert nxt["r"] == later + timedelta(minutes=30)            # modifié : recalculé
    assert sum(1 for e in events if e["kind"] == "loaded") == 2


def test_invalid_file_keeps_previous_triggers(tmp_path):
    root = _project(tmp_path, "triggers:\n  - {name: q, type: interval, every: 10m}\n")
    events = []
    eng = _engine(root, FakeFire(), events)
    (root / "triggers.yaml").write_text("triggers:\n  - {name: q, type: cron}\n")
    os.utime(root / "triggers.yaml", (time.time() + 5, time.time() + 5))
    eng.tick(T0 + timedelta(minutes=1))
    assert any(e["kind"] == "error" and "requires 'cron'" in e["error"] for e in events)
    assert eng.tick(T0 + timedelta(minutes=10)) == ["q"]
    _wait(eng)


def test_stop_waits_for_running_runs(tmp_path):
    root = _project(tmp_path, "triggers:\n  - {name: q, type: interval, every: 1m}\n")
    fake = FakeFire()
    fake.gate.clear()
    events = []
    eng = _engine(root, fake, events)
    eng.tick(T0 + timedelta(minutes=1))
    threading.Timer(0.3, fake.gate.set).start()
    assert eng.stop(wait=5) is True
    assert any(e["kind"] == "stopping" for e in events)
    assert any(e["kind"] == "finished" for e in events)
    assert eng.tick(T0 + timedelta(minutes=5)) == []           # arrêté : plus de lancement


def test_engine_thread_runs_a_real_project(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("PYTHONPATH", str(repo) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    root = _project(tmp_path, "triggers:\n  - {name: q, type: interval, every: 1s}\n")
    events = []
    eng = TriggerEngine(on_event=events.append, tick=0.2)
    eng.add_project(root)
    eng.start()
    deadline = time.time() + 60
    while time.time() < deadline and not any(e["kind"] == "finished" for e in events):
        time.sleep(0.2)
    eng.stop(wait=60)
    done = [e for e in events if e["kind"] == "finished"]
    assert done and done[0]["status"] == "success", done
    assert read_history(root)[0]["origin"] == "watch"
