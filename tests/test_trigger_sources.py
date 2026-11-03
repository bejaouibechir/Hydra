"""Déclencheurs source_change : mesure d'une source et moteur (0.19, lot 2.4)."""
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hydra_etl.triggers.core import FireResult
from hydra_etl.triggers.engine import TriggerEngine
from hydra_etl.triggers.models import SourceRef
from hydra_etl.triggers.sources import SourceMeasureError, _sql, measure

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)


def _project(base: Path, triggers: str = "") -> Path:
    root = base / "p"
    (root / ".hydra").mkdir(parents=True)
    (root / ".hydra" / "project.json").write_text(json.dumps({"id": "p", "name": "p"}))
    job = root / "jobs" / "ingest"
    job.mkdir(parents=True)
    (job / "sources.yaml").write_text(
        'version: "1.0"\nsources:\n  orders:\n    type: csv\n    connection: {}\n'
        "    extract:\n      table: ../../data/orders.csv\n")
    (job / "destinations.yaml").write_text(
        'version: "1.0"\ndestinations:\n  out:\n    type: csv\n    connection: {}\n'
        "    load:\n      table: ../../out/o.csv\n      mode: replace\n")
    (job / "pipeline.yaml").write_text('version: "1.0"\npipeline:\n  from: orders\n  to: out\n')
    (root / "data").mkdir()
    (root / "data" / "orders.csv").write_text("id,amount,updated\n1,45,2026-11-01\n2,120,2026-11-02\n3,9,2026-10-30\n")
    (root / "workflows").mkdir()
    (root / "workflows" / "main.yaml").write_text(
        "workflow:\n  name: main\n  steps:\n    - {name: s, type: action, action: log, params: {message: hi}}\n")
    (root / "workflows" / "thread.yaml").write_text(
        "thread:\n  - mode: sequential\n    workflows:\n      - name: main\n")
    if triggers:
        (root / "triggers.yaml").write_text(triggers)
    return root


# ── Mesure ────────────────────────────────────────────────────────────────

def test_measure_csv(tmp_path):
    root = _project(tmp_path)
    ref = lambda **kw: SourceRef(job="jobs/ingest", id="orders", **kw)   # noqa: E731
    assert measure(root, ref(check="count")) == "3"
    assert measure(root, ref(check="max", column="amount")) == "120"      # numérique, pas texte
    assert measure(root, ref(check="max", column="updated")) == "2026-11-02"
    c1 = measure(root, ref(check="checksum"))
    (root / "data" / "orders.csv").write_text("id,amount,updated\n1,46,2026-11-01\n")
    assert measure(root, ref(check="checksum")) != c1
    assert measure(root, ref(check="count")) == "1"


def test_measure_errors(tmp_path):
    root = _project(tmp_path)
    with pytest.raises(SourceMeasureError, match="column 'nope' not found"):
        measure(root, SourceRef(job="jobs/ingest", id="orders", check="max", column="nope"))
    with pytest.raises(SourceMeasureError, match="ghost"):
        measure(root, SourceRef(job="jobs/ingest", id="ghost"))
    (root / "data" / "orders.csv").unlink()
    with pytest.raises(SourceMeasureError):
        measure(root, SourceRef(job="jobs/ingest", id="orders"))


class _SqliteConn:
    def __init__(self, db):
        self.db = db

    def _connect(self):
        return sqlite3.connect(self.db)


def test_sql_aggregate(tmp_path):
    db = str(tmp_path / "t.db")
    c = sqlite3.connect(db)
    c.execute("create table orders(id int, updated text)")
    c.executemany("insert into orders values (?, ?)", [(1, "2026-11-01"), (2, "2026-11-03")])
    c.commit()
    c.close()
    conn = _SqliteConn(db)
    assert _sql(conn, "postgresql", "orders", None, "count", None) == "2"
    assert _sql(conn, "postgresql", "orders", None, "max", "updated") == "2026-11-03"
    assert _sql(conn, "postgresql", None, "select * from orders where id > 1", "count", None) == "1"


def test_column_name_is_checked(tmp_path):
    with pytest.raises(SourceMeasureError, match="letters, digits"):
        measure(tmp_path, SourceRef(job="j", id="s", check="max", column="a; drop table x"))


# ── Moteur ────────────────────────────────────────────────────────────────

TRIG = "triggers:\n  - {name: s, type: source_change, source: {job: jobs/ingest, id: orders}, every: 1m}\n"


class FakeMeasure:
    def __init__(self, values):
        self.values = list(values)

    def __call__(self, root, source, env):
        v = self.values.pop(0)
        if isinstance(v, Exception):
            raise v
        return v


class FakeFire:
    def __init__(self):
        self.calls, self.gate = [], threading.Event()
        self.gate.set()

    def __call__(self, root, trig, **kw):
        self.calls.append(kw.get("extra_params"))
        self.gate.wait(5)
        return FireResult(trig.name, "success", None, [], 0.1)


def _settle(eng):
    """Attend les threads de mesure et de run, sans avancer l'horloge."""
    import time
    for _ in range(100):
        busy = any(w.measuring for st in eng.projects.values() for w in st.watched.values())
        if not busy:
            break
        time.sleep(0.02)
    for th in list(eng._runs):
        th.join(5)


def _step(eng, minutes):
    eng.tick(T0 + timedelta(minutes=minutes))
    _settle(eng)
    eng.tick(T0 + timedelta(minutes=minutes, seconds=1))      # traite le résultat de la mesure
    _settle(eng)


def test_change_starts_a_run_with_values(tmp_path):
    root = _project(tmp_path, TRIG)
    fake, events = FakeFire(), []
    eng = TriggerEngine(fire_fn=fake, measure_fn=FakeMeasure(["10", "10", "12"]),
                        clock=lambda: T0, on_event=events.append)
    eng.add_project(root)
    _step(eng, 0)                                             # référence
    assert eng.status()[0]["value"] == "10" and fake.calls == []
    assert any(e["kind"] == "measured" and e["value"] == "10" for e in events)
    _step(eng, 1)                                             # inchangé
    assert fake.calls == []
    _step(eng, 2)                                             # 10 → 12
    assert fake.calls == [{"trigger.value": "12", "trigger.previous": "10"}]


def test_measure_error_keeps_the_reference(tmp_path):
    root = _project(tmp_path, TRIG)
    fake, events = FakeFire(), []
    eng = TriggerEngine(fire_fn=fake, measure_fn=FakeMeasure(["5", RuntimeError("db down"), "5"]),
                        clock=lambda: T0, on_event=events.append)
    eng.add_project(root)
    _step(eng, 0)
    _step(eng, 1)
    assert any(e["kind"] == "error" and "db down" in e["error"] for e in events)
    _step(eng, 2)
    assert fake.calls == [] and eng.status()[0]["value"] == "5"


def test_change_during_a_run_is_not_lost(tmp_path):
    root = _project(tmp_path, TRIG)
    fake = FakeFire()
    eng = TriggerEngine(fire_fn=fake, measure_fn=FakeMeasure(["1", "2", "3", "3"]), clock=lambda: T0)
    eng.add_project(root)
    _step(eng, 0)
    fake.gate.clear()
    eng.tick(T0 + timedelta(minutes=1))                       # mesure 2
    _settle(eng)
    eng.tick(T0 + timedelta(minutes=1, seconds=1))            # 1 → 2 : run (bloqué)
    eng.tick(T0 + timedelta(minutes=2))                       # mesure 3 pendant le run
    import time
    time.sleep(0.2)
    eng.tick(T0 + timedelta(minutes=2, seconds=1))
    assert len(fake.calls) == 1
    fake.gate.set()
    _settle(eng)
    eng.tick(T0 + timedelta(minutes=2, seconds=2))
    _settle(eng)
    assert fake.calls[1] == {"trigger.value": "3", "trigger.previous": "2"}
