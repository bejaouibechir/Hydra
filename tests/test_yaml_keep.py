"""Studio écrit les YAML sans abîmer ce que l'utilisateur a écrit (hydra_etl/api/yaml_keep.py)."""
from __future__ import annotations

from pathlib import Path

import yaml

from hydra_etl.api.yaml_keep import write_yaml_keeping

SRC = '''# Snowflake source
version: "1.0"
sources:
  snowflake_orders:
    type: snowflake
    connection:
      account: "{{ env:SNOWFLAKE_ACCOUNT }}"
      private_key_file: "{{ env:SNOWFLAKE_PRIVATE_KEY_FILE }}"   # key-pair authentication
      database: SALES
      # lowercase for PostgreSQL
      column_case: lower        # ORDER_ID -> order_id
    extract:
      table: ORDERS
      batch_size: 10000
'''
# ce que Studio produit pour le même contenu (js-yaml : guillemets simples, sans commentaire)
SRC_STUDIO = '''version: '1.0'
sources:
  snowflake_orders:
    type: snowflake
    connection:
      account: '{{ env:SNOWFLAKE_ACCOUNT }}'
      private_key_file: '{{ env:SNOWFLAKE_PRIVATE_KEY_FILE }}'
      database: SALES
      column_case: lower
    extract:
      table: ORDERS
      batch_size: 10000
'''


def test_same_content_is_not_rewritten(tmp_path: Path):
    f = tmp_path / "sources.yaml"
    f.write_text(SRC, encoding="utf-8")
    assert write_yaml_keeping(f, SRC_STUDIO, kind="sources") is False
    assert f.read_text(encoding="utf-8") == SRC


def test_changed_value_keeps_comments_and_quotes_elsewhere(tmp_path: Path):
    f = tmp_path / "sources.yaml"
    f.write_text(SRC, encoding="utf-8")
    new = SRC_STUDIO.replace("database: SALES", "database: SALES_V2")
    assert write_yaml_keeping(f, new, kind="sources") is True
    text = f.read_text(encoding="utf-8")
    assert yaml.safe_load(text) == yaml.safe_load(new)
    assert text.startswith("# Snowflake source\n")
    assert '"{{ env:SNOWFLAKE_PRIVATE_KEY_FILE }}"   # key-pair authentication' in text
    assert "      # lowercase for PostgreSQL\n      column_case: lower        # ORDER_ID -> order_id" in text
    assert "database: SALES_V2" in text


def test_inline_list_is_kept_when_unchanged(tmp_path: Path):
    f = tmp_path / "destinations.yaml"
    f.write_text('version: "1.0"\ndestinations:\n  pg:\n    type: postgresql\n    load:\n'
                 '      table: orders\n      mode: upsert   # no duplicates\n      key: [order_id]   # primary key\n',
                 encoding="utf-8")
    new = ("version: '1.0'\ndestinations:\n  pg:\n    type: postgresql\n    load:\n"
           "      table: orders2\n      mode: upsert\n      key:\n        - order_id\n")
    write_yaml_keeping(f, new, kind="destinations")
    text = f.read_text(encoding="utf-8")
    assert yaml.safe_load(text) == yaml.safe_load(new)
    assert "key: [order_id]   # primary key" in text and "- order_id" not in text
    assert "mode: upsert   # no duplicates" in text


def test_workflow_keeps_description_and_does_not_add_default_trigger(tmp_path: Path):
    f = tmp_path / "migrate.yaml"
    old = ('version: "1.0"\nworkflow:\n  name: migrate\n  description: Copy orders   # why\n  steps:\n'
           '    - name: orders\n      type: job\n      job: ../jobs/orders\n')
    f.write_text(old, encoding="utf-8")
    studio = ('version: "1.0"\nworkflow:\n  name: migrate\n  trigger:\n    type: manual\n  steps:\n'
              '    - name: orders\n      type: job\n      job: ../jobs/orders\n')
    assert write_yaml_keeping(f, studio, kind="workflow") is False
    assert f.read_text(encoding="utf-8") == old
    studio2 = studio + "    - name: report\n      type: job\n      job: ../jobs/report\n      depends_on: [orders]\n"
    assert write_yaml_keeping(f, studio2, kind="workflow") is True
    doc = yaml.safe_load(f.read_text(encoding="utf-8"))["workflow"]
    assert doc["description"] == "Copy orders"
    assert list(doc)[:2] == ["name", "description"]
    assert "trigger" not in doc
    assert [s["name"] for s in doc["steps"]] == ["orders", "report"]


def test_explicit_trigger_is_written(tmp_path: Path):
    f = tmp_path / "wf.yaml"
    f.write_text('version: "1.0"\nworkflow:\n  name: wf\n  steps: []\n', encoding="utf-8")
    studio = "version: '1.0'\nworkflow:\n  name: wf\n  trigger:\n    type: schedule\n    cron: 0 6 * * *\n  steps: []\n"
    assert write_yaml_keeping(f, studio, kind="workflow") is True
    assert yaml.safe_load(f.read_text(encoding="utf-8"))["workflow"]["trigger"]["cron"] == "0 6 * * *"


def test_pipeline_name_added_by_studio_is_not_written(tmp_path: Path):
    f = tmp_path / "pipeline.yaml"
    old = 'version: "1.0"\npipeline:\n  from: a\n  to: b\n'
    f.write_text(old, encoding="utf-8")
    studio = "version: '1.0'\npipeline:\n  name: myjob\n  from: a\n  to: b\n"
    assert write_yaml_keeping(f, studio, kind="pipeline", job_name="myjob") is False
    assert f.read_text(encoding="utf-8") == old


def test_transformation_steps_keep_their_comments(tmp_path: Path):
    f = tmp_path / "transformations.yaml"
    old = ('version: "1.0"\nsteps:\n  # paid orders only\n  - filter:\n      expr: "status == \'paid\'"\n'
           '  - cast:\n      mapping:\n        amount: float   # was text\n')
    f.write_text(old, encoding="utf-8")
    studio = ("version: '1.0'\nsteps:\n  - filter:\n      expr: status == 'paid'\n  - cast:\n      mapping:\n"
              "        amount: float\n  - sort:\n      by: amount\n")
    write_yaml_keeping(f, studio, kind="transformations")
    text = f.read_text(encoding="utf-8")
    assert yaml.safe_load(text) == yaml.safe_load(studio)
    assert "  # paid orders only\n" in text and "amount: float   # was text" in text


def test_new_file_and_invalid_old_file(tmp_path: Path):
    f = tmp_path / "pipeline.yaml"
    assert write_yaml_keeping(f, "pipeline:\n  from: a\n  to: b\n", kind="pipeline") is True
    f.write_text("pipeline: [unclosed\n", encoding="utf-8")
    assert write_yaml_keeping(f, "pipeline:\n  from: a\n  to: b\n", kind="pipeline") is True
    assert yaml.safe_load(f.read_text(encoding="utf-8")) == {"pipeline": {"from": "a", "to": "b"}}
