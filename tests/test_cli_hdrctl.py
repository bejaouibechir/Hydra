"""
Tests de la CLI hdrctl.

Couvre :
1. Commande --help / --version
2. Commande init (tous templates, --force, --quiet)
3. Commande validate (DSL valide, DSL invalide, --strict)
4. Commande test (sources, destinations, transforms)
5. Commande list
6. Commande run --dry-run
7. Commande run réelle (CSV→CSV)
8. Gestion erreurs (répertoire manquant, fichiers manquants)
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from hydra_etl import __version__
import os
import yaml
from click.testing import CliRunner

from hydra_etl.cli.hdrctl import cli, VALID_TEMPLATES, validate_job_dir, find_jobs, resolve_job_files


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def runner():
    return CliRunner()


def make_job(tmp_path: Path, name: str = "test_job", extra_files: dict | None = None) -> Path:
    """Crée un job CSV minimal valide."""
    job = tmp_path / name
    job.mkdir()

    (job / "sources.yaml").write_text(textwrap.dedent("""\
        sources:
          src_csv:
            type: csv
            extract:
              table: input.csv
              batch_size: 1000
    """))
    (job / "destinations.yaml").write_text(textwrap.dedent("""\
        destinations:
          dest_csv:
            type: csv
            load:
              table: output.csv
              mode: replace
    """))
    (job / "pipeline.yaml").write_text(textwrap.dedent("""\
        pipeline:
          from: src_csv
          to: dest_csv
    """))
    (job / "input.csv").write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf-8")
    if extra_files:
        for rel, content in extra_files.items():
            target = job / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    return job


# ═══════════════════════════════════════════════════════════════
# 1. --help et --version
# ═══════════════════════════════════════════════════════════════

class TestHelp:

    def test_help_shows_commands(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        for cmd in ["run", "init", "test", "validate", "list"]:
            assert cmd in result.output

    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        # Regle 3.1 : le test lit la source de verite, il ne recopie pas le numero.
        assert __version__ in result.output
        assert "hydra" in result.output or "hdrctl" in result.output

    def test_run_help(self, runner):
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--on-success" in result.output

    def test_init_help(self, runner):
        result = runner.invoke(cli, ["init", "--help"])
        assert result.exit_code == 0
        assert "--template" in result.output

    def test_validate_help(self, runner):
        result = runner.invoke(cli, ["validate", "--help"])
        assert result.exit_code == 0
        assert "--strict" in result.output

    def test_test_help(self, runner):
        result = runner.invoke(cli, ["test", "--help"])
        assert result.exit_code == 0
        assert "--only-sources" in result.output


# ═══════════════════════════════════════════════════════════════
# 2. Commande init
# ═══════════════════════════════════════════════════════════════

class TestInit:
    """`hdrctl init` initialise un PROJET : .hydra, workflow1, job1."""

    def test_init_empty_folder_creates_project(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["init", "my_project"])
            assert result.exit_code == 0, result.output
            root = Path("my_project")
            assert (root / ".hydra" / "project.json").is_file()
            assert (root / "workflows" / "workflow1.yaml").is_file()
            for f in ["sources.yaml", "destinations.yaml", "pipeline.yaml", "transformations.yaml"]:
                assert (root / "jobs" / "job1" / f).is_file(), f

    def test_init_dot_in_empty_folder(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("here").mkdir()
            os.chdir("here")
            result = runner.invoke(cli, ["init", "."])
            assert result.exit_code == 0, result.output
            assert Path(".hydra/project.json").is_file()
            assert Path("jobs/job1/pipeline.yaml").is_file()

    def test_init_default_path_is_current_dir(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("here").mkdir()
            os.chdir("here")
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0, result.output
            assert Path(".hydra").is_dir()

    def test_workflow1_references_job1(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "p"])
            doc = yaml.safe_load(Path("p/workflows/workflow1.yaml").read_text())
            assert doc["workflow"]["name"] == "workflow1"
            steps = doc["workflow"]["steps"]
            assert [st["name"] for st in steps] == ["job1"]
            assert (Path("p/workflows") / steps[0]["job"]).resolve() == Path("p/jobs/job1").resolve()

    def test_init_all_templates(self, runner, tmp_path):
        for tmpl in VALID_TEMPLATES:
            with runner.isolated_filesystem(temp_dir=tmp_path):
                result = runner.invoke(cli, ["init", f"proj_{tmpl}", "--template", tmpl])
                assert result.exit_code == 0, f"Template {tmpl} : {result.output}"
                assert Path(f"proj_{tmpl}/jobs/job1/pipeline.yaml").exists()

    def test_init_mysql_creates_env_example(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "p", "--template", "mysql"])
            assert "DB_HOST" in Path("p/jobs/job1/.env.example").read_text()

    def test_init_csv_template_job_runs(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "p"])
            assert Path("p/jobs/job1/data/input.csv").exists()

    def test_init_non_empty_foreign_folder_stops(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("existing").mkdir()
            (Path("existing") / "somefile.txt").write_text("x", encoding="utf-8")
            result = runner.invoke(cli, ["init", "existing"])
            assert result.exit_code != 0
            assert not Path("existing/.hydra").exists()
            assert [p.name for p in Path("existing").iterdir()] == ["somefile.txt"]

    def test_init_folder_with_job_files_only_adds_hydra(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            job = Path("myjob")
            job.mkdir()
            contents = {"sources.yaml": "sources: {}\n", "destinations.yaml": "destinations: {}\n",
                        "pipeline.yaml": "pipeline: {}\n", "transformations.yaml": "steps: []\n"}
            for n, c_ in contents.items():
                (job / n).write_text(c_, encoding="utf-8")
            result = runner.invoke(cli, ["init", "myjob"])
            assert result.exit_code == 0, result.output
            assert (job / ".hydra" / "project.json").is_file()
            assert not (job / "jobs").exists() and not (job / "workflows").exists()
            for n, c_ in contents.items():
                assert (job / n).read_text(encoding="utf-8") == c_

    def test_init_existing_project_is_left_untouched(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "p"])
            Path("p/jobs/job1/pipeline.yaml").write_text("pipeline:\n  from: x\n  to: y\n", encoding="utf-8")
            result = runner.invoke(cli, ["init", "p"])
            assert result.exit_code == 0
            assert "from: x" in Path("p/jobs/job1/pipeline.yaml").read_text()

    def test_init_quiet_mode(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["init", "p", "--quiet"])
            assert result.exit_code == 0

    # ── Structure 0.12 : environments, outputs, scripts, parameters, thread ──

    def test_init_creates_full_project_layout(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["init", "myproject"])
            assert result.exit_code == 0, result.output
            root = Path("myproject")
            assert sorted(p.name for p in root.iterdir()) == sorted([
                ".gitignore", ".hydra", "Data", "environments", "jobs", "outputs",
                "parameters.yaml", "README.md", "scripts", "workflows"])
            assert sorted(p.name for p in (root / ".hydra").iterdir()) == ["project.json", "secrets"]
            for d in ["Data", "environments", "outputs", "scripts"]:
                assert (root / d).is_dir(), d
            assert sorted(p.name for p in (root / "workflows").iterdir()) == ["thread.yaml", "workflow1.yaml"]
            assert sorted(p.name for p in (root / "jobs" / "job1").iterdir()) == sorted([
                "README.md", "data", "destinations.yaml", "pipeline.yaml",
                "sources.yaml", "transformations.yaml"])
            assert not (root / "output").exists()

    def test_init_full_path(self, runner, tmp_path):
        target = tmp_path / "deep" / "myproject"
        result = runner.invoke(cli, ["init", str(target)])
        assert result.exit_code == 0, result.output
        assert (target / "workflows" / "thread.yaml").is_file()
        assert (target / ".hydra" / "project.json").is_file()

    def test_init_thread_yaml_lists_workflow1(self, runner, tmp_path):
        from hydra_etl.workflow.thread import load_thread, missing_workflow_files
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "p"])
            th = load_thread(Path("p/workflows/thread.yaml"))
            assert len(th.thread) == 1
            assert th.thread[0].mode == "sequential"
            assert [(w.name, w.active) for w in th.thread[0].workflows] == [("workflow1", True)]
            assert missing_workflow_files(th, Path("p/workflows")) == []

    def test_init_parameters_yaml_is_empty_and_valid(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "p"])
            doc = yaml.safe_load(Path("p/parameters.yaml").read_text(encoding="utf-8"))
            assert doc == {"version": "1.0", "parameters": {}}

    def test_init_project_readme_and_marker(self, runner, tmp_path):
        import json
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "p"])
            readme = Path("p/README.md").read_text(encoding="utf-8")
            assert readme.startswith("# p\n")
            for entry in ["environments/", "outputs/", "scripts/", "thread.yaml", "parameters.yaml"]:
                assert entry in readme, entry
            marker = json.loads(Path("p/.hydra/project.json").read_text(encoding="utf-8"))
            assert marker["conventions"]["output_dir"] == "outputs"

    def test_init_job_readme_uses_hdrctl(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "p"])
            readme = Path("p/jobs/job1/README.md").read_text(encoding="utf-8")
            assert "hdrctl test" in readme
            assert "hydra test" not in readme

    @pytest.mark.parametrize("template,expected", [("csv", 3), ("mysql", 4)])
    def test_init_next_steps_are_numbered_consecutively(self, runner, tmp_path, template, expected):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["init", "p", "--template", template, "--lang", "en"])
            import re as _re
            nums = [int(n) for n in _re.findall(r"^\s+(\d+)\. ", result.output, _re.M)]
            assert nums == list(range(1, expected + 1)), result.output
            assert "hdrctl run p --dry-run" in result.output
            assert "workflow run" not in result.output

    def test_init_generated_workflow_runs(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "p"])
            wf = str(Path("p/workflows/workflow1.yaml"))
            assert runner.invoke(cli, ["workflow", "validate", wf]).exit_code == 0
            result = runner.invoke(cli, ["workflow", "run", wf])
            assert result.exit_code == 0, result.output


# ═══════════════════════════════════════════════════════════════
# 3. Commande validate
# ═══════════════════════════════════════════════════════════════

class TestValidate:

    def test_validate_valid_job(self, runner, tmp_path):
        job = make_job(tmp_path)
        result = runner.invoke(cli, ["validate", str(job)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_missing_sources(self, runner, tmp_path):
        job = make_job(tmp_path)
        (job / "sources.yaml").unlink()
        result = runner.invoke(cli, ["validate", str(job)])
        assert result.exit_code != 0

    def test_validate_invalid_sources_yaml(self, runner, tmp_path):
        job = make_job(tmp_path)
        (job / "sources.yaml").write_text("not: valid: yaml: [[\n", encoding="utf-8")
        result = runner.invoke(cli, ["validate", str(job)])
        assert result.exit_code != 0

    def test_validate_pipeline_coherence_bad_from(self, runner, tmp_path):
        job = make_job(tmp_path)
        (job / "pipeline.yaml").write_text("pipeline:\n  from: ghost_source\n  to: dest_csv\n", encoding="utf-8")
        result = runner.invoke(cli, ["validate", str(job)])
        assert result.exit_code != 0
        assert "ghost_source" in result.output

    def test_validate_pipeline_coherence_bad_to(self, runner, tmp_path):
        job = make_job(tmp_path)
        (job / "pipeline.yaml").write_text("pipeline:\n  from: src_csv\n  to: ghost_dest\n", encoding="utf-8")
        result = runner.invoke(cli, ["validate", str(job)])
        assert result.exit_code != 0
        assert "ghost_dest" in result.output

    def test_validate_with_transforms(self, runner, tmp_path):
        job = make_job(tmp_path, extra_files={
            "transformations.yaml": "steps:\n  - select:\n      columns: [id, name]\n"
        })
        result = runner.invoke(cli, ["validate", str(job)])
        assert result.exit_code == 0

    def test_validate_strict_flag(self, runner, tmp_path):
        job = make_job(tmp_path, extra_files={
            "transformations.yaml": "steps:\n  - filter:\n      expr: 'id > 0'\n"
        })
        result = runner.invoke(cli, ["validate", str(job), "--strict"])
        assert result.exit_code == 0
        assert "strict" in result.output.lower()

    def test_validate_directory_not_found(self, runner, tmp_path):
        result = runner.invoke(cli, ["validate", str(tmp_path / "ghost")])
        assert result.exit_code != 0

    def test_validate_with_explicit_yaml_files(self, runner, tmp_path):
        job = make_job(tmp_path)
        (job / "custom_sources.yaml").write_text((job / "sources.yaml").read_text())
        (job / "custom_destinations.yaml").write_text((job / "destinations.yaml").read_text())
        (job / "custom_pipeline.yaml").write_text((job / "pipeline.yaml").read_text())

        result = runner.invoke(cli, [
            "validate", str(job),
            "-s", "custom_sources.yaml",
            "-d", "custom_destinations.yaml",
            "-p", "custom_pipeline.yaml",
        ])
        assert result.exit_code == 0


# ═══════════════════════════════════════════════════════════════
# 4. Commande test
# ═══════════════════════════════════════════════════════════════

class TestTestCommand:

    def test_test_valid_job_passes(self, runner, tmp_path):
        job = make_job(tmp_path)
        result = runner.invoke(cli, ["test", str(job)])
        assert result.exit_code == 0
        assert "pass" in result.output or "valid" in result.output

    def test_test_only_sources(self, runner, tmp_path):
        job = make_job(tmp_path)
        result = runner.invoke(cli, ["test", str(job), "--only-sources"])
        assert result.exit_code == 0
        assert "sources" in result.output.lower()

    def test_test_only_destinations(self, runner, tmp_path):
        job = make_job(tmp_path)
        result = runner.invoke(cli, ["test", str(job), "--only-destinations"])
        assert result.exit_code == 0

    def test_test_only_transform(self, runner, tmp_path):
        job = make_job(tmp_path, extra_files={
            "transformations.yaml": "steps:\n  - select:\n      columns: [id]\n"
        })
        result = runner.invoke(cli, ["test", str(job), "--only-transform"])
        assert result.exit_code == 0

    def test_test_invalid_destinations_fails(self, runner, tmp_path):
        job = make_job(tmp_path)
        # Mode upsert sans key → invalid
        (job / "destinations.yaml").write_text(
            "destinations:\n  dest_csv:\n    type: mysql\n"
            "    connection: {}\n    load:\n      table: t\n      mode: upsert\n"
        , encoding="utf-8")
        result = runner.invoke(cli, ["test", str(job), "--only-destinations"])
        assert result.exit_code != 0

    def test_test_with_env_file(self, runner, tmp_path):
        job = make_job(tmp_path)
        (job / ".env").write_text("DB_HOST=localhost\nDB_PASS=secret\n", encoding="utf-8")
        result = runner.invoke(cli, ["test", str(job)])
        assert result.exit_code == 0
        assert "DB_HOST" in result.output

    def test_test_directory_not_found(self, runner):
        result = runner.invoke(cli, ["test", "/nonexistent/path"])
        assert result.exit_code != 0

    def test_test_with_explicit_yaml_files(self, runner, tmp_path):
        job = make_job(tmp_path)
        (job / "custom_sources.yaml").write_text((job / "sources.yaml").read_text())
        (job / "custom_destinations.yaml").write_text((job / "destinations.yaml").read_text())
        (job / "custom_pipeline.yaml").write_text((job / "pipeline.yaml").read_text())

        result = runner.invoke(cli, [
            "test", str(job),
            "-s", "custom_sources.yaml",
            "-d", "custom_destinations.yaml",
            "-p", "custom_pipeline.yaml",
        ])
        assert result.exit_code == 0


# ═══════════════════════════════════════════════════════════════
# 5. Commande list
# ═══════════════════════════════════════════════════════════════

class TestList:

    def test_list_finds_valid_jobs(self, runner, tmp_path):
        make_job(tmp_path, "job_a")
        make_job(tmp_path, "job_b")
        result = runner.invoke(cli, ["list", str(tmp_path)])
        assert result.exit_code == 0
        assert "job_a" in result.output
        assert "job_b" in result.output

    def test_list_empty_directory(self, runner, tmp_path):
        result = runner.invoke(cli, ["list", str(tmp_path)])
        assert result.exit_code == 0
        assert "No jobs" in result.output

    def test_list_shows_ok_status(self, runner, tmp_path):
        make_job(tmp_path, "good_job")
        result = runner.invoke(cli, ["list", str(tmp_path)])
        assert "good_job" in result.output

    def test_list_directory_not_found(self, runner):
        result = runner.invoke(cli, ["list", "/no/such/dir"])
        assert result.exit_code != 0

    def test_list_count_summary(self, runner, tmp_path):
        make_job(tmp_path, "j1")
        make_job(tmp_path, "j2")
        result = runner.invoke(cli, ["list", str(tmp_path)])
        assert "2 job(s)" in result.output
        assert "OK OK" not in result.output


# ═══════════════════════════════════════════════════════════════
# 6. Commande run --dry-run
# ═══════════════════════════════════════════════════════════════

class TestRunDryRun:

    def test_dry_run_valid_job_exits_0(self, runner, tmp_path):
        job = make_job(tmp_path)
        result = runner.invoke(cli, ["run", str(job), "--dry-run"])
        assert result.exit_code == 0
        assert "dry" in result.output.lower() or "DRY" in result.output

    def test_dry_run_invalid_yaml_exits_nonzero(self, runner, tmp_path):
        job = make_job(tmp_path)
        (job / "sources.yaml").write_text("not_valid: [[\n", encoding="utf-8")
        result = runner.invoke(cli, ["run", str(job), "--dry-run"])
        # Dry-run doit détecter l'erreur
        assert "invalide" in result.output or result.exit_code != 0

    def test_dry_run_bad_pipeline_from(self, runner, tmp_path):
        job = make_job(tmp_path)
        (job / "pipeline.yaml").write_text("pipeline:\n  from: ghost\n  to: dest_csv\n", encoding="utf-8")
        result = runner.invoke(cli, ["run", str(job), "--dry-run"])
        assert "ghost" in result.output or result.exit_code != 0

    def test_dry_run_no_write(self, runner, tmp_path):
        """Le dry-run ne doit pas créer de fichier output."""
        job = make_job(tmp_path)
        runner.invoke(cli, ["run", str(job), "--dry-run"])
        assert not (job / "output.csv").exists()

    def test_dry_run_with_explicit_yaml_files(self, runner, tmp_path):
        job = make_job(tmp_path)
        (job / "custom_sources.yaml").write_text((job / "sources.yaml").read_text())
        (job / "custom_destinations.yaml").write_text((job / "destinations.yaml").read_text())
        (job / "custom_pipeline.yaml").write_text((job / "pipeline.yaml").read_text())

        result = runner.invoke(cli, [
            "run", str(job), "--dry-run",
            "-s", "custom_sources.yaml",
            "-d", "custom_destinations.yaml",
            "-p", "custom_pipeline.yaml",
        ])
        assert result.exit_code == 0


# ═══════════════════════════════════════════════════════════════
# 7. Commande run réelle (CSV→CSV)
# ═══════════════════════════════════════════════════════════════

class TestRunReal:

    def test_run_csv_to_csv_success(self, runner, tmp_path):
        job = make_job(tmp_path)
        result = runner.invoke(cli, ["run", str(job)])
        assert result.exit_code == 0
        assert (job / "output.csv").exists()

    def test_run_produces_correct_output(self, runner, tmp_path):
        job = make_job(tmp_path)
        runner.invoke(cli, ["run", str(job)])
        import csv
        rows = list(csv.DictReader((job / "output.csv").read_text().splitlines()))
        assert len(rows) == 2
        assert rows[0]["name"] == "Alice"

    def test_run_with_transforms(self, runner, tmp_path):
        job = make_job(tmp_path, extra_files={
            "transformations.yaml": "steps:\n  - select:\n      columns: [id]\n"
        })
        result = runner.invoke(cli, ["run", str(job)])
        assert result.exit_code == 0
        import csv
        rows = list(csv.DictReader((job / "output.csv").read_text().splitlines()))
        assert list(rows[0].keys()) == ["id"]

    def test_run_verbosity_v(self, runner, tmp_path):
        job = make_job(tmp_path)
        result = runner.invoke(cli, ["run", str(job), "-v"])
        assert result.exit_code == 0

    def test_run_verbosity_vv(self, runner, tmp_path):
        job = make_job(tmp_path)
        result = runner.invoke(cli, ["run", str(job), "-vv"])
        assert result.exit_code == 0

    def test_run_missing_dir_exits_nonzero(self, runner):
        result = runner.invoke(cli, ["run", "/nonexistent/path/job"])
        assert result.exit_code != 0
