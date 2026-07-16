#!/usr/bin/env python3
"""
hdrctl — Hydra ETL Control CLI
Version 1.2.0

Point d'entrée principal de la CLI Hydra ETL.

Commandes :
    hdrctl run      [PATH] [options]    Exécute un pipeline ETL
    hdrctl init     <NOM>  [options]    Crée un nouveau job
    hdrctl test     [PATH] [options]    Valide sources, destinations, DSL
    hdrctl validate [PATH] [options]    Validation stricte du DSL YAML
    hdrctl list     [PATH]              Liste les jobs du répertoire
    hdrctl --version                    Version
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Optional

# Supprimer les warnings Pydantic internes inoffensifs :
# 1. Champ 'schema' dans SourceDefinition (shadowing BaseModel.schema supprime en v2)
# 2. PydanticSerializationUnexpectedValue sur les params de transformation (dict attendu)
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", message="Field name .* shadows an attribute", category=UserWarning)

import click

from cli.i18n import t, set_lang

# ─────────────────────────────────────────────────────────────────────────────
# Couleurs ANSI
# ─────────────────────────────────────────────────────────────────────────────

class C:
    GR  = "\033[92m"    # Vert
    RD  = "\033[91m"    # Rouge
    YL  = "\033[93m"    # Jaune
    CY  = "\033[96m"    # Cyan
    DM  = "\033[90m"    # Gris
    WH  = "\033[97m"    # Blanc vif
    BD  = "\033[1m"     # Gras
    RS  = "\033[0m"     # Reset

def _ansi_enabled() -> bool:
    """Détecte si le terminal supporte ANSI."""
    if sys.platform == "win32":
        os.system("")   # Active ANSI sur Windows 10+
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

_USE_COLOR = _ansi_enabled()

def c(color: str, text: str) -> str:
    return f"{color}{text}{C.RS}" if _USE_COLOR else text

# ─────────────────────────────────────────────────────────────────────────────
# Logo & Banner
# ─────────────────────────────────────────────────────────────────────────────

VERSION = "1.2.0"

def print_banner() -> None:
    """Affiche le banner HYDRA ETL en ASCII art (doom font)."""
    lines = [
        r" _   ___   _____________  ___    _____ _____ _     ",
        r"| | | \ \ / /  _  \ ___ \/ _ \  |  ___|_   _| |    ",
        r"| |_| |\ V /| | | | |_/ / /_\ \ | |__   | | | |    ",
        r"|  _  | \ / | | | |    /|  _  | |  __|  | | | |    ",
        r"| | | | | | | |/ /| |\ \| | | | | |___  | | | |____",
        r"\_| |_/ \_/ |___/ \_| \_\_| |_/ \____/  \_/ \_____/",
    ]
    click.echo()
    for line in lines:
        click.echo("  " + c(C.CY + C.BD, line))
    click.echo(f"\n  {c(C.DM, t('banner.subtitle'))}  {c(C.WH, 'v' + VERSION)}  {c(C.DM, '─' * 28)}")
    click.echo()

def ok(text: str) -> None:
    click.echo(f"  {c(C.GR, 'ok')}  {text}")

def err_line(text: str) -> None:
    click.echo(f"  {c(C.RD, 'err')} {text}", err=True)

def info(text: str) -> None:
    click.echo(f"  {c(C.DM, text)}")

def section(title: str) -> None:
    click.echo(f"\n{c(C.WH + C.BD, '  ' + title)}")

def step_ok(n: int, total: int, name: str, extra: str = "", duration: float = 0.0) -> None:
    pad   = name.ljust(28)
    dur   = f"{c(C.DM, f'{duration:.1f}s')}" if duration else ""
    xtra  = f"  {c(C.DM, f'({extra})')}" if extra else ""
    click.echo(f"  {c(C.GR, f'[{n}/{total}]')}  {c(C.WH, pad)}  {c(C.GR, 'ok')}  {dur}{xtra}")

def step_fail(n: int, total: int, name: str, reason: str = "") -> None:
    pad = name.ljust(28)
    click.echo(f"  {c(C.RD, f'[{n}/{total}]')}  {c(C.WH, pad)}  {c(C.RD, t('step.error'))}",
               err=True)
    if reason:
        click.echo(f"           {c(C.YL, reason)}", err=True)

def success_box(msg: str) -> None:
    click.echo(f"\n  {c(C.GR + C.BD, '✅ ' + msg)}")

def error_box(msg: str) -> None:
    click.echo(f"\n  {c(C.RD + C.BD, '❌ ' + msg)}", err=True)

# ─────────────────────────────────────────────────────────────────────────────
# Validation d'un job directory
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_FILES = ["sources.yaml", "destinations.yaml", "pipeline.yaml"]
OPTIONAL_FILES = ["transformations.yaml", ".env"]

def validate_job_dir(path: Path) -> list[str]:
    """Retourne la liste des fichiers requis manquants."""
    return [f for f in REQUIRED_FILES if not (path / f).exists()]


def _resolve_cli_path(base: Path, explicit: Optional[str], default_name: str) -> Path:
    if not explicit:
        return (base / default_name).resolve()
    path = Path(explicit).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def resolve_job_files(
    base: Path,
    sources: Optional[str] = None,
    destinations: Optional[str] = None,
    pipeline: Optional[str] = None,
    transformations: Optional[str] = None,
) -> dict:
    return {
        "sources": _resolve_cli_path(base, sources, "sources.yaml"),
        "destinations": _resolve_cli_path(base, destinations, "destinations.yaml"),
        "pipeline": _resolve_cli_path(base, pipeline, "pipeline.yaml"),
        "transformations": _resolve_cli_path(base, transformations, "transformations.yaml"),
    }


def validate_job_files(files: dict[str, Path]) -> list[Path]:
    missing: list[Path] = []
    for key in ("sources", "destinations", "pipeline"):
        if not files[key].exists():
            missing.append(files[key])
    return missing

def find_jobs(root: Path) -> list[Path]:
    """Retourne tous les sous-dossiers qui ressemblent à un job Hydra."""
    jobs = []
    try:
        children = sorted(root.iterdir())
    except PermissionError:
        return jobs
    for child in children:
        try:
            if child.is_dir() and not child.name.startswith("."):
                missing = validate_job_dir(child)
                if not missing:
                    jobs.append(child)
        except PermissionError:
            continue
    return jobs

# ─────────────────────────────────────────────────────────────────────────────
# Templates init
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES: dict[str, dict[str, str]] = {

    "basic": {
        "sources.yaml": """\
sources:
  src_input:
    type: csv
    extract:
      table: input.csv
      batch_size: 10000
""",
        "destinations.yaml": """\
destinations:
  dest_output:
    type: csv
    load:
      table: output.csv
      mode: replace
""",
        "pipeline.yaml": """\
pipeline:
  from: src_input
  to: dest_output
""",
        "transformations.yaml": """\
steps:
  - select:
      columns: [id, name]
  # - filter:
  #     expr: "id > 0"
  # - cast:
  #     mapping:
  #       id: int
""",
    },

    "mysql": {
        "sources.yaml": """\
sources:
  src_mysql:
    type: mysql
    connection:
      host: ${ENV:DB_HOST}
      port: 3306
      database: ${ENV:DB_NAME}
      user: ${ENV:DB_USER}
      password: ${ENV:DB_PASS}
    extract:
      table: source_table
      batch_size: 10000
""",
        "destinations.yaml": """\
destinations:
  dest_mysql:
    type: mysql
    connection:
      host: ${ENV:DB_HOST}
      port: 3306
      database: ${ENV:DB_NAME}
      user: ${ENV:DB_USER}
      password: ${ENV:DB_PASS}
    load:
      table: dest_table
      mode: upsert
      key: [id]
      batch_size: 5000
""",
        "pipeline.yaml": """\
pipeline:
  from: src_mysql
  to: dest_mysql
""",
        "transformations.yaml": """\
steps:
  - select:
      columns: [id, name, created_at]
  - cast:
      mapping:
        id: int
""",
        ".env.example": """\
DB_HOST=localhost
DB_NAME=mydb
DB_USER=root
DB_PASS=secret
""",
    },

    "postgres": {
        "sources.yaml": """\
sources:
  src_pg:
    type: postgresql
    connection:
      host: ${ENV:PG_HOST}
      port: 5432
      database: ${ENV:PG_DB}
      user: ${ENV:PG_USER}
      password: ${ENV:PG_PASS}
    extract:
      table: source_table
      batch_size: 10000
""",
        "destinations.yaml": """\
destinations:
  dest_pg:
    type: postgresql
    connection:
      host: ${ENV:PG_HOST}
      port: 5432
      database: ${ENV:PG_DB}
      user: ${ENV:PG_USER}
      password: ${ENV:PG_PASS}
    load:
      table: dest_table
      mode: upsert
      key: [id]
""",
        "pipeline.yaml": """\
pipeline:
  from: src_pg
  to: dest_pg
""",
        "transformations.yaml": """\
steps:
  - select:
      columns: [id, name]
""",
        ".env.example": """\
PG_HOST=localhost
PG_DB=mydb
PG_USER=postgres
PG_PASS=secret
""",
    },

    "csv": {
        "sources.yaml": """\
sources:
  src_csv:
    type: csv
    extract:
      table: data/input.csv
      batch_size: 50000
""",
        "destinations.yaml": """\
destinations:
  dest_csv:
    type: csv
    load:
      table: data/output.csv
      mode: replace
""",
        "pipeline.yaml": """\
pipeline:
  from: src_csv
  to: dest_csv
""",
        "transformations.yaml": """\
steps:
  - select:
      columns: [id, name, value]
  - filter:
      expr: "value > 0"
""",
        "data/input.csv": "id,name,value\n1,Alice,100\n2,Bob,200\n3,Charlie,-5\n",
    },

    "api": {
        "sources.yaml": """\
sources:
  src_api:
    type: web_api
    connection:
      base_url: ${ENV:API_BASE_URL}
      auth:
        type: bearer
        token: ${ENV:API_TOKEN}
      pagination:
        strategy: cursor
        cursor_field: next_cursor
        page_size: 100
    extract:
      table: /v1/records
      batch_size: 100
""",
        "destinations.yaml": """\
destinations:
  dest_csv:
    type: csv
    load:
      table: output/api_data.csv
      mode: replace
""",
        "pipeline.yaml": """\
pipeline:
  from: src_api
  to: dest_csv
""",
        "transformations.yaml": """\
steps:
  - select:
      columns: [id, name, created_at]
""",
        ".env.example": """\
API_BASE_URL=https://api.example.com
API_TOKEN=your_token_here
""",
    },

    "mongodb": {
        "sources.yaml": """\
sources:
  src_mongo:
    type: mongodb
    connection:
      host: ${ENV:MONGO_HOST}
      port: 27017
      database: ${ENV:MONGO_DB}
      collection: ${ENV:MONGO_COLLECTION}
    extract:
      table: ${ENV:MONGO_COLLECTION}
      batch_size: 1000
""",
        "destinations.yaml": """\
destinations:
  dest_csv:
    type: csv
    load:
      table: output/mongo_export.csv
      mode: replace
""",
        "pipeline.yaml": """\
pipeline:
  from: src_mongo
  to: dest_csv
""",
        "transformations.yaml": """\
steps:
  - select:
      columns: [id, name, status]
""",
        ".env.example": """\
MONGO_HOST=localhost
MONGO_DB=mydb
MONGO_COLLECTION=mycollection
""",
    },
}


def create_job_structure(job_dir: Path, template: str, force: bool) -> list[str]:
    """
    Crée la structure d'un job depuis un template.
    Retourne la liste des fichiers créés.
    """
    tmpl_files = TEMPLATES.get(template, TEMPLATES["basic"])
    created = []

    for rel_path, content in tmpl_files.items():
        target = job_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and not force:
            continue

        target.write_text(content, encoding="utf-8")
        created.append(rel_path)

    # Toujours créer README.md
    readme = job_dir / "README.md"
    if not readme.exists() or force:
        readme.write_text(
            f"# Job : {job_dir.name}\n\n"
            f"Template : `{template}`\n\n"
            "## Structure\n\n"
            "- `sources.yaml` — sources de données\n"
            "- `destinations.yaml` — destinations\n"
            "- `pipeline.yaml` — orchestration\n"
            "- `transformations.yaml` — transformations DSL (optionnel)\n"
            "- `.env` — variables d'environnement (à créer depuis .env.example)\n\n"
            "## Utilisation\n\n"
            "```bash\n"
            f"hydra test {job_dir.name}   # valider la config\n"
            f"hdrctl run  {job_dir.name}   # exécuter\n"
            "```\n",
            encoding="utf-8",
        )
        created.append("README.md")

    return created


# ─────────────────────────────────────────────────────────────────────────────
# Hooks
# ─────────────────────────────────────────────────────────────────────────────

def fire_hook(name: str, cmd: Optional[str], verbosity: int) -> None:
    if not cmd:
        return
    click.echo(f"\n  {c(C.DM, t('hook.running', name=name, cmd=cmd))}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            click.echo(f"  {c(C.GR, '✓')} {t('hook.executed', name=name)}")
        else:
            click.echo(f"  {c(C.YL, '⚠')} {t('hook.nonzero', name=name, code=result.returncode)}", err=True)
        if verbosity >= 2 and result.stdout.strip():
            click.echo(f"  {c(C.DM, result.stdout.strip())}")
    except subprocess.TimeoutExpired:
        click.echo(f"  {c(C.RD, '✗')} {t('hook.timeout', name=name)}", err=True)
    except Exception as e:
        click.echo(f"  {c(C.RD, '✗')} {t('hook.error', name=name, error=e)}", err=True)


# ─────────────────────────────────────────────────────────────────────────────
# Validation DSL (pour test + validate)
# ─────────────────────────────────────────────────────────────────────────────

def _load_yaml(path: Path) -> tuple[dict, str | None]:
    """Charge un YAML. Retourne (data, error_msg)."""
    import yaml
    try:
        raw = _read_yaml(path)
        data = yaml.safe_load(raw) or {}
        return data, None
    except Exception as e:
        return {}, str(e)


def _read_yaml(path: Path) -> str:
    """Lit un fichier YAML en gérant les encodages Windows (UTF-8, UTF-8-BOM, UTF-16)."""
    for enc in ("utf-8-sig", "utf-16", "utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, ValueError):
            continue
    raise ValueError(t("yaml.encoding_error", name=path.name))


def _validate_sources_yaml(path: Path) -> list[str]:
    """Retourne la liste des erreurs de validation sources.yaml."""
    errors = []
    data, err = _load_yaml(path)
    if err:
        return [t("yaml.invalid", error=err)]
    try:
        import sys as _sys
        _sys.path.insert(0, str(path.parent.parent.parent))
        from internal.parser.source import SourceParser
        SourceParser().parse(data)
    except Exception as e:
        errors.append(str(e))
    return errors


def _validate_destinations_yaml(path: Path) -> list[str]:
    errors = []
    data, err = _load_yaml(path)
    if err:
        return [t("yaml.invalid", error=err)]
    try:
        from internal.parser.destination import DestinationParser
        DestinationParser().parse(data)
    except Exception as e:
        errors.append(str(e))
    return errors


def _validate_transform_yaml(path: Path) -> list[str]:
    if not path.exists():
        return []
    errors = []
    data, err = _load_yaml(path)
    if err:
        return [t("yaml.invalid", error=err)]
    try:
        from internal.parser.transform import TransformParser
        TransformParser().parse(data)
    except Exception as e:
        errors.append(str(e))
    return errors


def _test_connection(connector_type: str, connection: dict, name: str) -> tuple[bool, str]:
    """Tente une connexion réelle. Retourne (success, message)."""
    try:
        from internal.connector.registry import build_connector
        cfg = {"type": connector_type, "connection": connection,
               "extract": {"table": "__test__", "batch_size": 1}}
        conn = build_connector(name=name, config=cfg)
        conn.test_connection()
        return True, "connexion OK"
    except Exception as e:
        short = str(e)[:80]
        return False, short


# ─────────────────────────────────────────────────────────────────────────────
# Callback --lang (commun à tous les sous-commandes)
# ─────────────────────────────────────────────────────────────────────────────

def _lang_callback(ctx: click.Context, param: click.Parameter, value: Optional[str]) -> None:
    if value:
        set_lang(value)


def _lang_option(f):
    """Décorateur réutilisable : ajoute --lang à une commande Click."""
    return click.option(
        "--lang",
        default=None,
        metavar="LANG",
        help=t("help.lang"),
        is_eager=True,
        expose_value=False,
        callback=_lang_callback,
    )(f)


# ─────────────────────────────────────────────────────────────────────────────
# CLI principal — Click
# ─────────────────────────────────────────────────────────────────────────────

CONTEXT_SETTINGS = dict(help_option_names=["--help", "-h"])


@click.group(context_settings=CONTEXT_SETTINGS, invoke_without_command=True,
             help=t("cli.help"))
@click.version_option(version=VERSION, prog_name="hydra",
                      message=f"%(prog)s %(version)s  |  Hydra ETL Framework  |  Python {sys.version.split()[0]}")
@_lang_option
@click.pass_context
def cli(ctx: click.Context) -> None:
    if ctx.invoked_subcommand is None:
        print_banner()
        click.echo(ctx.get_help())


# ─────────────────────────────────────────────────────────────────────────────
# Commande : run
# ─────────────────────────────────────────────────────────────────────────────

@cli.command("run", help=t("help.run.docstring"))
@_lang_option
@click.argument("path", default=".", type=click.Path())
@click.option("-v", "verbosity", flag_value=1, default=0, help=t("help.run.verbose1"))
@click.option("-vv", "verbosity", flag_value=2, help=t("help.run.verbose2"))
@click.option("-vvv", "verbosity", flag_value=3, help=t("help.run.verbose3"))
@click.option("--dry-run", is_flag=True, default=False, help=t("help.run.dry_run"))
@click.option("-s", "--sources", "sources_file", default=None, metavar="FILE",
              help=t("help.run.sources"))
@click.option("-d", "--destinations", "destinations_file", default=None, metavar="FILE",
              help=t("help.run.destinations"))
@click.option("-p", "--pipeline", "pipeline_file", default=None, metavar="FILE",
              help=t("help.run.pipeline"))
@click.option("-t", "--transformations", "transformations_file", default=None, metavar="FILE",
              help=t("help.run.transformations"))
@click.option("--on-success", "on_success", default=None, metavar="CMD",
              help=t("help.run.on_success"))
@click.option("--on-failure", "on_failure", default=None, metavar="CMD",
              help=t("help.run.on_failure"))
@click.option("--on-finish", "on_finish", default=None, metavar="CMD",
              help=t("help.run.on_finish"))
@click.option("--env", "env_name", default=None, metavar="NAME",
              help=t("help.run.env"))
@click.option("-P", "--param", "param_overrides", multiple=True, metavar="KEY=VALUE",
              help=t("help.run.param"))
def cmd_run(path: str, verbosity: int, dry_run: bool,
            sources_file: Optional[str], destinations_file: Optional[str],
            pipeline_file: Optional[str], transformations_file: Optional[str],
            on_success: Optional[str], on_failure: Optional[str],
            on_finish: Optional[str],
            env_name: Optional[str] = None, param_overrides: tuple = ()) -> None:
    """Exécute un pipeline ETL."""
    print_banner()
    job_dir = Path(path).resolve()

    # Validation existence
    if not job_dir.exists() or not job_dir.is_dir():
        error_box(t("dir.not_found", path=path))
        sys.exit(1)

    job_files = resolve_job_files(
        job_dir,
        sources=sources_file,
        destinations=destinations_file,
        pipeline=pipeline_file,
        transformations=transformations_file,
    )

    missing = validate_job_files(job_files)
    if missing:
        error_box(t("run.missing_files"))
        for f in missing:
            err_line(f"  — {f}")
        sys.exit(1)

    job_name = job_dir.name

    # Parametres CLI (--param KEY=VALUE, repetable)
    param_dict: dict = {}
    for _item in param_overrides:
        if "=" not in _item:
            error_box(t("run.param_invalid", item=_item))
            sys.exit(1)
        _k, _v = _item.split("=", 1)
        param_dict[_k.strip()] = _v.strip()

    # ── Mode dry-run ─────────────────────────────────────────────
    if dry_run:
        click.echo(f"\n  {c(C.YL + C.BD, t('run.dry_run_mode'))} — {c(C.DM, t('run.dry_run_no_write'))}")
        section(t("run.dry_run_section", job_name=c(C.CY, job_name)))
        click.echo()
        _run_validate_only(job_dir, verbosity, job_files)
        success_box(t("run.dry_run_done"))
        info(t("run.hint", cmd=c(C.WH, f"hydra run {path}")))
        sys.exit(0)

    # ── Exécution réelle ──────────────────────────────────────────
    click.echo(f"\n  {c(C.WH, '▶')}  Pipeline  {c(C.CY + C.BD, job_name)}  {c(C.DM, f'— {path}')}")
    click.echo()

    t_start = time.monotonic()
    status = "FAILURE"

    try:
        from internal.runner.executor import JobExecutor
        executor = JobExecutor(
            job_dir=job_dir,
            sources_file=job_files["sources"],
            destinations_file=job_files["destinations"],
            pipeline_file=job_files["pipeline"],
            transformations_file=job_files["transformations"] if job_files["transformations"].exists() else None,
            env=env_name,
            params=param_dict,
        )
        result = executor.run()

        duration = time.monotonic() - t_start

        if result.success:
            status = "SUCCESS"
            click.echo()
            success_box(t("run.success", duration=f"{duration:.1f}"))
            click.echo(f"  {c(C.DM, t('run.rows_read', rows=f'{result.rows_in:,}'))}")
            click.echo(f"  {c(C.DM, t('run.rows_written', rows=f'{result.rows_out:,}'))}")

            # Verbosité 1 — résumé config
            if verbosity >= 1:
                section(t("run.section.detail"))
                _print_job_config(job_dir, job_files)

            # Verbosité 2 — variables résolues
            if verbosity >= 2:
                section(t("run.section.env"))
                _print_env_vars(job_dir)
                section(t("run.section.metrics"))
                click.echo(f"  {c(C.DM, f'rows_in={result.rows_in:,}  rows_out={result.rows_out:,}  duration={result.duration:.3f}s')}")

            # Verbosité 3 — log complet
            if verbosity >= 3:
                section(t("run.section.log"))
                click.echo(f"  {c(C.DM, f'JobExecutor completed — job_id={job_name}')}")
                click.echo(f"  {c(C.DM, f'duration={result.duration:.3f}s  rows_in={result.rows_in}  rows_out={result.rows_out}')}")

        else:
            status = "FAILURE"
            click.echo()
            error_box(t("run.failure", duration=f"{duration:.1f}"))
            click.echo(f"\n  {c(C.WH, t('run.cause'))}")
            click.echo(f"  {c(C.YL, result.error or t('run.unknown_error'))}")
            click.echo(f"\n  {c(C.DM, t('run.hint_verbose'))}")

    except KeyboardInterrupt:
        status = "FAILURE"
        click.echo(f"\n\n  {c(C.YL, '⚠  ' + t('run.interrupted'))}")
        sys.exit(130)
    except Exception as exc:
        status = "FAILURE"
        error_box(t("run.critical_error", type=type(exc).__name__))
        click.echo(f"  {c(C.YL, str(exc))}", err=True)
    finally:
        fire_hook("on-success", on_success if status == "SUCCESS" else None, verbosity)
        fire_hook("on-failure", on_failure if status == "FAILURE" else None, verbosity)
        fire_hook("on-finish", on_finish, verbosity)

    sys.exit(0 if status == "SUCCESS" else 1)


def _run_validate_only(job_dir: Path, verbosity: int, job_files: dict[str, Path]) -> None:
    """Validation sans exécution (dry-run)."""
    display_names = {
        "sources": "sources.yaml",
        "destinations": "destinations.yaml",
        "pipeline": "pipeline.yaml",
        "transformations": "transformations.yaml",
    }
    for key in ("sources", "destinations", "pipeline", "transformations"):
        fname = display_names[key]
        fpath = job_files[key]
        if not fpath.exists():
            if key == "transformations":
                info(f"{fname:<28} — {t('validate.optional_absent')}")
            else:
                err_line(f"{fname:<28} — {t('validate.missing')}")
            continue
        ok(f"{c(C.WH, fname):<36} — {t('validate.present')}")

    click.echo()
    # Validation parsers
    errs_src = _validate_sources_yaml(job_files["sources"])
    errs_dst = _validate_destinations_yaml(job_files["destinations"])
    errs_trf = _validate_transform_yaml(job_files["transformations"])

    if not errs_src:
        ok(f"{c(C.WH, 'sources.yaml'):<36} — {t('validate.dsl_valid')}")
    else:
        for e in errs_src:
            err_line(f"sources.yaml : {e}")

    if not errs_dst:
        ok(f"{c(C.WH, 'destinations.yaml'):<36} — {t('validate.dsl_valid')}")
    else:
        for e in errs_dst:
            err_line(f"destinations.yaml : {e}")

    if not errs_trf:
        if job_files["transformations"].exists():
            ok(f"{c(C.WH, 'transformations.yaml'):<36} — {t('validate.dsl_valid')}")
    else:
        for e in errs_trf:
            err_line(f"transformations.yaml : {e}")

    # Cohérence pipeline.from / pipeline.to
    try:
        import yaml
        pipeline = yaml.safe_load(_read_yaml(job_files["pipeline"]))
        sources  = yaml.safe_load(_read_yaml(job_files["sources"]))
        dests    = yaml.safe_load(_read_yaml(job_files["destinations"]))
        pipe     = (pipeline or {}).get("pipeline", {})
        from_id  = pipe.get("from")
        to_id    = pipe.get("to")
        if from_id and from_id not in (sources or {}).get("sources", {}):
            err_line(t("validate.pipeline_from_missing", from_id=from_id))
        else:
            ok(f"{c(C.WH, 'pipeline.from'):<36} — {t('validate.resolved', id=from_id)}")
        if to_id and to_id not in (dests or {}).get("destinations", {}):
            err_line(t("validate.pipeline_to_missing", to_id=to_id))
        else:
            ok(f"{c(C.WH, 'pipeline.to'):<36} — {t('validate.resolved', id=to_id)}")
    except Exception as e:
        err_line(t("validate.coherence_error", error=e))


def _print_job_config(job_dir: Path, job_files: dict[str, Path]) -> None:
    """Affiche un résumé de la config du job (verbosité 1)."""
    import yaml
    try:
        pipeline = yaml.safe_load(_read_yaml(job_files["pipeline"]))
        pipe     = pipeline.get("pipeline", {})
        _from = pipe.get("from", "?")
        _to   = pipe.get("to", "?")
        click.echo(f"  {c(C.DM, t('run.pipeline_flow', from_=_from, to_=_to))}")
    except Exception:
        pass
    if job_files["transformations"].exists():
        try:
            trf  = yaml.safe_load(_read_yaml(job_files["transformations"]))
            n    = len((trf or {}).get("steps", []))
            click.echo(f"  {c(C.DM, t('run.transforms_applied', n=n))}")
        except Exception:
            pass


def _print_env_vars(job_dir: Path) -> None:
    """Affiche les variables .env résolues (sans valeurs sensibles)."""
    env_files = []
    if (job_dir.parent / ".env").exists():
        env_files.append(job_dir.parent / ".env")
    if (job_dir / ".env").exists():
        env_files.append(job_dir / ".env")

    if not env_files:
        info(t("env.none_found"))
        return

    for ef in env_files:
        try:
            lines = ef.read_text(encoding="utf-8").splitlines()
            keys  = [l.split("=")[0].strip() for l in lines
                     if l.strip() and not l.startswith("#") and "=" in l]
            if keys:
                keys_str = " ".join(keys)
                click.echo(f"  {c(C.DM, f'{ef.name} : {keys_str}')}")
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Commande : init
# ─────────────────────────────────────────────────────────────────────────────

VALID_TEMPLATES = sorted(TEMPLATES.keys())


@cli.command("init", help=t("help.init.docstring"))
@_lang_option
@click.argument("name")
@click.option("--template", "-t", default="basic",
              type=click.Choice(VALID_TEMPLATES, case_sensitive=False),
              show_default=True, help=t("help.init.template"))
@click.option("--force", is_flag=True, default=False, help=t("help.init.force"))
@click.option("--quiet", "-q", is_flag=True, default=False, help=t("help.init.quiet"))
def cmd_init(name: str, template: str, force: bool, quiet: bool) -> None:
    """Crée un nouveau job ETL depuis un template."""
    print_banner()
    job_dir = Path(name)

    if job_dir.exists() and not force:
        existing_files = list(job_dir.iterdir()) if job_dir.is_dir() else []
        if existing_files:
            error_box(t("init.dir_exists", name=name))
            info(t("init.use_force", flag=c(C.WH, "--force")))
            sys.exit(1)

    if not quiet:
        click.echo(f"\n  {c(C.CY, t('init.creating'))}  {c(C.WH + C.BD, name)}"
                   f"  {c(C.DM, f'[template: {template}]')}")
        click.echo()

    job_dir.mkdir(parents=True, exist_ok=True)
    created = create_job_structure(job_dir, template, force)

    for fpath in created:
        ok(fpath)

    success_box(t("init.success", name=c(C.WH, name)))
    click.echo()
    info(t("init.next_steps"))
    info(t("init.step1", path=c(C.WH, f"./{name}/")))
    if (job_dir / ".env.example").exists():
        info(t("init.step2"))
    info(t("init.step3", cmd=c(C.WH, f"hydra test {name}")))
    info(t("init.step4", cmd=c(C.WH, f"hdrctl run  {name}")))
    click.echo()


# ─────────────────────────────────────────────────────────────────────────────
# Commande : test
# ─────────────────────────────────────────────────────────────────────────────

@cli.command("test", help=t("help.test.docstring"))
@_lang_option
@click.argument("path", default=".", type=click.Path())
@click.option("--only-sources", "only_src", is_flag=True, default=False,
              help=t("help.test.only_sources"))
@click.option("--only-destinations", "only_dst", is_flag=True, default=False,
              help=t("help.test.only_destinations"))
@click.option("--only-transform", "only_trf", is_flag=True, default=False,
              help=t("help.test.only_transform"))
@click.option("-s", "--sources", "sources_file", default=None, metavar="FILE",
              help=t("help.test.sources"))
@click.option("-d", "--destinations", "destinations_file", default=None, metavar="FILE",
              help=t("help.test.destinations"))
@click.option("-p", "--pipeline", "pipeline_file", default=None, metavar="FILE",
              help=t("help.test.pipeline"))
@click.option("-t", "--transformations", "transformations_file", default=None, metavar="FILE",
              help=t("help.test.transformations"))
def cmd_test(path: str, only_src: bool, only_dst: bool, only_trf: bool,
             sources_file: Optional[str], destinations_file: Optional[str],
             pipeline_file: Optional[str], transformations_file: Optional[str]) -> None:
    """Valide la configuration d'un job (YAML + connexions)."""
    print_banner()
    job_dir = Path(path).resolve()

    if not job_dir.exists() or not job_dir.is_dir():
        error_box(t("dir.not_found", path=path))
        sys.exit(1)

    click.echo(f"\n  {c(C.WH, t('test.job_title'))}  {c(C.CY, job_dir.name)}\n")

    job_files = resolve_job_files(
        job_dir,
        sources=sources_file,
        destinations=destinations_file,
        pipeline=pipeline_file,
        transformations=transformations_file,
    )

    all_ok = True

    # ── Sources ───────────────────────────────────────────────────────
    if not only_dst and not only_trf:
        section("Sources")
        src_path = job_files["sources"]
        if not src_path.exists():
            err_line(t("test.sources_missing"))
            all_ok = False
        else:
            errs = _validate_sources_yaml(src_path)
            if errs:
                for e in errs:
                    err_line(f"sources.yaml : {e}")
                all_ok = False
            else:
                ok(f"{c(C.WH, 'sources.yaml'):<36} — {t('validate.dsl_valid')}")

            # Test connexion optionnel
            import yaml
            try:
                data = yaml.safe_load(_read_yaml(src_path))
                for src_name, src_def in (data or {}).get("sources", {}).items():
                    ctype = src_def.get("type", "?")
                    if ctype in ("csv", "json", "parquet"):
                        ok(f"{c(C.WH, src_name):<36} — {t('test.local_file', ctype=ctype)}")
                    else:
                        ok(f"{c(C.WH, src_name):<36} — {t('test.conn_not_tested', ctype=ctype)}")
            except Exception:
                pass

    # ── Destinations ──────────────────────────────────────────────────
    if not only_src and not only_trf:
        section("Destinations")
        dst_path = job_files["destinations"]
        if not dst_path.exists():
            err_line(t("test.destinations_missing"))
            all_ok = False
        else:
            errs = _validate_destinations_yaml(dst_path)
            if errs:
                for e in errs:
                    err_line(f"destinations.yaml : {e}")
                all_ok = False
            else:
                ok(f"{c(C.WH, 'destinations.yaml'):<36} — {t('validate.dsl_valid')}")
                # Vérifier mode upsert + key
                import yaml
                try:
                    data = yaml.safe_load(_read_yaml(dst_path))
                    for dst_name, dst_def in (data or {}).get("destinations", {}).items():
                        load = dst_def.get("load", {})
                        mode = load.get("mode", "append")
                        key  = load.get("key")
                        if mode == "upsert" and key:
                            ok(f"{c(C.WH, dst_name):<36} — {t('test.upsert_mode', key=key)}")
                        else:
                            ok(f"{c(C.WH, dst_name):<36} — {t('test.mode', mode=mode)}")
                except Exception:
                    pass

    # ── Transformations ───────────────────────────────────────────────
    if not only_src and not only_dst:
        section("Transformations")
        trf_path = job_files["transformations"]
        if not trf_path.exists():
            info(t("test.transform_absent"))
        else:
            errs = _validate_transform_yaml(trf_path)
            if errs:
                for e in errs:
                    err_line(f"transformations.yaml : {e}")
                all_ok = False
            else:
                import yaml
                try:
                    data  = yaml.safe_load(_read_yaml(trf_path))
                    steps = (data or {}).get("steps", [])
                    ok(f"{c(C.WH, 'transformations.yaml'):<36} — {t('validate.steps_valid', n=len(steps))}")
                    ops = [next(iter(s)) for s in steps if isinstance(s, dict)]
                    if ops:
                        info(t("validate.ops_list", ops=", ".join(ops)))
                except Exception:
                    ok(f"{c(C.WH, 'transformations.yaml'):<36} — {t('validate.dsl_valid')}")

    # ── Secrets ───────────────────────────────────────────────────────
    if not only_src and not only_dst and not only_trf:
        section(t("run.section.env"))
        env_found = False
        for env_path in [job_dir / ".env", job_dir.parent / ".env"]:
            if env_path.exists():
                try:
                    lines = env_path.read_text().splitlines()
                    keys  = [l.split("=")[0].strip() for l in lines
                             if l.strip() and not l.startswith("#") and "=" in l]
                    ok(f"{c(C.WH, env_path.name):<36} — {t('test.env_vars_count', count=len(keys), keys=' '.join(keys))}")
                    env_found = True
                except Exception:
                    pass
        if not env_found:
            info(t("test.env_not_found"))

    # ── Résultat final ────────────────────────────────────────────────
    click.echo()
    if all_ok:
        success_box(t("test.all_ok"))
        info(t("run.hint", cmd=c(C.WH, f"hydra run {path}")))
        sys.exit(0)
    else:
        error_box(t("test.errors"))
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Commande : validate
# ─────────────────────────────────────────────────────────────────────────────

@cli.command("validate", help=t("help.validate.docstring"))
@_lang_option
@click.argument("path", default=".", type=click.Path())
@click.option("--strict", is_flag=True, default=False, help=t("help.validate.strict"))
@click.option("-s", "--sources", "sources_file", default=None, metavar="FILE",
              help=t("help.validate.sources"))
@click.option("-d", "--destinations", "destinations_file", default=None, metavar="FILE",
              help=t("help.validate.destinations"))
@click.option("-p", "--pipeline", "pipeline_file", default=None, metavar="FILE",
              help=t("help.validate.pipeline"))
@click.option("-t", "--transformations", "transformations_file", default=None, metavar="FILE",
              help=t("help.validate.transformations"))
def cmd_validate(path: str, strict: bool,
                 sources_file: Optional[str] = None, destinations_file: Optional[str] = None,
                 pipeline_file: Optional[str] = None, transformations_file: Optional[str] = None) -> None:
    """Validation stricte du DSL YAML (sans test de connexion)."""
    print_banner()
    job_dir = Path(path).resolve()

    if not job_dir.exists() or not job_dir.is_dir():
        error_box(t("dir.not_found", path=path))
        sys.exit(1)

    label = t("validate.strict_label") if strict else t("validate.dsl_label")
    click.echo(f"\n  {c(C.WH, f'🔍 {label}')}  {c(C.CY, job_dir.name)}\n")

    job_files = resolve_job_files(
        job_dir,
        sources=sources_file,
        destinations=destinations_file,
        pipeline=pipeline_file,
        transformations=transformations_file,
    )

    all_ok   = True
    all_errs = []

    checks = [
        ("pipeline.yaml", job_files["pipeline"], None),
        ("sources.yaml", job_files["sources"], _validate_sources_yaml),
        ("destinations.yaml", job_files["destinations"], _validate_destinations_yaml),
        ("transformations.yaml", job_files["transformations"], _validate_transform_yaml),
    ]

    for fname, fpath, validator in checks:
        if not fpath.exists():
            if fname == "transformations.yaml":
                info(f"{c(C.WH, fname):<36} — {t('validate.optional_absent')}")
            else:
                err_line(f"{fname} — {t('validate.missing')}")
                all_ok = False
            continue

        ok(f"{c(C.WH, fname):<36} — {t('validate.present')}")

        if validator:
            errs = validator(fpath)
            if errs:
                all_ok = False
                for e in errs:
                    err_line(f"  → {e}")
                    all_errs.append(f"{fname}: {e}")
            else:
                ok(f"{c(C.WH, fname):<36} — {t('validate.pydantic_valid')}")

    # Pipeline cohérence
    try:
        import yaml
        pipeline = yaml.safe_load(_read_yaml(job_files["pipeline"]))
        sources  = yaml.safe_load(_read_yaml(job_files["sources"]))
        dests    = yaml.safe_load(_read_yaml(job_files["destinations"]))
        pipe     = pipeline.get("pipeline", {})
        from_id  = pipe.get("from")
        to_id    = pipe.get("to")
        if from_id and from_id not in (sources or {}).get("sources", {}):
            err_line(t("validate.pipeline_from_missing", from_id=from_id))
            all_ok = False
        else:
            ok(f"{c(C.WH, 'pipeline.from'):<36} — {t('validate.resolved', id=from_id)}")
        if to_id and to_id not in (dests or {}).get("destinations", {}):
            err_line(t("validate.pipeline_to_missing", to_id=to_id))
            all_ok = False
        else:
            ok(f"{c(C.WH, 'pipeline.to'):<36} — {t('validate.resolved', id=to_id)}")
    except Exception as e:
        err_line(t("validate.coherence_error", error=e))
        all_ok = False

    # Mode strict — vérifications supplémentaires
    if strict and job_files["transformations"].exists():
        section(t("validate.strict_section"))
        try:
            import yaml
            data  = yaml.safe_load(_read_yaml(job_files["transformations"]))
            steps = (data or {}).get("steps", [])
            ops   = [next(iter(s)) for s in steps if isinstance(s, dict)]
            ok(f"{c(C.WH, t('validate.ops_recognized')):<36} — {', '.join(ops) if ops else 'aucune'}")

            # Vérifier expressions calculate/filter (parse only, no eval)
            for step in steps:
                if not isinstance(step, dict):
                    continue
                op   = next(iter(step))
                pms  = step[op]
                if op == "filter" and isinstance(pms, dict):
                    expr = pms.get("expr", "")
                    ok(f"{c(C.WH, f'filter.expr'):<36} — '{expr[:40]}'")
                if op == "calculate" and isinstance(pms, dict):
                    col  = pms.get("column", "?")
                    expr = pms.get("expr", "")
                    ok(f"{c(C.WH, f'calculate.{col}'):<36} — '{expr[:40]}'")
        except Exception as e:
            err_line(t("validate.strict_error", error=e))

    click.echo()
    if all_ok:
        success_box(t("validate.success"))
        sys.exit(0)
    else:
        error_box(t("validate.failure", count=len(all_errs)))
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Commande : list
# ─────────────────────────────────────────────────────────────────────────────

@cli.command("list", help=t("help.list.docstring"))
@_lang_option
@click.argument("path", default=".", type=click.Path())
def cmd_list(path: str) -> None:
    """Liste les jobs Hydra dans un répertoire."""
    print_banner()
    root = Path(path).resolve()

    if not root.exists() or not root.is_dir():
        error_box(t("dir.not_found", path=path))
        sys.exit(1)

    click.echo(f"  {c(C.WH, t('list.header'))} {c(C.CY, str(root))}\n")
    click.echo(f"  {c(C.DM, '─' * 70)}")

    jobs = find_jobs(root)

    if not jobs:
        info(t("list.none_found"))
        info(t("list.create_hint", cmd=c(C.WH, "hydra init mon_job")))
        sys.exit(0)

    n_ok = 0
    for job_path in jobs:
        name    = job_path.name
        has_trf = (job_path / "transformations.yaml").exists()
        has_env = (job_path / ".env").exists()
        status  = c(C.GR, "✅ OK")
        n_ok   += 1
        extras  = []
        if has_trf:
            extras.append("transforms")
        if has_env:
            extras.append(".env")
        extra_str = c(C.DM, f"  [{', '.join(extras)}]") if extras else ""
        click.echo(f"  {c(C.CY, name):<30} {status:<25} {extra_str}")

    click.echo(f"  {c(C.DM, '─' * 70)}")
    click.echo()
    info(t("list.summary", count=len(jobs), ok=c(C.GR, str(n_ok) + " OK")))
    info(t("list.run_hint", cmd=c(C.WH, "hydra run <nom>")))
    click.echo()



# ──────────────────────────────────────────────────────────────────────────────
# Commande : clear
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("clear", help=t("help.clear.docstring"))
def cmd_clear() -> None:
    """Clear the terminal screen."""
    click.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Groupe de commandes : workflow
# ─────────────────────────────────────────────────────────────────────────────

@cli.group("workflow", invoke_without_command=False, help=t("help.workflow.docstring"))
@_lang_option
def cmd_workflow() -> None:
    """Groupe workflow."""
    pass


@cmd_workflow.command("run", help=t("help.workflow.run.docstring"))
@_lang_option
@click.argument("path", default="./workflow.yaml", metavar="PATH")
def cmd_workflow_run(path: str) -> None:
    """Execute un workflow DAG."""
    from workflow.parser import load_workflow, validate_workflow
    from workflow.runner import WorkflowRunner

    print_banner()
    wf_path = Path(path).resolve()
    if not wf_path.exists():
        error_box(t("workflow.file_not_found", path=str(wf_path)))
        sys.exit(1)

    wf = load_workflow(wf_path)
    info(t("workflow.run.starting", name=c(C.CY, wf.name)))
    click.echo(c(C.DM, "  " + "─" * 56))

    runner = WorkflowRunner(wf, base_dir=wf_path.parent)
    result = runner.run()

    click.echo()
    for sr in result.steps:
        if sr.success:
            click.echo(f"  {c(C.GR, '✓')}  {t('workflow.run.step_ok', name=sr.step_name, duration=f'{sr.duration:.1f}')}")
        elif sr.error and "skipped" in str(sr.error).lower():
            click.echo(f"  {c(C.YL, '⏭')}  {t('workflow.run.step_skip', name=sr.step_name)}")
        else:
            click.echo(f"  {c(C.RD, '✗')}  {t('workflow.run.step_fail', name=sr.step_name, error=sr.error)}")

    click.echo()
    if result.success:
        ok_count = sum(1 for s in result.steps if s.success)
        success_box(t("workflow.run.success", name=wf.name, duration=f"{result.duration:.1f}", ok=ok_count, total=len(result.steps)))
    else:
        error_box(t("workflow.run.failure", name=wf.name, duration=f"{result.duration:.1f}", error=result.error))
        sys.exit(1)


@cmd_workflow.command("validate", help=t("help.workflow.validate.docstring"))
@_lang_option
@click.argument("path", default="./workflow.yaml", metavar="PATH")
def cmd_workflow_validate(path: str) -> None:
    """Valide un manifest workflow sans l'executer."""
    from workflow.parser import validate_workflow

    wf_path = Path(path).resolve()
    if not wf_path.exists():
        error_box(t("workflow.file_not_found", path=str(wf_path)))
        sys.exit(1)

    ok, msg = validate_workflow(wf_path)
    if ok:
        success_box(t("workflow.validate.success"))
    else:
        error_box(t("workflow.validate.failure", error=msg))
        sys.exit(1)


@cmd_workflow.command("list", help=t("help.workflow.list.docstring"))
@_lang_option
@click.argument("path", default=".", metavar="PATH")
def cmd_workflow_list(path: str) -> None:
    """Liste les workflows d'un dossier."""
    search_dir = Path(path).resolve()
    if not search_dir.exists():
        error_box(t("dir.not_found", path=str(search_dir)))
        sys.exit(1)

    workflows = sorted(search_dir.rglob("workflow.yaml"))
    info(t("workflow.list.header") + f"  {c(C.CY, str(search_dir))}")
    click.echo(c(C.DM, "  " + "─" * 56))

    if not workflows:
        info(t("workflow.list.none_found"))
        sys.exit(0)

    for wf_path in workflows:
        try:
            from workflow.parser import load_workflow
            wf = load_workflow(wf_path)
            n_steps = len(wf.steps)
            click.echo(f"  {c(C.CY, wf.name):<30} {c(C.DM, str(wf_path.relative_to(search_dir)))}  ({n_steps} steps)")
        except Exception:
            click.echo(f"  {c(C.RD, '?')} {wf_path.relative_to(search_dir)}")

    click.echo()
    info(t("workflow.list.summary", count=len(workflows)))
    click.echo()



# ─────────────────────────────────────────────────────────────────────────────
# Scaffold workflow : templates manifest + job manifests
# ─────────────────────────────────────────────────────────────────────────────

# workflow.yaml par template (les chemins pointent vers ./jobs/<step>)
WORKFLOW_TEMPLATES: dict[str, str] = {
    "basic": """\
workflow:
  name: "{name}"
  description: "Sequential pipeline: job_a → job_b → notify"
  trigger:
    type: manual
  steps:
    - name: "job_a"
      type: job
      job: "./jobs/job_a"
      depends_on: []
      on_failure: fail

    - name: "job_b"
      type: job
      job: "./jobs/job_b"
      depends_on: ["job_a"]
      on_failure: fail

    - name: "notify"
      type: action
      action: log
      params:
        message: "Workflow {name} completed successfully."
      depends_on: ["job_b"]
      on_failure: skip
""",

    "parallel": """\
workflow:
  name: "{name}"
  description: "Fan-out / fan-in: extract → [transform_a, transform_b] → load"
  trigger:
    type: manual
  steps:
    - name: "extract"
      type: job
      job: "./jobs/extract"
      depends_on: []
      on_failure: fail

    - name: "transform_a"
      type: job
      job: "./jobs/transform_a"
      depends_on: ["extract"]
      on_failure: fail

    - name: "transform_b"
      type: job
      job: "./jobs/transform_b"
      depends_on: ["extract"]
      on_failure: fail

    - name: "load"
      type: job
      job: "./jobs/load"
      depends_on: ["transform_a", "transform_b"]
      on_failure: fail
""",

    "scheduled": """\
workflow:
  name: "{name}"
  description: "Scheduled pipeline — runs daily at 08:00"
  trigger:
    type: schedule
    cron: "0 8 * * *"
  steps:
    - name: "extract"
      type: job
      job: "./jobs/extract"
      depends_on: []
      on_failure: fail

    - name: "transform"
      type: job
      job: "./jobs/transform"
      depends_on: ["extract"]
      on_failure: fail

    - name: "load"
      type: job
      job: "./jobs/load"
      depends_on: ["transform"]
      on_failure: fail

    - name: "notify"
      type: action
      action: log
      params:
        message: "Scheduled workflow {name} completed."
      depends_on: ["load"]
      on_failure: skip
""",

    "notify": """\
workflow:
  name: "{name}"
  description: "Pipeline with webhook notification on completion"
  trigger:
    type: manual
  steps:
    - name: "extract"
      type: job
      job: "./jobs/extract"
      depends_on: []
      on_failure: fail

    - name: "transform"
      type: job
      job: "./jobs/transform"
      depends_on: ["extract"]
      on_failure: fail

    - name: "load"
      type: job
      job: "./jobs/load"
      depends_on: ["transform"]
      on_failure: fail

    - name: "webhook_success"
      type: action
      action: webhook
      params:
        url: "https://hooks.example.com/notify"
        method: POST
        body:
          workflow: "{name}"
          status: "success"
      depends_on: ["load"]
      on_failure: skip
""",
}

VALID_WORKFLOW_TEMPLATES = list(WORKFLOW_TEMPLATES.keys())

# ─────────────────────────────────────────────────────────────────────────────
# Contenu des manifests générés pour chaque job scaffoldé
# ─────────────────────────────────────────────────────────────────────────────

def _sources_yaml(job_name: str) -> str:
    return f"""\
version: "1.0"
sources:
  src_{job_name}:
    type: csv
    connection: {{}}
    extract:
      table: data/input.csv
      batch_size: 1000
"""

def _destinations_yaml(job_name: str) -> str:
    return f"""\
version: "1.0"
destinations:
  dst_{job_name}:
    type: csv
    connection: {{}}
    load:
      table: data/output.csv
      mode: replace
"""

def _pipeline_yaml(job_name: str) -> str:
    return f"""\
version: "1.0"
pipeline:
  from: src_{job_name}
  to: dst_{job_name}
"""

def _transformations_yaml() -> str:
    return """\
version: "1.0"
transformations:
  steps:
    - filter:
        expr: "1 == 1"   # Remplacer par votre logique
"""

SAMPLE_CSV = """\
id,name,value
1,item_a,10.5
2,item_b,20.0
3,item_c,5.75
"""

ENV_EXAMPLE = """\
# Variables d'environnement pour ce workflow
# Copier ce fichier en .env et remplir les valeurs

# DB_HOST=localhost
# DB_PORT=3306
# DB_USER=hydra
# DB_PASS=secret
"""


def _scaffold_job(jobs_dir: Path, job_name: str) -> list[str]:
    """Crée le dossier d'un job et retourne la liste des fichiers créés."""
    job_dir = jobs_dir / job_name
    data_dir = job_dir / "data"
    job_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(exist_ok=True)

    files = []
    for fname, content_fn in [
        ("sources.yaml",        lambda: _sources_yaml(job_name)),
        ("destinations.yaml",   lambda: _destinations_yaml(job_name)),
        ("pipeline.yaml",       lambda: _pipeline_yaml(job_name)),
        ("transformations.yaml",lambda: _transformations_yaml()),
    ]:
        path = job_dir / fname
        path.write_text(content_fn(), encoding="utf-8")
        files.append(str(path.relative_to(job_dir.parent.parent)))

    sample = data_dir / "input.csv"
    sample.write_text(SAMPLE_CSV, encoding="utf-8")
    files.append(str(sample.relative_to(job_dir.parent.parent)))
    return files


def _extract_job_steps(workflow_yaml: str) -> list[str]:
    """Extrait les noms des steps de type job depuis le YAML workflow."""
    import re
    job_names = []
    for line in workflow_yaml.splitlines():
        m = re.match(r'\s+job:\s+"?\.\/jobs\/([^"]+)"?', line)
        if m:
            job_names.append(m.group(1).strip())
    return job_names


# ─────────────────────────────────────────────────────────────────────────────
# Commande : hydra workflow init
# ─────────────────────────────────────────────────────────────────────────────

@cmd_workflow.command("init", help=t("help.workflow.init.docstring"))
@_lang_option
@click.argument("name", metavar="NAME")
@click.option("--template", "-t", default="basic",
              type=click.Choice(VALID_WORKFLOW_TEMPLATES),
              show_default=True,
              help=t("help.workflow.init.template"))
@click.option("--force", is_flag=True, default=False,
              help=t("help.workflow.init.force"))
def cmd_workflow_init(name: str, template: str, force: bool) -> None:
    """Scaffolde un projet workflow complet (dossiers + manifests)."""
    project_dir = Path(name).resolve()

    if project_dir.exists() and not force:
        error_box(t("workflow.init.exists", path=name))
        sys.exit(1)

    project_dir.mkdir(parents=True, exist_ok=True)
    jobs_dir = project_dir / "jobs"
    jobs_dir.mkdir(exist_ok=True)

    # Écrire workflow.yaml
    raw_template = WORKFLOW_TEMPLATES[template]
    workflow_content = raw_template.format(name=name)
    workflow_file = project_dir / "workflow.yaml"
    workflow_file.write_text(workflow_content, encoding="utf-8")

    # Écrire .env.example
    (project_dir / ".env.example").write_text(ENV_EXAMPLE, encoding="utf-8")

    # Scaffolder chaque job référencé dans le template
    job_names = _extract_job_steps(workflow_content)
    created_jobs = []
    for job_name in job_names:
        _scaffold_job(jobs_dir, job_name)
        created_jobs.append(job_name)

    # Affichage arborescence
    success_box(t("workflow.init.success", name=name, path=project_dir.name))
    click.echo()
    info("  " + project_dir.name + "/")
    info("  ├── workflow.yaml")
    info("  ├── .env.example")
    info("  └── jobs/")
    for i, job in enumerate(created_jobs):
        is_last = i == len(created_jobs) - 1
        prefix = "    └──" if is_last else "    ├──"
        pad    = "        " if is_last else "    │   "
        info("  " + prefix + " " + job + "/")
        info("  " + pad + "  ├── sources.yaml")
        info("  " + pad + "  ├── destinations.yaml")
        info("  " + pad + "  ├── pipeline.yaml")
        info("  " + pad + "  ├── transformations.yaml")
        info("  " + pad + "  └── data/input.csv")

    click.echo()
    info(t("workflow.init.next", path=project_dir.name + "/workflow.yaml"))
    click.echo()


@cli.command("serve", help="Démarre l'API FastAPI Hydra (Studio backend).")
@_lang_option
@click.option("--host", default="127.0.0.1", show_default=True, help="Adresse d'écoute.")
@click.option("--port", default=5678, show_default=True, type=int, help="Port d'écoute.")
@click.option("--reload", is_flag=True, default=False, help="Hot-reload (dev uniquement).")
@click.option("--workspace", default=None, envvar="HYDRA_WORKSPACE",
              help="Répertoire racine des projets Studio (défaut : ~/hydra-workspace).")
def cmd_serve(host: str, port: int, reload: bool, workspace: Optional[str]) -> None:
    """Démarre l'API FastAPI Hydra sur http://<host>:<port>."""
    try:
        import uvicorn
    except ImportError:
        click.echo("❌  uvicorn n'est pas installé. Lancez : pip install uvicorn[standard]", err=True)
        sys.exit(1)

    # Résoudre la racine du projet (dossier contenant cli/ et api/)
    # __file__ = <projet>/cli/hdrctl.py → parent.parent = <projet>/
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Changer le cwd pour que les chemins relatifs dans les jobs fonctionnent
    import os
    os.chdir(project_root)

    if workspace:
        os.environ["HYDRA_WORKSPACE"] = workspace

    print_banner()
    click.echo(f"🚀  Hydra API démarrée sur http://{host}:{port}")
    click.echo(f"📚  Docs disponibles sur http://{host}:{port}/docs")
    click.echo()

    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=reload,
        reload_dirs=[str(project_root)] if reload else None,
        log_level="info",
    )


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
