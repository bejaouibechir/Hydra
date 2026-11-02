"""Step type: project — exécution (0.19, lot 1.2) : in-process et subprocess."""
import json
import os
import sys
from pathlib import Path

import pytest

from hydra_etl.internal.config.env_admin import set_global_var, set_secret_value

REPO = Path(__file__).resolve().parents[1]

PROBE = (
    "import os, json\n"
    "keys = ['SLAVE_DOTENV', 'MASTER_DOTENV', 'LENT', 'GLOBAL_COMMON', 'GLOBAL_ENV', 'HYDRA_ENV']\n"
    "out = {k: os.environ.get(k) for k in keys}\n"
    "out['region'] = '{{ param:region }}'\n"
    "out['pw'] = '${SECRET:slave.pw}'\n"
    "out['cwd'] = os.getcwd()\n"
    "json.dump(out, open('probe.json', 'w'))\n"
)


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _slave(base: Path, name: str = "slave", required: bool = False) -> Path:
    root = base / name
    _write(root / ".hydra" / "project.json", json.dumps({"id": name[:8], "name": name}))
    _write(root / ".env", "SLAVE_DOTENV=from-slave\n")
    decl = "  region: {type: string, default: eu}\n"
    if required:
        decl += "  run_date: {type: string, required: true}\n"
    _write(root / "parameters.yaml", "parameters:\n" + decl)
    _write(root / "environments" / "dev.yaml", "parameters:\n  region: dev-region\n")
    script = "\n".join("          " + ln for ln in PROBE.splitlines())
    _write(root / "workflows" / "main.yaml",
           "workflow:\n  name: main\n  steps:\n    - name: probe\n      type: action\n"
           f"      action: python\n      params:\n        script: |\n{script}\n")
    _write(root / "workflows" / "other.yaml",
           "workflow:\n  name: other\n  steps:\n    - name: mark\n      type: action\n"
           "      action: python\n      params:\n        script: \"open('other.txt','w').write('x')\"\n")
    _write(root / "workflows" / "thread.yaml",
           "thread:\n  - mode: sequential\n    workflows:\n      - name: main\n")
    set_secret_value(root, "slave.pw", "SLAVE-SECRET")
    return root


def _master(base: Path, steps: str, name: str = "master") -> Path:
    root = base / name
    _write(root / ".hydra" / "project.json", json.dumps({"id": name[:8], "name": name}))
    _write(root / ".env", "MASTER_DOTENV=from-master\n")
    _write(root / "workflows" / "main.yaml", "workflow:\n  name: main\n  steps:\n" + steps)
    _write(root / "workflows" / "thread.yaml",
           "thread:\n  - mode: sequential\n    workflows:\n      - name: main\n")
    return root


def _run(master: Path, env=None, params=None):
    from hydra_etl.workflow.project import ProjectRunner, prepare_project
    return ProjectRunner(prepare_project(master), env=env, params=params or {}).run()


def _step_error(res):
    for r in res.runs:
        for st in (r.result.steps if r.result else []):
            if st.error:
                return st.error
    return res.runs[0].error if res.runs else None


@pytest.fixture(params=["inprocess", "subprocess"])
def isolation(request, monkeypatch):
    if request.param == "subprocess":
        monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    return request.param


def test_isolation_params_variables_secrets_env(tmp_path, isolation, monkeypatch):
    set_global_var(None, "GLOBAL_COMMON", "c")
    set_global_var("dev", "GLOBAL_ENV", "g-dev")
    slave = _slave(tmp_path)
    master = _master(tmp_path, f"""    - name: call
      type: project
      project: ../slave
      isolation: {isolation}
      params: {{region: "{{{{ param:zone }}}}"}}
      variables: {{LENT: "lent-{{{{ param:zone }}}}"}}
""")
    _write(master / "parameters.yaml", "parameters:\n  zone: {type: string, default: north}\n")
    before = dict(os.environ)
    res = _run(master, env="dev")
    assert res.success, _step_error(res)
    probe = json.loads((slave / "probe.json").read_text())
    assert probe["SLAVE_DOTENV"] == "from-slave"
    assert probe["MASTER_DOTENV"] is None                # le .env du maître ne passe pas
    assert probe["LENT"] == "lent-north"                 # variables: prêtées
    assert probe["GLOBAL_COMMON"] == "c" and probe["GLOBAL_ENV"] == "g-dev"   # env: inherit
    assert probe["HYDRA_ENV"] == "dev"
    assert probe["region"] == "north"                    # params: plus fort que environments/dev.yaml
    assert probe["pw"] == "SLAVE-SECRET"                 # ses propres secrets
    assert Path(probe["cwd"]).resolve() == slave.resolve()
    # le maître retrouve son environnement
    assert os.environ.get("MASTER_DOTENV") == "from-master"   # le maître garde son .env
    assert "SLAVE_DOTENV" not in os.environ and "LENT" not in os.environ


def test_env_none_and_explicit(tmp_path, isolation):
    set_global_var("dev", "GLOBAL_ENV", "g-dev")
    set_global_var("prod", "GLOBAL_ENV", "g-prod")
    slave = _slave(tmp_path)
    for env_value, expected_env, expected_region in (("none", None, "eu"), ("prod", "g-prod", "eu")):
        master = _master(tmp_path, f"""    - name: call
      type: project
      project: ../slave
      isolation: {isolation}
      env: {env_value}
""", name=f"m-{env_value}")
        res = _run(master, env="dev")
        assert res.success, _step_error(res)
        probe = json.loads((slave / "probe.json").read_text())
        assert probe["GLOBAL_ENV"] == expected_env and probe["region"] == expected_region


def test_master_secret_is_not_visible(tmp_path, isolation):
    slave = _slave(tmp_path)
    f = slave / "workflows" / "main.yaml"
    f.write_text(f.read_text().replace("${SECRET:slave.pw}", "${SECRET:master.only}"))
    master = _master(tmp_path, f"""    - name: call
      type: project
      project: ../slave
      isolation: {isolation}
""")
    set_secret_value(master, "master.only", "MASTER-SECRET")
    res = _run(master)
    assert not res.success
    assert "master.only" in (_step_error(res) or "") or "failed" in (_step_error(res) or "")


def test_required_parameter_checked_before_start(tmp_path):
    slave = _slave(tmp_path, required=True)
    master = _master(tmp_path, """    - name: call
      type: project
      project: ../slave
""")
    res = _run(master)
    assert not res.success and "run_date" in _step_error(res)
    assert not (slave / "probe.json").exists()


def test_only_the_listed_workflows(tmp_path, isolation):
    slave = _slave(tmp_path)
    master = _master(tmp_path, f"""    - name: call
      type: project
      project: ../slave
      isolation: {isolation}
      workflows: [other]
""")
    assert _run(master).success
    assert (slave / "other.txt").exists() and not (slave / "probe.json").exists()


def test_runtime_cycle_through_a_computed_path(tmp_path):
    """Chemin calculé ({{ param }}) : invisible à la validation, arrêté au run."""
    a = _master(tmp_path, """    - name: call
      type: project
      project: "{{ param:target }}"
""", name="a")
    _write(a / "parameters.yaml", "parameters:\n  target: {type: string, default: ../b}\n")
    b = _master(tmp_path, """    - name: back
      type: project
      project: ../a
""", name="b")
    res = _run(a)
    assert not res.success
    assert "cycle" in json.dumps([str(_step_error(res))])


def test_parallel_steps_switch_to_subprocess(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    s1 = _slave(tmp_path, "s1")
    s2 = _slave(tmp_path, "s2")
    master = _master(tmp_path, """    - name: one
      type: project
      project: ../s1
    - name: two
      type: project
      project: ../s2
""")
    res = _run(master)
    assert res.success, _step_error(res)
    logs = "\n".join(l for r in res.runs for st in r.result.steps for l in st.logs)
    assert logs.count("runs in a separate process") == 2
    assert (s1 / "probe.json").exists() and (s2 / "probe.json").exists()


def test_cli_run_only_workflows(tmp_path):
    from click.testing import CliRunner
    from hydra_etl.cli.hdrctl import cli
    slave = _slave(tmp_path)
    r = CliRunner().invoke(cli, ["run", str(slave), "-w", "other"])
    assert r.exit_code == 0, r.output
    assert (slave / "other.txt").exists() and not (slave / "probe.json").exists()
