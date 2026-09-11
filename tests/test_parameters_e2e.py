"""
Test end-to-end de l'étage 1 : paramètres résolus par le runner.

Job CSV -> cast -> filter (utilise {{ param:min_qty }}) -> script (utilise
params[...]) -> CSV, avec un environments/dev.yaml et une surcharge runtime.
Prouve : résolution {{ param }} dans les YAML + injection du dict `params`
(lecture seule) dans le nœud script + précédence env/runtime.
"""

import csv
from pathlib import Path

from hydra_etl.internal.runner.executor import JobExecutor


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_job_with_parameters(tmp_path):
    root = tmp_path / "project"
    job = root / "jobs" / "orders"
    data_in = job / "in.csv"
    data_out = job / "out.csv"

    # Déclarations (contrat) au niveau projet
    _write(root / "parameters.yaml", """
parameters:
  markup:  { type: float,  default: 1.0 }
  label:   { type: string, default: "base" }
  min_qty: { type: int,    default: 0 }
""")
    # Valeurs de l'environnement dev
    _write(root / "environments" / "dev.yaml", """
parameters:
  markup: 1.2
  label: dev_run
""")

    _write(data_in, "id,price,qty\n1,100,3\n2,50,1\n3,200,5\n")

    _write(job / "sources.yaml", f"""
version: "1.0"
sources:
  src:
    type: csv
    connection: {{}}
    extract: {{ table: "{data_in.as_posix()}" }}
""")
    _write(job / "destinations.yaml", f"""
version: "1.0"
destinations:
  dst:
    type: csv
    connection: {{}}
    load: {{ table: "{data_out.as_posix()}", mode: replace }}
""")
    _write(job / "pipeline.yaml", """
version: "1.0"
pipeline:
  name: orders
  from: src
  to: dst
  transformations: transformations
""")
    # filter utilise {{ param:min_qty }} (substitution string) ;
    # script utilise params["markup"] / params["label"] (dict injecté).
    _write(job / "transformations.yaml", """
version: "1.0"
transformations:
  steps:
    - cast: { mapping: { price: float, qty: int } }
    - filter: { expr: "qty >= {{ param:min_qty }}" }
    - script:
        inputs: [price]
        outputs: { final_price: float, tag: str }
        mode: vectorized
        code: |
          final_price = price * params["markup"]
          tag = params["label"]
""")

    # env=dev -> markup 1.2, label dev_run ; runtime -> min_qty=2 (surcharge le défaut 0)
    ex = JobExecutor(job_dir=job, root_dir=root, env="dev", params={"min_qty": 2})
    result = ex.run()
    assert getattr(result, "success", True), getattr(result, "error", None)

    rows = list(csv.DictReader(data_out.open(encoding="utf-8")))
    # qty >= 2 -> lignes id 1 (qty 3) et id 3 (qty 5) ; id 2 (qty 1) filtrée
    ids = sorted(r["id"] for r in rows)
    assert ids == ["1", "3"]
    by_id = {r["id"]: r for r in rows}
    # markup 1.2 depuis dev.yaml
    assert float(by_id["1"]["final_price"]) == 120.0
    assert float(by_id["3"]["final_price"]) == 240.0
    # label dev_run injecté via params
    assert by_id["1"]["tag"] == "dev_run"


def test_required_param_missing_fails(tmp_path):
    """Un paramètre requis sans valeur ni défaut -> le job échoue proprement."""
    root = tmp_path / "project"
    job = root / "jobs" / "j"
    _write(root / "parameters.yaml", "parameters:\n  schema: { type: string, required: true }\n")
    _write(job / "in.csv", "id\n1\n")
    _write(job / "sources.yaml", f'version: "1.0"\nsources:\n  src: {{ type: csv, connection: {{}}, extract: {{ table: "{(job / "in.csv").as_posix()}" }} }}\n')
    _write(job / "destinations.yaml", f'version: "1.0"\ndestinations:\n  dst: {{ type: csv, connection: {{}}, load: {{ table: "{(job / "out.csv").as_posix()}", mode: replace }} }}\n')
    _write(job / "pipeline.yaml", 'version: "1.0"\npipeline: { name: j, from: src, to: dst }\n')

    import pytest
    with pytest.raises(Exception):
        JobExecutor(job_dir=job, root_dir=root, env="dev")


def test_parameters_found_up_the_tree(tmp_path):
    """Nidification façon Studio : job dans project/jobs/<name>, params à la racine
    projet. Sans root_dir explicite, le runner remonte l'arborescence et les trouve."""
    project = tmp_path / "project"
    job = project / "jobs" / "orders"
    (project / "workflows").mkdir(parents=True)  # marqueur racine projet

    _write(project / "parameters.yaml", "parameters:\n  markup: { type: float, default: 1.0 }\n")
    _write(project / "environments" / "dev.yaml", "parameters: { markup: 2.0 }\n")
    _write(job / "in.csv", "id,price\n1,100\n")
    _write(job / "sources.yaml", f'version: "1.0"\nsources:\n  src: {{ type: csv, connection: {{}}, extract: {{ table: "{(job / "in.csv").as_posix()}" }} }}\n')
    _write(job / "destinations.yaml", f'version: "1.0"\ndestinations:\n  dst: {{ type: csv, connection: {{}}, load: {{ table: "{(job / "out.csv").as_posix()}", mode: replace }} }}\n')
    _write(job / "pipeline.yaml", 'version: "1.0"\npipeline: { name: orders, from: src, to: dst, transformations: transformations }\n')
    _write(job / "transformations.yaml", """
version: "1.0"
transformations:
  steps:
    - cast: { mapping: { price: float } }
    - script:
        inputs: [price]
        outputs: { scaled: float }
        mode: vectorized
        code: |
          scaled = price * params["markup"]
""")

    # PAS de root_dir -> root_dir par defaut = job.parent = project/jobs ; la recherche
    # ascendante doit trouver les params a project/.
    import csv
    ex = JobExecutor(job_dir=job, env="dev")
    ex.run()
    rows = list(csv.DictReader((job / "out.csv").open(encoding="utf-8")))
    assert float(rows[0]["scaled"]) == 200.0  # markup 2.0 depuis project/environments/dev.yaml
