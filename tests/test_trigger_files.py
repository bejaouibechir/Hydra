"""Déclencheurs de fichiers : socle FileEventSource, file, marker (0.19, lot 2.3)."""
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hydra_etl.triggers.core import FireResult, read_history
from hydra_etl.triggers.engine import TriggerEngine
from hydra_etl.triggers.files import FileWatcher, LocalSource, S3Source, SftpSource, source_for

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


# ── Socle ─────────────────────────────────────────────────────────────────

def test_local_source_lists_and_deletes(tmp_path):
    (tmp_path / "in" / "sub").mkdir(parents=True)
    (tmp_path / "in" / "a.csv").write_text("1")
    (tmp_path / "in" / "sub" / "b.csv").write_text("22")
    (tmp_path / "in" / "c.txt").write_text("x")
    src = LocalSource(tmp_path)
    assert set(src.list("in/*.csv")) == {"in/a.csv"}
    assert set(src.list("in/**/*.csv")) == {"in/a.csv", "in/sub/b.csv"}
    assert src.list("in/sub/b.csv")["in/sub/b.csv"][1] == 2
    src.delete("in/a.csv")
    assert not (tmp_path / "in" / "a.csv").exists()
    with pytest.raises(ValueError, match="outside"):
        src.delete("../x")


def test_remote_sources_are_reserved(tmp_path):
    assert isinstance(source_for(tmp_path), LocalSource)
    for url, cls in (("sftp://host/in", SftpSource), ("s3://bucket/in", S3Source)):
        src = source_for(tmp_path, url)
        assert isinstance(src, cls)
        with pytest.raises(NotImplementedError, match="not available yet"):
            src.list("*.csv")
    with pytest.raises(ValueError, match="unsupported"):
        source_for(tmp_path, "ftp://x")


def test_watcher_added_modified_debounce(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "old.csv").write_text("x")
    w = FileWatcher(LocalSource(tmp_path), "in/*.csv", ["added", "modified"], debounce=2)
    assert w.poll(0) == []                                  # état de départ : old.csv ignoré
    (tmp_path / "in" / "a.csv").write_text("1")
    assert w.poll(1) == [] and w.poll(2) == []              # pas encore stable 2 s
    assert [(e.path, e.kind) for e in w.poll(3.5)] == [("in/a.csv", "added")]
    (tmp_path / "in" / "old.csv").write_text("changed")
    w.poll(4)
    assert [(e.path, e.kind) for e in w.poll(6.5)] == [("in/old.csv", "modified")]
    os.remove(tmp_path / "in" / "a.csv")
    w.poll(7)
    (tmp_path / "in" / "a.csv").write_text("again")
    w.poll(8)
    assert [(e.path, e.kind) for e in w.poll(10.5)] == [("in/a.csv", "added")]


def test_watcher_filters_events(tmp_path):
    (tmp_path / "x.csv").write_text("1")
    w = FileWatcher(LocalSource(tmp_path), "*.csv", ["added"], debounce=0)
    w.poll(0)
    (tmp_path / "x.csv").write_text("12345")
    assert w.poll(1) == []                                  # modified non demandé


def test_growing_file_waits_until_stable(tmp_path):
    w = FileWatcher(LocalSource(tmp_path), "*.csv", ["added"], debounce=2)
    w.poll(0)
    f = tmp_path / "big.csv"
    f.write_text("a")
    w.poll(1)
    f.write_text("a" * 50)                                  # encore en cours de copie
    assert w.poll(3) == []
    assert [e.path for e in w.poll(5.5)] == ["big.csv"]


# ── Moteur ────────────────────────────────────────────────────────────────

def _project(base: Path, triggers: str) -> Path:
    root = base / "p"
    (root / ".hydra").mkdir(parents=True)
    (root / ".hydra" / "project.json").write_text(json.dumps({"id": "p", "name": "p"}))
    (root / "workflows").mkdir()
    (root / "workflows" / "main.yaml").write_text(
        "workflow:\n  name: main\n  steps:\n    - name: s\n      type: action\n      action: python\n"
        "      params:\n        script: 'print(\"got {{ param:trigger.files }}\")'\n")
    (root / "workflows" / "thread.yaml").write_text(
        "thread:\n  - mode: sequential\n    workflows:\n      - name: main\n")
    (root / "inbox").mkdir()
    (root / "triggers.yaml").write_text(triggers)
    return root


class FakeFire:
    def __init__(self):
        self.calls = []

    def __call__(self, root, trig, **kw):
        self.calls.append((trig.name, kw.get("extra_params"), kw.get("detail")))
        return FireResult(trig.name, "success", None, [], 0.1)


def _wait(eng):
    for th in list(eng._runs):
        th.join(5)


def test_file_trigger_batches_files_and_passes_them(tmp_path):
    root = _project(tmp_path, "triggers:\n  - {name: f, type: file, path: 'inbox/*.csv', every: 1s, debounce: 0s}\n")
    fake = FakeFire()
    eng = TriggerEngine(fire_fn=fake, clock=lambda: T0)
    eng.add_project(root)
    st = eng.status()[0]
    assert st["poll"] == 1.0 and st["next"] is None
    (root / "inbox" / "b.csv").write_text("1")
    (root / "inbox" / "a.csv").write_text("1")
    assert eng.tick(T0 + timedelta(seconds=1)) == ["f"]
    _wait(eng)
    name, extra, detail = fake.calls[0]
    assert extra == {"trigger.file": "inbox/a.csv", "trigger.files": "inbox/a.csv,inbox/b.csv"}
    assert "inbox/a.csv" in detail
    assert eng.tick(T0 + timedelta(seconds=2)) == []         # rien de nouveau


def test_file_event_waits_for_running_run(tmp_path):
    import threading
    root = _project(tmp_path, "triggers:\n  - {name: f, type: file, path: 'inbox/*.csv', every: 1s, debounce: 0s}\n")
    gate = threading.Event()
    calls = []

    def slow(root_, trig, **kw):
        calls.append(kw.get("extra_params")["trigger.files"])
        gate.wait(5)
        return FireResult(trig.name, "success", None, [], 0.1)

    eng = TriggerEngine(fire_fn=slow, clock=lambda: T0)
    eng.add_project(root)
    (root / "inbox" / "a.csv").write_text("1")
    assert eng.tick(T0 + timedelta(seconds=1)) == ["f"]
    (root / "inbox" / "b.csv").write_text("1")
    assert eng.tick(T0 + timedelta(seconds=2)) == []         # run en cours : b.csv attend
    assert eng.status()[0]["pending"] == ["inbox/b.csv"]
    gate.set()
    _wait(eng)
    assert eng.tick(T0 + timedelta(seconds=3)) == ["f"]      # pas perdu
    _wait(eng)
    assert calls == ["inbox/a.csv", "inbox/b.csv"]
    assert not any(e["status"] == "skipped" for e in read_history(root))


def test_marker_is_consumed_or_kept(tmp_path):
    root = _project(tmp_path, "triggers:\n  - {name: m, type: marker, path: inbox/READY, every: 1s}\n"
                              "  - {name: k, type: marker, path: inbox/KEEP, every: 1s, consume: false}\n")
    fake = FakeFire()
    eng = TriggerEngine(fire_fn=fake, clock=lambda: T0)
    eng.add_project(root)
    (root / "inbox" / "READY").write_text("")
    (root / "inbox" / "KEEP").write_text("")
    assert sorted(eng.tick(T0 + timedelta(seconds=1))) == ["k", "m"]
    _wait(eng)
    assert not (root / "inbox" / "READY").exists()
    assert (root / "inbox" / "KEEP").exists()
    assert eng.tick(T0 + timedelta(seconds=2)) == []         # KEEP déjà vu : pas de nouveau run
    (root / "inbox" / "READY").write_text("")                # le témoin revient
    assert eng.tick(T0 + timedelta(seconds=3)) == ["m"]
    _wait(eng)


def test_existing_files_do_not_trigger(tmp_path):
    root = _project(tmp_path, "triggers:\n  - {name: f, type: file, path: 'inbox/*.csv', every: 1s, debounce: 0s}\n")
    (root / "inbox" / "already.csv").write_text("1")
    eng = TriggerEngine(fire_fn=FakeFire(), clock=lambda: T0)
    eng.add_project(root)
    assert eng.tick(T0 + timedelta(seconds=5)) == []


def test_real_run_receives_the_file(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("PYTHONPATH", str(repo) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    root = _project(tmp_path, "triggers:\n  - {name: f, type: file, path: 'inbox/*.csv', every: 1s, debounce: 0s}\n")
    events = []
    eng = TriggerEngine(on_event=events.append, tick=0.2)
    eng.add_project(root)
    eng.start()
    time.sleep(0.5)
    (root / "inbox" / "orders.csv").write_text("id\n1\n")
    deadline = time.time() + 60
    while time.time() < deadline and not any(e["kind"] == "finished" for e in events):
        time.sleep(0.2)
    eng.stop(wait=60)
    done = [e for e in events if e["kind"] == "finished"]
    assert done and done[0]["status"] == "success", done
    assert any("got inbox/orders.csv" in line for line in done[0]["lines"]), done[0]["lines"]
