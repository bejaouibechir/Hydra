"""Étape 5b sur une vraie base (pannes provoquées) : timeout au milieu d'un
chargement PostgreSQL en tout ou rien, puis bascule ; rollback puis bascule.

Lancer avec, par exemple :
  HYDRA_TEST_PG="host=127.0.0.1 port=5432 user=postgres password=x database=hydra"
"""
from __future__ import annotations

import os
import textwrap
from pathlib import Path

import pytest

from hydra_etl.workflow.project import RECOVERED, SUCCESS, ProjectRunner, prepare_project


def _pg_conn() -> dict:
    raw = os.environ.get("HYDRA_TEST_PG")
    if not raw:
        pytest.skip("HYDRA_TEST_PG not set")
    pytest.importorskip("psycopg2")
    return dict(kv.split("=", 1) for kv in raw.split())


@pytest.fixture
def pg():
    import psycopg2
    conn = _pg_conn()
    cn = psycopg2.connect(host=conn["host"], port=int(conn["port"]), user=conn["user"],
                          password=conn.get("password"), dbname=conn["database"])
    cn.autocommit = True
    cur = cn.cursor()
    cur.execute("DROP TABLE IF EXISTS fb_sales; CREATE TABLE fb_sales (id int, v text);"
                "INSERT INTO fb_sales VALUES (0, 'old');")

    def rows():
        cur.execute("SELECT count(*), min(v) FROM fb_sales")
        return cur.fetchone()
    yield conn, rows
    cur.execute("DROP TABLE IF EXISTS fb_sales")
    cn.close()


def _project(tmp_path: Path, conn: dict, n_rows: int, main_steps: str, rollback: bool,
             thread_extra: str) -> Path:
    root = tmp_path / "p"
    (root / ".hydra").mkdir(parents=True)
    (root / "workflows").mkdir()
    data = root / "data"
    data.mkdir()
    with open(data / "big.csv", "w", encoding="utf-8") as f:
        f.write("id,v\n")
        f.writelines(f"{i},row{i}\n" for i in range(1, n_rows + 1))
    j = root / "jobs" / "load_pg"
    j.mkdir(parents=True)
    (j / "sources.yaml").write_text(textwrap.dedent("""\
        sources:
          src:
            type: csv
            extract:
              table: ../../data/big.csv
              batch_size: 100
        """), encoding="utf-8")
    c = "\n".join(f"        {k}: {v}" for k, v in conn.items())
    (j / "destinations.yaml").write_text(
        "destinations:\n  dst:\n    type: postgresql\n    connection:\n" + c.replace("        ", "      ")
        + "\n    load:\n      table: fb_sales\n      mode: replace\n", encoding="utf-8")
    (j / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")
    bad = root / "jobs" / "broken"
    bad.mkdir()
    (bad / "sources.yaml").write_text("sources:\n  src:\n    type: csv\n    extract:\n"
                                      "      table: ../../data/missing.csv\n", encoding="utf-8")
    (bad / "destinations.yaml").write_text("destinations:\n  dst:\n    type: csv\n    load:\n"
                                           "      table: ../../data/out.csv\n      mode: replace\n",
                                           encoding="utf-8")
    (bad / "pipeline.yaml").write_text("pipeline:\n  from: src\n  to: dst\n", encoding="utf-8")
    (root / "workflows" / "main.yaml").write_text(
        "workflow:\n  name: main\n" + ("  rollback: true\n" if rollback else "") + "  steps:\n"
        + textwrap.indent(textwrap.dedent(main_steps), "    "), encoding="utf-8")
    marker = (root / "backup.txt").as_posix()
    (root / "workflows" / "backup.yaml").write_text(textwrap.dedent(f"""\
        workflow:
          name: backup
          steps:
            - name: mark
              type: action
              action: python
              params:
                script: "open(r'{marker}', 'w').write('backup ran')"
        """), encoding="utf-8")
    (root / "workflows" / "thread.yaml").write_text(
        'version: "1.0"\nthread:\n  - workflows:\n      - name: main\n' + thread_extra
        + "        fallback:\n          use: [backup]\n          on_failure: true\n", encoding="utf-8")
    return root


LOAD = "    - name: load\n      type: job\n      job: ../jobs/load_pg\n"


def test_timeout_mid_load_leaves_the_table_intact_then_switches(pg, tmp_path):
    conn, rows = pg
    root = _project(tmp_path, conn, 300_000, LOAD, rollback=False, thread_extra="        timeout: 1s\n")
    events = []
    res = ProjectRunner(prepare_project(root)).run(lambda k, d: events.append((k, d)))
    main = res.runs[0]
    assert main.status == RECOVERED and main.timed_out, main.error
    assert "timed out after 1s" in main.error
    # le job a été coupé entre deux lots : la publication en tout ou rien est annulée
    jr = main.result.steps[0].job_result
    assert 0 < jr.rows_in < 300_000 and not jr.partial_write
    assert rows() == (1, "old")
    assert res.success and res.runs[1].status == SUCCESS
    assert (root / "backup.txt").read_text() == "backup ran"
    assert [d["trigger"] for k, d in events if k == "fallback"] == ["timeout"]


def test_rollback_of_a_published_load_then_switches(pg, tmp_path):
    conn, rows = pg
    steps = LOAD + """\
    - name: last
      type: job
      job: ../jobs/broken
      depends_on: [load]
    """
    root = _project(tmp_path, conn, 500, steps, rollback=True, thread_extra="")
    res = ProjectRunner(prepare_project(root)).run()
    main = res.runs[0]
    assert main.status == RECOVERED and main.result.rollback["status"] == "done"
    assert rows() == (1, "old")                    # chargement publié puis défait
    assert res.success and (root / "backup.txt").exists()


def test_published_load_without_rollback_blocks_the_switch(pg, tmp_path):
    conn, rows = pg
    steps = LOAD + """\
    - name: last
      type: job
      job: ../jobs/broken
      depends_on: [load]
    """
    root = _project(tmp_path, conn, 500, steps, rollback=False, thread_extra="")
    res = ProjectRunner(prepare_project(root)).run()
    assert not res.success and not (root / "backup.txt").exists()
    assert "step 'load' had already published its data" in res.runs[0].error
    assert rows() == (500, "row1")                 # les données publiées restent (pas de doublon)
