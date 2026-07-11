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
import yaml
from click.testing import CliRunner

from cli.hdrctl import cli, VALID_TEMPLATES, validate_job_dir, find_jobs, resolve_job_files


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
        assert "1.2.0" in result.output
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
        assert "--force" in result.output

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

    def test_init_basic_creates_files(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["init", "my_job"])
            assert result.exit_code == 0
            for f in ["sources.yaml", "destinations.yaml", "pipeline.yaml", "README.md"]:
                assert Path("my_job" / Path(f)).exists(), f"Manque {f}"

    def test_init_all_templates(self, runner, tmp_path):
        for tmpl in VALID_TEMPLATES:
            with runner.isolated_filesystem(temp_dir=tmp_path):
                result = runner.invoke(cli, ["init", f"job_{tmpl}", "--template", tmpl])
                assert result.exit_code == 0, f"Template {tmpl} : {result.output}"
                assert Path(f"job_{tmpl}/pipeline.yaml").exists()

    def test_init_creates_pipeline_yaml_content(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "j", "--template", "basic"])
            data = yaml.safe_load(Path("j/pipeline.yaml").read_text())
            assert "pipeline" in data
            assert "from" in data["pipeline"]
            assert "to" in data["pipeline"]

    def test_init_mysql_creates_env_example(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "myjob", "--template", "mysql"])
            assert Path("myjob/.env.example").exists()
            content = Path("myjob/.env.example").read_text()
            assert "DB_HOST" in content

    def test_init_csv_creates_sample_data(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "j", "--template", "csv"])
            assert Path("j/data/input.csv").exists()

    def test_init_fails_if_dir_exists_not_empty(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path("existing").mkdir()
            (Path("existing") / "somefile.txt").write_text("x", encoding="utf-8")
            result = runner.invoke(cli, ["init", "existing"])
            assert result.exit_code != 0

    def test_init_force_overwrites(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "j", "--template", "basic"])
            # Modifier un fichier
            Path("j/pipeline.yaml").write_text("pipeline:\n  from: old\n  to: old\n", encoding="utf-8")
            runner.invoke(cli, ["init", "j", "--template", "basic", "--force"])
            data = yaml.safe_load(Path("j/pipeline.yaml").read_text())
            assert data["pipeline"]["from"] != "old"

    def test_init_quiet_mode(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["init", "j", "--quiet"])
            assert result.exit_code == 0

    def test_init_readme_created(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["init", "myjob"])
            readme = Path("myjob/README.md")
            assert readme.exists()
            assert "myjob" in readme.read_text()


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
        assert "2" in result.output


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
