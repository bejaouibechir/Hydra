"""Modèle du thread de projet (workflows/thread.yaml)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hydra_etl.workflow.thread import (
    default_thread_yaml, load_thread, missing_workflow_files, parse_delay, parse_thread,
)


@pytest.mark.parametrize("value,seconds", [
    (None, 0.0), (0, 0.0), (5, 5.0), (2.5, 2.5), ("30", 30.0), ("30s", 30.0),
    ("5m", 300.0), ("1h", 3600.0), ("500ms", 0.5), (" 2 M ", 120.0),
])
def test_parse_delay(value, seconds):
    assert parse_delay(value) == seconds


@pytest.mark.parametrize("value", ["abc", "5d", "-3", -1, True, "1h30"])
def test_parse_delay_rejects(value):
    with pytest.raises(ValueError):
        parse_delay(value)


def test_full_thread():
    th = parse_thread({"version": "1.0", "thread": [
        {"mode": "sequential", "delay_after": "30s",
         "workflows": [{"name": "a"}, {"name": "b", "active": False}]},
        {"mode": "parallel", "workflows": [{"name": "c"}, {"name": "d.yaml"}]},
    ]})
    assert th.workflow_names() == ["a", "b", "c", "d"]
    assert th.thread[0].delay_seconds == 30
    assert th.thread[1].delay_seconds == 0
    assert th.thread[0].workflows[1].active is False
    assert th.thread[0].workflows[0].active is True


def test_defaults():
    th = parse_thread({"thread": [{"workflows": [{"name": "a"}]}]})
    assert th.version == "1.0"
    assert th.thread[0].mode == "sequential"


def test_empty_thread_is_valid():
    assert parse_thread({"thread": []}).workflow_names() == []
    assert parse_thread(None).workflow_names() == []


@pytest.mark.parametrize("data,fragment", [
    ({"thread": [{"mode": "random", "workflows": [{"name": "a"}]}]}, "mode"),
    ({"thread": [{"workflows": []}]}, "workflows"),
    ({"thread": [{"workflows": [{"name": "a"}]}, {"workflows": [{"name": "a"}]}]}, "more than once"),
    ({"thread": [{"delay_after": "2x", "workflows": [{"name": "a"}]}]}, "invalid delay"),
    ({"thread": [{"workflows": [{"name": "a", "enabled": True}]}]}, "enabled"),
    ({"thread": [{"workflows": [{"name": "../evil"}]}]}, "invalid workflow name"),
    ({"stages": []}, "stages"),
    (["a"], "mapping"),
])
def test_invalid_threads(data, fragment):
    with pytest.raises(ValueError, match=fragment.replace(".", r"\.")):
        parse_thread(data)


def test_missing_workflow_files(tmp_path):
    (tmp_path / "a.yaml").write_text("x", encoding="utf-8")
    (tmp_path / "b.yml").write_text("x", encoding="utf-8")
    th = parse_thread({"thread": [{"workflows": [{"name": "a"}, {"name": "b"}, {"name": "c"}]}]})
    assert missing_workflow_files(th, tmp_path) == ["c"]


def test_default_thread_yaml_roundtrip(tmp_path):
    f = tmp_path / "thread.yaml"
    f.write_text(default_thread_yaml(["w1", "w2"]), encoding="utf-8")
    th = load_thread(f)
    assert th.workflow_names() == ["w1", "w2"]
    assert all(w.active for w in th.thread[0].workflows)


def test_load_thread_bad_yaml(tmp_path):
    f = tmp_path / "thread.yaml"
    f.write_text("thread: [\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid YAML"):
        load_thread(f)


# ── Boucles ───────────────────────────────────────────────────────────────────

from hydra_etl.workflow.thread import remove_from_thread, render_thread  # noqa: E402


def _t(loops, stages=None):
    stages = stages or [
        {"workflows": [{"name": "a"}, {"name": "b"}]},
        {"mode": "parallel", "workflows": [{"name": "c"}, {"name": "d"}]},
        {"workflows": [{"name": "e"}]},
    ]
    return parse_thread({"thread": stages, "loops": loops})


def test_units_and_positions():
    th = _t([])
    assert [(u.stage, u.names, u.parallel, u.last_in_stage) for u in th.units()] == [
        (0, ["a"], False, False), (0, ["b"], False, True), (1, ["c", "d"], True, True), (2, ["e"], False, True)]
    assert th.unit_of("d") == 2


def test_valid_loops_and_roundtrip(tmp_path):
    th = _t([{"from": "d", "to": "b", "times": 3, "delay": "5m"}, {"from": "e", "to": "e", "times": 2}])
    assert th.loops[0].from_ == "d" and th.loops[0].delay_seconds == 300
    f = tmp_path / "thread.yaml"
    f.write_text(render_thread(th), encoding="utf-8")
    assert load_thread(f) == th
    assert th.model_dump(by_alias=True)["loops"][0]["from"] == "d"


@pytest.mark.parametrize("loops,fragment", [
    ([{"from": "a", "to": "e", "times": 2}], "must come before"),
    ([{"from": "x", "to": "a", "times": 2}], "not in the thread"),
    ([{"from": "c", "to": "a", "times": 0}], "times"),
    ([{"from": "c", "to": "a", "times": 1001}], "times"),
    ([{"from": "c", "to": "a", "times": 2, "delay": "soon"}], "invalid delay"),
    ([{"from": "c", "to": "a", "times": 2}, {"from": "e", "to": "d", "times": 2}], "overlap"),
    ([{"from": "c", "to": "a", "times": 2, "every": 1}], "every"),
])
def test_invalid_loops(loops, fragment):
    with pytest.raises(ValueError, match=fragment):
        _t(loops)


def test_d_and_c_share_a_position_in_a_parallel_stage():
    # c et d sont dans la même étape parallèle : une boucle d -> c est valide
    assert _t([{"from": "c", "to": "d", "times": 2}]).loops[0].to == "d"


def test_removing_a_workflow_drops_its_loops():
    th = _t([{"from": "d", "to": "b", "times": 3}, {"from": "e", "to": "e", "times": 2}])
    th2, found = remove_from_thread(th, "b")
    assert found and [(lp.from_, lp.to) for lp in th2.loops] == [("e", "e")]
