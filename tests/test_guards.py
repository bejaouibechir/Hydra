"""hydra_check_job alerts (hydra_etl/ai/guards.py): false alarms seen in the MCP campaign."""
from __future__ import annotations

import yaml

from hydra_etl.ai.guards import check


def _docs(**files):
    texts = {f"{k}.yaml": v for k, v in files.items()}
    return texts, {k: yaml.safe_load(v) for k, v in texts.items()}


SQLITE_SRC = "sources:\n  orders:\n    type: sqlite\n    connection: {path: ../../data/shop.db}\n    extract: {table: orders}\n"


def test_output_csv_is_not_taken_for_the_input():
    texts, docs = _docs(
        sources=SQLITE_SRC,
        destinations="destinations:\n  report:\n    type: csv\n    load: {table: ../../outputs/monthly_revenue.csv}\n",
        pipeline="pipeline: {from: orders, to: report}\n",
        transformations="steps:\n  - filter: {expr: \"status == 'paid'\"}\n  - aggregate: {by: [m], agg: {n: {func: count, col: id}}}\n  - sort: {by: [m]}\n")
    prompt = ("Using data/shop.db, build a job that gives, for each month, the number of paid orders. "
              "Write outputs/monthly_revenue.csv with the columns month, orders, oldest month first.")
    assert not any("requested input" in a for a in check(prompt, texts, docs))


def test_a_real_csv_input_is_still_checked():
    texts, docs = _docs(
        sources=SQLITE_SRC,
        destinations="destinations:\n  out:\n    type: csv\n    load: {table: ../../outputs/out.csv}\n",
        pipeline="pipeline: {from: orders, to: out}\n")
    prompt = "Load data/customers.csv into outputs/out.csv"
    assert any("requested input is '.csv'" in a for a in check(prompt, texts, docs))


def test_upsert_answers_never_duplicate():
    texts, docs = _docs(
        sources=SQLITE_SRC,
        destinations="destinations:\n  wh:\n    type: sqlite\n    connection: {path: ../../outputs/w.db}\n"
                     "    load: {table: orders, mode: upsert, key: [order_id]}\n",
        pipeline="pipeline: {from: orders, to: wh}\n",
        transformations="steps:\n  - cast: {mapping: {amount: float}}\n")
    prompt = ("Copy the orders table into outputs/w.db. order_id is the key: running the job again must "
              "update the existing rows, never duplicate them.")
    assert not any("deduplicate" in a for a in check(prompt, texts, docs))


def test_update_the_existing_rows_asks_for_upsert():
    texts, docs = _docs(
        sources=SQLITE_SRC,
        destinations="destinations:\n  wh:\n    type: sqlite\n    connection: {path: ../../outputs/w.db}\n"
                     "    load: {table: orders, mode: upsert, key: [order_id]}\n",
        pipeline="pipeline: {from: orders, to: wh}\n")
    prompt = "order_id is the key: running the job again must update the existing rows."
    assert not any("mode" in a for a in check(prompt, texts, docs))
