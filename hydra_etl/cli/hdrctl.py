#!/usr/bin/env python3
"""
hdrctl — Hydra ETL Control CLI

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

from hydra_etl.cli.i18n import t, set_lang

import logging as _logging

# La CLI affiche elle-même le résultat des workflows. Sans handler, les
# logger.error du moteur passeraient par le handler de dernier recours de Python
# et apparaîtraient une seconde fois, sur stderr. Un NullHandler n'empêche pas la
# propagation vers les handlers configurés ailleurs (hdrctl serve, -vvv).
_logging.getLogger("hydra_etl.workflow").addHandler(_logging.NullHandler())

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

# Regle 3.1 : source de verite unique, hydra_etl/__init__.py.
# Ne jamais reintroduire un litteral ici.
from hydra_etl import __version__ as VERSION


def _harden_stdio() -> None:
    """
    Empêche `hdrctl` de planter quand sa sortie n'est pas en UTF-8.

    Sous Windows, une sortie redirigée (fichier, pipe, CI, sous-processus)
    hérite de cp1252 : le premier emoji imprimé lève alors UnicodeEncodeError
    et la commande échoue — alors que le travail demandé, lui, s'est bien
    passé. On remplace les caractères non encodables au lieu d'échouer.

    Le bandeau et les filets ont déjà leur propre repli ASCII ; ceci couvre
    tous les autres glyphes (✅ ❌ ⚠ 🔍 ✓ ✗) d'un seul geste.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass


_harden_stdio()

_HYDRA_ART = """
                                          @
                                             @@@@@-
                                                  @@%+ -
                                @              @@@@::: @@@.
                           .@               @@@@:.:::-:%  #*
                         @@                 @..::+@@@@@@@@@@@@@
                       @                   @@:::+@          @@
                    .@                     @.:::@                    @@
                   @@                     @@::..@                 @@@@%@@.:
                 @@      @@@@@@            @.::.%@              @@@-..:::.#+=
                @@             @@@@@@      @%::::%@           @@@-:#@@@#..* *
              %@@          @@@@@::@ @@@     @%.:::@@        @@%.:@@@   @@@@@@@:@
              @          @@@::::@@@@@-%@@@   @@::::%@       @:::%@           @@@
             @           @::.=@@@ @@@@@@@@    @@.:::%@     @=.::@
           -#@          @@..:%                 @:::::%@    @::::@
           @@           @::::#                 @::.:::@    @::::@         @  @             @
          %@            @%:::=@@               @:.::::@   @#:.:=@      @@@@ @@@@@           @
          +@             @@#:..@@@@@           @::.:::@   @.:::@      @@::+==::%@@@         @@
         %@@               @@@:::::@@@@@      @@:::::@@  @@::.+@   @@@@:..::::.%  @@        @@
         @@                  @@@@@:::::%@@@  @@.:::.@@  @%.:::@   @%.::@@@@@@@@@@@@@@@@      @
         @@                      @@@%.:::.%@@ @@:.:@@  @%::::@@  @%:::%@          *@@@@      @:
         @@      @@@@@@@@@@@@@      @@=.::::@@ @:::% @@@:::.@@  @%:::@@                      @
         @@          %....*   @@      @%:.:::@ @::.%%@.::.#@@  @@:.:@@                       @
         @@        @@@::@@@@@@@@@@@    @:::..@@@.:::::::.@@   @@:::@@                        @.
        .@@@      @@.::@@  -           @-.:::::::::...:@@@  @@%..@@@        @@ @            @@
         +-@      @.:::%               **::.:..::.:.:%%@  @@%.:@@@    @@@@@@%%@@@@          @@.
          .@      @@:.:@@               *::::::.:::::# @@@=.%@@@    @@@-:+@@*:=  @@         @@
           @@      @@+:.%@@@@@@        @=..:.::::.:::###.%@@@     @@%::@@@  @@@@@@%@       @@
           :%@       @@@@:::..+@@@@    @:.::::..:::.:.%@@@    @@@@%::@@@         @@@@@    @@@
           *@@          @@@@@@::::@@@  @:.::.::::.::%@@   @@@@%::::@@@                    @@
            @@@              @@@%:::@@ @.::::::::.%@@  @@@#.:::%@@@@                     @@
            .=#@                @%:::@ @::.:::..:@@  @@@.::@@@@@                        @@
               +@@               @@::%%%::::::.:@@ @@@::#@@@                           @@
                -@@               @#:::.:::.:::@@ @@:..@@                            @@@
                 @@@#              @..:::::::.:@  @.::%@                            @@*.
                  @%@@             @*::::..::::@ @#::%@                           @@@
                    @@@@            @:::.::...:@ @:.:@                           @@@
                      @@@@@         @@+::.::::.@ @::.@                         @@@
                        -:@@@         @%:.::::.@ @%::@@                     @@@@
                            %@@@       @@@:.:::@@ @@::%@                 @@@@-
                               @@@@@     @@@@::.%@ @:-:@@             @@@-:
                                .: @@@@@@   %...:@@@ -..%@@@@@%@@@@@@%=
                                    . : :%@@@@:::::-:-::::+@@@*   :
                                                             .
"""

def _fit_art(art: str, max_width: int) -> list[str]:
    """Downscale l'ASCII art (nearest-neighbor) pour tenir dans max_width.

    N'agrandit jamais : si l'art tient déjà, il est renvoyé tel quel.
    Le ratio hauteur/largeur est préservé, avec correction du fait qu'une
    cellule terminal est ~2x plus haute que large.
    """
    lines = art.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return []
    w = max(len(l) for l in lines)
    lines = [l.ljust(w) for l in lines]
    h = len(lines)
    if max_width <= 0 or w <= max_width:
        return [l.rstrip() for l in lines]
    scale = max_width / w
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))  # cellule ~2:1 -> pas de /2 supplémentaire
    out = []
    for r in range(new_h):
        row = lines[min(int(r / scale), h - 1)]
        out.append(
            "".join(row[min(int(cc / scale), w - 1)] for cc in range(new_w)).rstrip()
        )
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def _art_width(art: str) -> int:
    lines = [l for l in art.split("\n") if l.strip()]
    return max((len(l.rstrip()) for l in lines), default=0)


# Facteur d'échelle du banner : 0.5 = moitié de la taille native (95 cols -> ~48)
_ART_SCALE = 0.5

# Wordmark "HYDRA" affiché sous l'art (police ansi_shadow, letter-spacing 2, 49 colonnes)
_HYDRA_WORD = (
    "██╗  ██╗  ██╗   ██╗  ██████╗   ██████╗    █████╗ \n"
    "██║  ██║  ╚██╗ ██╔╝  ██╔══██╗  ██╔══██╗  ██╔══██╗\n"
    "███████║   ╚████╔╝   ██║  ██║  ██████╔╝  ███████║\n"
    "██╔══██║    ╚██╔╝    ██║  ██║  ██╔══██╗  ██╔══██║\n"
    "██║  ██║     ██║     ██████╔╝  ██║  ██║  ██║  ██║\n"
    "╚═╝  ╚═╝     ╚═╝     ╚═════╝   ╚═╝  ╚═╝  ╚═╝  ╚═╝"
)

# Repli ASCII pur si le terminal ne gère pas l'UTF-8 (Windows cp1252, etc.)
_HYDRA_WORD_ASCII = (
    " _   _   __   __   ____     ____       _    \n"
    "| | | |  \\ \\ / /  |  _ \\   |  _ \\     / \\   \n"
    "| |_| |   \\ V /   | | | |  | |_) |   / _ \\  \n"
    "|  _  |    | |    | |_| |  |  _ <   / ___ \\ \n"
    "|_| |_|    |_|    |____/   |_| \\_\\ /_/   \\_\\"
)


def print_banner() -> None:
    """Affiche le banner HYDRA ETL en ASCII art, mis à l'échelle et adapté au terminal."""
    import shutil
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    target = int(round(_art_width(_HYDRA_ART) * _ART_SCALE))
    lines = _fit_art(_HYDRA_ART, min(target, cols - 2))  # marge de 2 espaces à gauche
    click.echo()
    for line in lines:
        click.echo("  " + c(C.CY + C.BD, line))

    # Wordmark HYDRA centré sous l'art
    art_w = max((len(l) for l in lines), default=0)
    enc = sys.stdout.encoding or "utf-8"

    def _encodable(s: str) -> bool:
        try:
            s.encode(enc)
            return True
        except (UnicodeEncodeError, LookupError):
            return False

    word = _HYDRA_WORD if _encodable(_HYDRA_WORD) else _HYDRA_WORD_ASCII
    wlines = word.split("\n")
    word_w = max(len(l) for l in wlines)
    if cols - 2 >= word_w:
        pad = " " * max(0, (art_w - word_w) // 2)
        click.echo()
        for line in wlines:
            click.echo("  " + pad + c(C.CY + C.BD, line))

    rule_char = "─" if _encodable("─") else "-"
    rule = rule_char * min(28, max(4, cols - 40))
    click.echo(f"\n  {c(C.DM, t('banner.subtitle'))}  {c(C.WH, 'v' + VERSION)}  {c(C.DM, rule)}")
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
  - cast:
      mapping:
        value: float
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
            f"# Job: {job_dir.name}\n\n"
            f"Template: `{template}`\n\n"
            "## Files\n\n"
            "- `sources.yaml` — where the data comes from\n"
            "- `destinations.yaml` — where the data goes\n"
            "- `pipeline.yaml` — which source feeds which destination\n"
            "- `transformations.yaml` — DSL transformations (optional)\n"
            "- `.env` — credentials (copy it from `.env.example` when present)\n\n"
            "## Commands\n\n"
            "```bash\n"
            f"hdrctl validate {job_dir.name}   # check the YAML files\n"
            f"hdrctl test     {job_dir.name}   # check the connections\n"
            f"hdrctl run      {job_dir.name}   # run this job alone\n"
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
        from hydra_etl.internal.parser.source import SourceParser
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
        from hydra_etl.internal.parser.destination import DestinationParser
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
        from hydra_etl.internal.parser.transform import TransformParser
        TransformParser().parse(data)
    except Exception as e:
        errors.append(str(e))
    return errors


def _test_connection(connector_type: str, connection: dict, name: str) -> tuple[bool, str]:
    """Tente une connexion réelle. Retourne (success, message)."""
    try:
        from hydra_etl.internal.connector.registry import build_connector
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
@click.option("--profile", "profile", is_flag=True, default=False, help=t("help.run.profile"))
@click.option("--secrets-file", "secrets_file", default=None, metavar="FILE",
              help=t("help.run.secrets_file"))
def cmd_run(path: str, verbosity: int, dry_run: bool,
            sources_file: Optional[str], destinations_file: Optional[str],
            pipeline_file: Optional[str], transformations_file: Optional[str],
            on_success: Optional[str], on_failure: Optional[str],
            on_finish: Optional[str],
            env_name: Optional[str] = None, param_overrides: tuple = (),
            profile: bool = False, secrets_file: Optional[str] = None) -> None:
    """Exécute un pipeline ETL."""
    verbosity = verbosity or 0  # click < 8.2 passes None when no -v flag is given
    print_banner()
    job_dir = Path(path).resolve()

    # Validation existence
    if not job_dir.exists() or not job_dir.is_dir():
        error_box(t("dir.not_found", path=path))
        sys.exit(1)
    _use_secrets_file(secrets_file)

    # Projet (.hydra/ sans fichiers de job à la racine) → tous ses workflows,
    # dans l'ordre de workflows/thread.yaml. Sinon : un job seul.
    from hydra_etl.workflow.project import is_project_root
    if is_project_root(job_dir) and not _has_job_files(job_dir):
        job_only = [opt for opt, val in (("-s/--sources", sources_file),
                                         ("-d/--destinations", destinations_file),
                                         ("-p/--pipeline", pipeline_file),
                                         ("-t/--transformations", transformations_file),
                                         ("--profile", profile)) if val]
        if job_only:
            error_box(t("run.project.job_options", options=", ".join(job_only),
                        path=path))
            sys.exit(1)
        code = _run_project(job_dir, verbosity, dry_run, env_name,
                            _parse_param_overrides(param_overrides))
        status = "SUCCESS" if code == 0 else "FAILURE"
        if not dry_run:
            fire_hook("on-success", on_success if status == "SUCCESS" else None, verbosity)
            fire_hook("on-failure", on_failure if status == "FAILURE" else None, verbosity)
            fire_hook("on-finish", on_finish, verbosity)
        sys.exit(code)

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
    param_dict = _parse_param_overrides(param_overrides)

    # ── Mode dry-run ─────────────────────────────────────────────
    if dry_run:
        click.echo(f"\n  {c(C.YL + C.BD, t('run.dry_run_mode'))} — {c(C.DM, t('run.dry_run_no_write'))}")
        section(t("run.dry_run_section", job_name=c(C.CY, job_name)))
        click.echo()
        has_error = _run_validate_only(job_dir, verbosity, job_files)
        if has_error:
            click.echo()
            error_box(t("run.dry_run_failed"))
            sys.exit(1)
        success_box(t("run.dry_run_done"))
        info(t("run.hint", cmd=c(C.WH, f"hdrctl run {path}")))
        sys.exit(0)

    # ── Exécution réelle ──────────────────────────────────────────
    click.echo(f"\n  {c(C.WH, '▶')}  Pipeline  {c(C.CY + C.BD, job_name)}  {c(C.DM, f'— {path}')}")
    click.echo()

    t_start = time.monotonic()
    status = "FAILURE"

    try:
        from hydra_etl.internal.runner.executor import JobExecutor
        executor = JobExecutor(
            job_dir=job_dir,
            sources_file=job_files["sources"],
            destinations_file=job_files["destinations"],
            pipeline_file=job_files["pipeline"],
            transformations_file=job_files["transformations"] if job_files["transformations"].exists() else None,
            env=env_name,
            params=param_dict,
            profile=profile or None,
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

        if getattr(result, "profile", None):
            from hydra_etl.internal.runner.profiler import format_profile
            click.echo()
            for _line in format_profile(result.profile).splitlines():
                click.echo(f"  {c(C.DM, _line)}")

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


def _use_secrets_file(path: Optional[str]) -> None:
    """--secrets-file : fichier de secrets hors du projet (prend la place de
    .hydra/secrets pour ce run). Transmis au moteur par HYDRA_SECRETS_FILE."""
    if not path:
        return
    from hydra_etl.internal.config.secrets import SECRETS_FILE_ENV
    f = Path(path).expanduser().resolve()
    if not f.is_file():
        error_box(t("run.secrets_file_not_found", path=str(f)))
        sys.exit(1)
    os.environ[SECRETS_FILE_ENV] = str(f)


def _parse_param_overrides(items) -> dict:
    """--param KEY=VALUE (répétable) → dict. Sort en erreur si `=` manque."""
    out: dict = {}
    for item in items or ():
        if "=" not in item:
            error_box(t("run.param_invalid", item=item))
            sys.exit(1)
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _print_workflow_steps(wf, result, indent: str = "  ") -> None:
    """Une ligne par step (OK / échec / ignoré), sortie des actions script."""
    reported = set()
    for sr in result.steps:
        reported.add(sr.step_name)
        if sr.skipped:
            click.echo(f"{indent}{c(C.YL, '⏭')}  {t('workflow.run.step_skip', name=sr.step_name)}")
        elif sr.success:
            click.echo(f"{indent}{c(C.GR, '✓')}  {t('workflow.run.step_ok', name=sr.step_name, duration=f'{sr.duration:.1f}')}")
            _echo_step_output(sr)
        else:
            click.echo(f"{indent}{c(C.RD, '✗')}  {t('workflow.run.step_fail', name=sr.step_name, error=sr.error)}")
            _echo_step_output(sr)
    # Un échec en mode on_failure=fail arrête le run : les steps jamais atteints
    # n'ont pas de résultat. Les afficher quand même, sinon on ne voit pas ce
    # qui n'a pas tourné.
    for step in wf.steps:
        if step.name not in reported:
            click.echo(f"{indent}{c(C.YL, '⏭')}  {t('workflow.run.step_skip', name=step.name)}")


def _fmt_seconds(sec: float) -> str:
    return f"{sec:g}s"


def _run_project(root: Path, verbosity: int, dry_run: bool,
                 env_name: Optional[str], params: dict) -> int:
    """`hdrctl run <projet>` : valide tout, puis lance les workflows selon
    workflows/thread.yaml. Retourne le code de sortie (0 succès, 1 échec)."""
    from hydra_etl.workflow.project import (
        FAILED, INACTIVE, NOT_RUN, ProjectError, ProjectRunner, prepare_project,
    )

    try:
        plan = prepare_project(root)
    except ProjectError as e:
        error_box(t("run.project.invalid", name=root.name))
        for msg in e.errors:
            err_line(f"  — {msg}")
        return 1

    stages = plan.thread.thread
    n_wf = len(plan.thread.workflow_names())
    env_txt = f"  {c(C.DM, f'[env: {env_name}]')}" if env_name else ""
    click.echo(f"\n  {c(C.WH, '▶')}  {t('run.project.title', name=c(C.CY + C.BD, root.name), workflows=n_wf, stages=len(stages))}{env_txt}")
    if plan.implicit:
        info(t("run.project.no_thread"))
    if not plan.active_names:
        click.echo()
        info(t("run.project.none_active"))
        return 0

    if dry_run:
        click.echo(f"\n  {c(C.YL + C.BD, t('run.dry_run_mode'))} — {c(C.DM, t('run.dry_run_no_write'))}")
        section(t("run.project.plan"))
        for i, stage in enumerate(stages, 1):
            delay = f"  {c(C.DM, t('run.project.then_wait', seconds=_fmt_seconds(stage.delay_seconds)))}" \
                if stage.delay_seconds and i < len(stages) else ""
            click.echo(f"  {t('run.project.stage', index=i, total=len(stages), mode=stage.mode)}{delay}")
            for w in stage.workflows:
                if not w.active:
                    click.echo(f"     {c(C.YL, '⏭')}  {t('run.project.inactive', name=w.name)}")
                    continue
                wf = plan.workflows[w.name]
                steps = ", ".join(st.name for st in wf.steps)
                detail = f"({len(wf.steps)}: {steps})" if steps else "(0)"
                click.echo(f"     {c(C.GR, '•')}  {c(C.WH, w.name)}  {c(C.DM, detail)}")
                if w.fallback:
                    fb = w.fallback
                    triggers = []
                    if fb.when:
                        triggers.append(t("run.project.plan_fallback_when", when=fb.when))
                    if fb.on_failure:
                        triggers.append(t("run.project.plan_fallback_failure"))
                    click.echo(f"        {c(C.CY, '↪')}  {t('run.project.plan_fallback', use=' → '.join(fb.use), triggers='; '.join(triggers))}")
        for lp in plan.thread.loops:
            pause = f", {t('run.project.loop_pause', seconds=_fmt_seconds(lp.delay_seconds))}" if lp.delay_seconds else ""
            click.echo(f"  {c(C.CY, '↻')}  {t('run.project.plan_loop', start=lp.to, end=lp.from_, times=lp.times)}{pause}")
        for wmsg in plan.warnings:
            click.echo(f"  {c(C.YL, '⚠')}  {wmsg}")
        click.echo()
        success_box(t("run.project.dry_run_done"))
        return 0

    def on_event(kind, data):
        if kind == "stage":
            click.echo(f"\n  {c(C.CY, t('run.project.stage', index=data['index'], total=data['total'], mode=data['stage'].mode))}")
            click.echo(c(C.DM, "  " + "─" * 56))
        elif kind == "inactive":
            click.echo(f"  {c(C.YL, '⏭')}  {t('run.project.inactive', name=data.name)}")
        elif kind == "not_run":
            click.echo(f"  {c(C.YL, '⏭')}  {t('run.project.not_run', name=data.name)}")
        elif kind == "start":
            it = f"  {c(C.DM, t('run.project.pass', iteration=data['iteration'], iterations=data['iterations']))}" \
                if data.get("iterations", 1) > 1 else ""
            click.echo(f"  {c(C.WH, '▶')}  {t('workflow.run.starting', name=c(C.CY, data['name']))}{it}")
        elif kind == "end":
            if data.result is not None:
                _print_workflow_steps(plan.workflows[data.name], data.result, indent="     ")
            if data.status == FAILED:
                click.echo(f"  {c(C.RD, '✗')}  {t('run.project.wf_failed', name=data.name, duration=f'{data.duration:.1f}', error=data.error or '')}")
            else:
                click.echo(f"  {c(C.GR, '✓')}  {t('run.project.wf_ok', name=data.name, duration=f'{data.duration:.1f}')}")
        elif kind == "loop":
            lp = data["loop"]
            pause = f" — {t('run.project.loop_pause', seconds=_fmt_seconds(data['seconds']))}" if data["seconds"] else ""
            click.echo(f"\n  {c(C.CY, '↻')}  {t('run.project.loop', start=lp.to, end=lp.from_, iteration=data['iteration'], iterations=data['iterations'])}{pause}")
        elif kind == "delay":
            click.echo(f"  {c(C.DM, '⏸')}  {c(C.DM, t('run.project.delay', seconds=_fmt_seconds(data['seconds'])))}")

    try:
        result = ProjectRunner(plan, env=env_name, params=params).run(on_event)
    except KeyboardInterrupt:
        click.echo(f"\n\n  {c(C.YL, '⚠  ' + t('run.interrupted'))}")
        return 130

    click.echo()
    ran = [r for r in result.runs if r.status not in (INACTIVE, NOT_RUN)]
    ok_count = sum(1 for r in ran if r.status != FAILED)
    if result.success:
        success_box(t("run.project.success", name=root.name, duration=f"{result.duration:.1f}",
                      ok=ok_count, total=len(ran)))
        return 0
    error_box(t("run.project.failure", name=root.name, duration=f"{result.duration:.1f}",
                failed=", ".join(r.name for r in result.failed)))
    return 1


def _run_validate_only(job_dir: Path, verbosity: int, job_files: dict[str, Path]) -> bool:
    """Validation sans exécution (dry-run).

    Retourne True si au moins une erreur de validation a été détectée,
    False si le job est valide.
    """
    has_error = False
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
                has_error = True
            continue
        ok(f"{c(C.WH, fname):<36} — {t('validate.present')}")

    click.echo()
    # Validation parsers
    errs_src = _validate_sources_yaml(job_files["sources"])
    errs_dst = _validate_destinations_yaml(job_files["destinations"])
    errs_trf = _validate_transform_yaml(job_files["transformations"])

    if errs_src or errs_dst or errs_trf:
        has_error = True

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

    # Cohérence pipeline.from / pipeline.to (même contrôle que `validate`)
    if job_files["pipeline"].exists():
        for level, text in _check_pipeline_refs(job_files):
            if level == "err":
                err_line(text)
                has_error = True
            elif level == "info":
                info(text)
            else:
                ok(text)

    return has_error


def _check_pipeline_refs(job_files: dict) -> list:
    """pipeline.yaml et ses renvois : [(niveau, texte)] (cf. workflow/jobcheck.py)."""
    from hydra_etl.workflow.jobcheck import pipeline_checks
    out = []
    for level, code, p in pipeline_checks(job_files):
        if code == "resolved":
            text = f"{c(C.WH, p['ref']):<36} — {t('validate.resolved', id=p['id'])}"
        elif code == "ref_param":
            text = f"{c(C.WH, p['ref']):<36} — {t('validate.pipeline_ref_param', value=p['value'])}"
        elif code == "from_missing":
            text = t("validate.pipeline_from_missing", from_id=p["id"])
        elif code == "to_missing":
            text = t("validate.pipeline_to_missing", to_id=p["id"])
        elif code == "ref_empty":
            text = t("validate.pipeline_ref_empty", ref=p["ref"])
        elif code == "invalid":
            text = t("validate.pipeline_invalid", field=p["field"], error=p["error"])
        elif code == "section_missing":
            text = t("validate.pipeline_section_missing")
        else:
            text = t("validate.coherence_error", error=p.get("error", ""))
        out.append((level, text))
    return out

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


_JOB_FILE_ALIASES = {
    "sources":         ("sources.yaml", "sources.yml"),
    "destinations":    ("destinations.yaml", "destinations.yml"),
    "pipeline":        ("pipeline.yaml", "pipeline.yml"),
    "transformations": ("transformations.yaml", "transformations.yml"),
}


def _has_job_files(folder: Path) -> bool:
    """Le dossier contient-il lui-même un job (sources + destinations + pipeline) ?
    transformations est facultatif."""
    return all(any((folder / n).is_file() for n in _JOB_FILE_ALIASES[k])
               for k in ("sources", "destinations", "pipeline"))


def _write_project_marker(root: Path) -> Path:
    """Crée `.hydra/project.json` — le marqueur de projet lu par Hydra Studio."""
    import json
    import uuid
    from datetime import datetime, timezone
    meta_dir = root / ".hydra"
    meta_dir.mkdir(parents=True, exist_ok=True)
    f = meta_dir / "project.json"
    f.write_text(json.dumps({
        "id": str(uuid.uuid4())[:8],
        "name": root.resolve().name,
        "description": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "conventions": {"data_dir": "Data", "output_dir": "outputs"},
        "workflows": [],
        "jobs": [],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return f


_PROJECT_PARAMETERS_YAML = """\
# Project parameters, available in every job and workflow as {{ param:NAME }}.
# Per-environment values go in environments/<env>.yaml (select with --env <env>).
# Example:
#   min_amount:
#     type: float
#     default: 50
#     description: Orders below this amount are dropped.
version: "1.0"
parameters: {}
"""


def _project_readme(name: str) -> str:
    return f"""\
# {name}

Hydra ETL project created with `hdrctl init`.

## Structure

| Path | Purpose |
|---|---|
| `.hydra/` | Project marker, Hydra Studio data, and `secrets` (git-ignored, see below) |
| `Data/` | Input data shared by the jobs |
| `environments/` | Parameter values per environment (`dev.yaml`, `prod.yaml`, ...) |
| `jobs/` | One folder per job: `sources.yaml`, `destinations.yaml`, `pipeline.yaml`, `transformations.yaml` |
| `outputs/` | Files produced by the jobs |
| `parameters.yaml` | Project parameters, used as `{{{{ param:NAME }}}}` |
| `scripts/` | Scripts called by workflow actions (python, bash, powershell) |
| `workflows/` | Workflows (`<name>.yaml`) and their execution order (`thread.yaml`) |

## Secrets

Put passwords and tokens in `.hydra/secrets`, one `name=value` per line, and use them as
`${{SECRET:name}}` in jobs and workflows. The file is listed in `.gitignore`. An environment variable
wins over it (`${{SECRET:db.password}}` first reads `DB_PASSWORD`), so CI or a vault can provide the
values without the file. To keep the file elsewhere: `HYDRA_SECRETS_FILE=<path>` or
`hdrctl run . --secrets-file <path>`.

## Commands

Run them from this folder.

```bash
hdrctl run . --dry-run        # validate the whole project, run nothing
hdrctl run .                  # run every workflow, in the order of workflows/thread.yaml
hdrctl run . --env prod       # same, with environments/prod.yaml
hdrctl run jobs/job1          # run one job alone
hdrctl workflow list          # workflows in thread order
hdrctl workflow add <name>    # new workflow, added at the end of workflows/thread.yaml
hdrctl workflow remove <name> # delete a workflow (its jobs are kept)
hdrctl job add <job> <workflow>       # new job, appended to a workflow
hdrctl job attach <job> <workflow> -p 1  # existing job, as the first step
hdrctl job detach <job> [<workflow>]  # take a job out of one workflow, or of all
hdrctl job list               # jobs, and the workflows that use them
```
"""


_WORKFLOW1_YAML = """\
version: "1.0"
workflow:
  name: workflow1
  description: "First workflow of the project"
  trigger:
    type: manual
  steps:
    - name: job1
      type: job
      job: ../jobs/job1
      depends_on: []
      on_failure: fail
"""


@cli.command("init", help=t("help.init.docstring"))
@_lang_option
@click.argument("path", default=".", type=click.Path())
@click.option("--template", "-t", default="csv",
              type=click.Choice(VALID_TEMPLATES, case_sensitive=False),
              show_default=True, help=t("help.init.template"))
@click.option("--quiet", "-q", is_flag=True, default=False, help=t("help.init.quiet"))
def cmd_init(path: str, template: str, quiet: bool) -> None:
    """Initialise un projet Hydra (dossier `.hydra`, workflow1, job1)."""
    print_banner()
    root = Path(path)

    if root.exists() and not root.is_dir():
        error_box(t("init.not_a_dir", path=path))
        sys.exit(1)

    existing = list(root.iterdir()) if root.is_dir() else []
    shown = root.resolve()

    # Déjà un projet : on ne touche à rien.
    if (root / ".hydra").is_dir():
        info(t("init.already_project", path=str(shown)))
        return

    # Dossier non vide.
    if existing:
        if _has_job_files(root):
            # Alternative 1 : un job existe déjà ici → on ajoute seulement `.hydra`.
            _write_project_marker(root)
            success_box(t("init.adopted", path=c(C.WH, str(shown))))
            click.echo()
            info(t("init.adopted_note"))
            click.echo()
            return
        error_box(t("init.not_empty", path=str(shown)))
        info(t("init.not_empty_hint"))
        sys.exit(1)

    # Alternative 2 : dossier absent ou vide → projet complet.
    if not quiet:
        click.echo(f"\n  {c(C.CY, t('init.creating'))}  {c(C.WH + C.BD, str(shown))}"
                   f"  {c(C.DM, f'[template: {template}]')}\n")

    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for sub in ("Data", "environments", "outputs", "scripts"):
        (root / sub).mkdir(exist_ok=True)
        created.append(f"{sub}/")

    for rel in create_job_structure(root / "jobs" / "job1", template, False):
        created.append(f"jobs/job1/{rel}")

    (root / "workflows").mkdir(exist_ok=True)
    (root / "workflows" / "workflow1.yaml").write_text(_WORKFLOW1_YAML, encoding="utf-8")
    created.append("workflows/workflow1.yaml")
    from hydra_etl.workflow.thread import THREAD_FILE, default_thread_yaml
    (root / "workflows" / THREAD_FILE).write_text(default_thread_yaml(["workflow1"]), encoding="utf-8")
    created.append(f"workflows/{THREAD_FILE}")

    (root / "parameters.yaml").write_text(_PROJECT_PARAMETERS_YAML, encoding="utf-8")
    created.append("parameters.yaml")
    (root / "README.md").write_text(_project_readme(root.resolve().name), encoding="utf-8")
    created.append("README.md")

    _write_project_marker(root)
    created.append(".hydra/project.json")
    from hydra_etl.internal.config.secrets import scaffold_secrets
    created.extend(scaffold_secrets(root))

    for fpath in created:
        ok(fpath)

    success_box(t("init.success", name=c(C.WH, root.resolve().name)))
    click.echo()
    info(t("init.next_steps"))
    steps = [t("init.step1", path=c(C.WH, str(root / "jobs" / "job1") + "/"))]
    if (root / "jobs" / "job1" / ".env.example").exists():
        steps.append(t("init.step2"))
    steps.append(t("init.step3", cmd=c(C.WH, f"hdrctl run {root} --dry-run")))
    steps.append(t("init.step4", cmd=c(C.WH, f"hdrctl run {root}")))
    for i, line in enumerate(steps, 1):
        info(f"  {i}. {line}")
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
        info(t("run.hint", cmd=c(C.WH, f"hdrctl run {path}")))
        sys.exit(0)
    else:
        error_box(t("test.errors"))
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Commande : validate
# ─────────────────────────────────────────────────────────────────────────────


_EXPR_UNCHECKED = object()


def _check_expr_syntax(expr: str):
    """Vérifie la syntaxe d'une expression filter/calculate sans l'évaluer.

    Utilise le pré-analyseur de pandas (backticks, `&`, `|`, `and`/`or`…),
    c'est-à-dire la même grammaire que `DataFrame.query` / `DataFrame.eval`
    au moment de l'exécution. Retourne None si la syntaxe est correcte,
    un message d'erreur sinon, ou _EXPR_UNCHECKED si l'analyseur pandas
    n'est pas disponible (on ne bloque jamais sur un doute).
    """
    import ast
    import tokenize
    try:
        from pandas.core.computation.expr import PandasExprVisitor
        from pandas.core.computation.scope import Scope
        preparse = PandasExprVisitor(Scope(level=0), "python", "pandas").preparser
    except Exception:
        return _EXPR_UNCHECKED
    try:
        ast.parse(preparse(expr), mode="eval")
    except SyntaxError as e:
        return e.msg
    except tokenize.TokenError:
        return "unbalanced brackets or quotes"
    except Exception as e:  # autre erreur du tokeniseur pandas
        return str(e) or type(e).__name__
    return None


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

    def fail(msg: str, where: str = "") -> None:
        """Affiche une erreur et la compte (le total final doit tout inclure)."""
        nonlocal all_ok
        err_line(msg)
        all_errs.append(f"{where}: {msg}" if where else msg)
        all_ok = False

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
                fail(f"{fname} — {t('validate.missing')}")
            continue

        ok(f"{c(C.WH, fname):<36} — {t('validate.present')}")

        if validator:
            errs = validator(fpath)
            if errs:
                err_line(fname)
                for e in errs:
                    fail(f"  → {e}", fname)
            else:
                ok(f"{c(C.WH, fname):<36} — {t('validate.pydantic_valid')}")

    # Pipeline cohérence (pipeline.yaml présent : sinon déjà compté MISSING)
    if job_files["pipeline"].exists():
        for level, text in _check_pipeline_refs(job_files):
            if level == "err":
                fail(text, "pipeline.yaml")
            elif level == "info":
                info(text)
            else:
                ok(text)

    # Mode strict — vérifications supplémentaires.
    # Les étapes sont lues via TransformParser (source de vérité du DSL) :
    # il accepte `steps:` à la racine comme `transformations: steps:`.
    if strict and job_files["transformations"].exists():
        section(t("validate.strict_section"))
        try:
            import yaml
            from hydra_etl.internal.parser.transform import TransformParser
            data  = yaml.safe_load(_read_yaml(job_files["transformations"]))
            steps = TransformParser().parse(data or {}).steps
        except Exception as e:
            # Déjà signalé par la validation Pydantic ci-dessus.
            fail(t("validate.strict_error", error=e), "transformations.yaml")
            steps = []

        ops = [s.op for s in steps]
        ok(f"{c(C.WH, t('validate.ops_recognized')):<36} — "
           f"{', '.join(ops) if ops else t('validate.ops_none')}")

        # Syntaxe des expressions filter/calculate (analyse seule, aucune évaluation).
        for idx, step in enumerate(steps, start=1):
            if step.op not in ("filter", "calculate"):
                continue
            pms  = step.params or {}
            expr = pms.get("expr", "")
            label = "filter.expr" if step.op == "filter" else f"calculate.{pms.get('column', '?')}"
            problem = _check_expr_syntax(expr)
            if problem is None:
                ok(f"{c(C.WH, label):<36} — '{expr[:40]}'")
            elif problem is _EXPR_UNCHECKED:
                info(f"{c(C.WH, label):<36} — {t('validate.expr_unchecked')}")
            else:
                msg = t("validate.expr_invalid", step=idx, op=step.op, expr=expr, error=problem)
                fail(msg, "transformations.yaml")

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

    # Racine d'un projet : ses jobs (jobs/*) et les workflows qui les utilisent.
    from hydra_etl.workflow.project import is_project_root
    if is_project_root(root) and not _has_job_files(root):
        _print_project_jobs(root)
        return

    click.echo(f"  {c(C.WH, t('list.header'))} {c(C.CY, str(root))}\n")
    click.echo(f"  {c(C.DM, '─' * 70)}")

    jobs = find_jobs(root)

    if not jobs:
        info(t("list.none_found"))
        info(t("list.create_hint", cmd=c(C.WH, "hdrctl init my_project")))
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
    info(t("list.summary", count=len(jobs), ok=c(C.GR, str(n_ok))))
    info(t("list.run_hint", cmd=c(C.WH, "hdrctl run <job>")))
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



# Nombre de lignes de sortie d'action affichees sous un step ; au-dela, un
# compteur renvoie vers les logs complets. Evite qu'un script bavard noie le
# resume du workflow.
_STEP_OUTPUT_MAX_LINES = 20


def _echo_step_output(step_result) -> None:
    """Affiche sous le step ce qu'une action script (python/bash/powershell)
    a ecrit sur stdout/stderr. Sans effet pour les autres types de steps."""
    lines = [ln for ln in getattr(step_result, "output", []) or [] if ln.strip()]
    if not lines:
        return
    for line in lines[:_STEP_OUTPUT_MAX_LINES]:
        click.echo(f"     {c(C.DM, '│')} {line}")
    extra = len(lines) - _STEP_OUTPUT_MAX_LINES
    if extra > 0:
        click.echo(f"     {c(C.DM, '│')} {c(C.DM, t('workflow.run.output_truncated', count=extra))}")

@cmd_workflow.command("run", help=t("help.workflow.run.docstring"))
@_lang_option
@click.argument("path", default="./workflow.yaml", metavar="NAME|PATH")
@click.option("--project", "project", default=None, metavar="PATH", help=t("help.workflow.project"))
@click.option("--secrets-file", "secrets_file", default=None, metavar="FILE",
              help=t("help.run.secrets_file"))
def cmd_workflow_run(path: str, project: Optional[str], secrets_file: Optional[str]) -> None:
    """Execute un workflow DAG."""
    from hydra_etl.workflow.parser import load_workflow, validate_workflow
    from hydra_etl.workflow.runner import WorkflowRunner

    print_banner()
    _use_secrets_file(secrets_file)
    wf_path = _resolve_workflow_arg(path, project)
    if not wf_path.exists():
        error_box(t("workflow.file_not_found", path=str(wf_path)))
        sys.exit(1)

    try:
        wf = load_workflow(wf_path)
    except ValueError as e:
        # Manifeste invalide : même message que `workflow validate`, sans trace Python.
        error_box(t("workflow.validate.failure", error=str(e)))
        sys.exit(1)
    info(t("workflow.run.starting", name=c(C.CY, wf.name)))
    click.echo(c(C.DM, "  " + "─" * 56))

    runner = WorkflowRunner(wf, base_dir=wf_path.parent)
    result = runner.run()

    click.echo()
    _print_workflow_steps(wf, result)

    click.echo()
    if result.success:
        ok_count = sum(1 for s in result.steps if s.success)
        success_box(t("workflow.run.success", name=wf.name, duration=f"{result.duration:.1f}", ok=ok_count, total=len(result.steps)))
    else:
        error_box(t("workflow.run.failure", name=wf.name, duration=f"{result.duration:.1f}", error=result.error))
        sys.exit(1)


@cmd_workflow.command("validate", help=t("help.workflow.validate.docstring"))
@_lang_option
@click.argument("path", default="./workflow.yaml", metavar="NAME|PATH")
@click.option("--project", "project", default=None, metavar="PATH", help=t("help.workflow.project"))
def cmd_workflow_validate(path: str, project: Optional[str]) -> None:
    """Valide un manifest workflow sans l'executer."""
    from hydra_etl.workflow.parser import validate_workflow

    wf_path = _resolve_workflow_arg(path, project)
    if not wf_path.exists():
        error_box(t("workflow.file_not_found", path=str(wf_path)))
        sys.exit(1)

    ok, msg = validate_workflow(wf_path)
    if ok:
        success_box(t("workflow.validate.success"))
    else:
        error_box(t("workflow.validate.failure", error=msg))
        sys.exit(1)


def _project_or_exit(project: Optional[str]) -> Path:
    """Racine du projet (--project, sinon le dossier courant et ses parents)."""
    from hydra_etl.workflow.project import ProjectError, require_project
    try:
        return require_project(project)
    except ProjectError:
        shown = Path(project).resolve() if project else Path.cwd()
        error_box(t("workflow.not_in_project", path=str(shown)))
        sys.exit(1)


def _project_error_exit(e) -> None:
    for i, msg in enumerate(e.errors):
        (error_box if i == 0 else err_line)(msg if i == 0 else f"  — {msg}")
    sys.exit(1)


def _resolve_workflow_arg(arg: str, project: Optional[str]) -> Path:
    """PATH d'un fichier workflow, ou NOM d'un workflow du projet
    (workflows/<nom>.yaml)."""
    p = Path(arg)
    if p.is_file():
        return p.resolve()
    if p.suffix in (".yaml", ".yml") or "/" in arg or "\\" in arg:
        if not project:
            return p.resolve()
    from hydra_etl.workflow.project import find_project_root, workflow_files
    root = find_project_root(Path(project)) if project else find_project_root(Path.cwd())
    if root is not None:
        f = workflow_files(root).get(p.stem if p.suffix in (".yaml", ".yml") else arg)
        if f is not None:
            return f.resolve()
    return p.resolve()


_project_option = click.option(
    "--project", "project", default=None, metavar="PATH",
    help=t("help.workflow.project"))


@cmd_workflow.command("add", help=t("help.workflow.add.docstring"))
@_lang_option
@click.argument("name", required=False)
@_project_option
@click.option("--fallback-for", "fallback_for", default=None, metavar="WORKFLOW",
              help=t("help.workflow.fallback_for"))
def cmd_workflow_add(name: Optional[str], project: Optional[str], fallback_for: Optional[str]) -> None:
    """Crée un workflow vide et l'inscrit en fin de thread (ou comme remplaçant)."""
    from hydra_etl.workflow.project import ProjectError, add_workflow
    root = _project_or_exit(project)
    try:
        name, path, thread = add_workflow(root, name, fallback_for=fallback_for)
    except ProjectError as e:
        _project_error_exit(e)
    rel = path.relative_to(root)
    success_box(t("workflow.add.success", name=name, path=str(rel)))
    stage = next((i for i, st in enumerate(thread.thread, 1)
                  if name in [w.name for w in st.workflows]), None)
    if stage is not None:
        info(t("workflow.add.thread", stage=stage, mode=thread.thread[stage - 1].mode))
    else:
        targets = [w.name for st in thread.thread for w in st.workflows
                   if w.fallback and name in w.fallback.use]
        info(t("workflow.add.fallback", targets=", ".join(targets)))
    here = Path.cwd().resolve() == root
    info(t("workflow.add.next", name=name, project="." if here else str(root)))
    click.echo()


@cmd_workflow.command("remove", help=t("help.workflow.remove.docstring"))
@_lang_option
@click.argument("name")
@_project_option
@click.option("-y", "--yes", is_flag=True, default=False, help=t("help.workflow.yes"))
def cmd_workflow_remove(name: str, project: Optional[str], yes: bool) -> None:
    """Supprime un workflow et son entrée du thread. Les jobs restent."""
    from hydra_etl.workflow.project import ProjectError, remove_workflow, workflow_files
    root = _project_or_exit(project)
    target = workflow_files(root).get(name.rsplit(".", 1)[0] if name.endswith((".yaml", ".yml")) else name)
    shown = str(target.relative_to(root)) if target else f"workflows/{name}.yaml"
    if not yes and not click.confirm(f"  {t('workflow.remove.confirm', path=shown, name=name)}", default=False):
        info(t("workflow.remove.cancelled"))
        return
    try:
        removed, in_thread = remove_workflow(root, name)
    except ProjectError as e:
        _project_error_exit(e)
    if removed is not None:
        ok(t("workflow.remove.file", path=str(removed.relative_to(root))))
    if in_thread:
        ok(t("workflow.remove.thread"))
    success_box(t("workflow.remove.success", name=name))


@cmd_workflow.command("list", help=t("help.workflow.list.docstring"))
@_lang_option
@click.argument("path", required=False, metavar="[PROJECT]")
@_project_option
def cmd_workflow_list(path: Optional[str], project: Optional[str]) -> None:
    """Liste les workflows d'un projet, dans l'ordre du thread."""
    from hydra_etl.workflow.project import find_project_root, list_workflows
    target = project or path
    start = Path(target) if target else Path.cwd()
    if not start.exists():
        error_box(t("dir.not_found", path=str(start.resolve())))
        sys.exit(1)
    root = find_project_root(start)
    if root is None:
        _legacy_workflow_list(start.resolve())
        return
    try:
        items, implicit = list_workflows(root)
    except ValueError as e:
        error_box(t("workflow.validate.failure", error=f"workflows/thread.yaml: {e}"))
        sys.exit(1)

    info(t("workflow.list.project", name=c(C.CY, root.name)) + f"  {c(C.DM, str(root))}")
    click.echo(c(C.DM, "  " + "─" * 56))
    if implicit:
        info(t("workflow.list.implicit"))
    if not items:
        info(t("workflow.list.none_found"))
        click.echo()
        return
    width = max(len(i.name) for i in items)
    for it in items:
        where = f"{it.stage}·{it.mode}" if it.stage else "—"
        if it.path is None:
            status = c(C.RD, "✗ " + t("workflow.list.missing"))
        elif it.error:
            status = c(C.RD, "✗ " + t("workflow.list.invalid", error=it.error))
        elif it.stage is None and it.fallback_of:
            status = c(C.CY, "↪ " + t("workflow.list.fallback_of", targets=", ".join(it.fallback_of)))
        elif it.stage is None:
            status = c(C.YL, "○ " + t("workflow.list.not_in_thread"))
        elif it.active:
            status = c(C.GR, "✓ " + t("workflow.list.active"))
        else:
            status = c(C.YL, "⏭ " + t("workflow.list.inactive"))
        steps = c(C.DM, t("workflow.list.steps", count=it.steps)) if it.steps is not None else ""
        click.echo(f"  {where:<14} {c(C.WH, it.name.ljust(width))}  {status}  {steps}")
    click.echo()
    info(t("workflow.list.summary", count=len([i for i in items if i.path is not None])))
    click.echo()


def _legacy_workflow_list(search_dir: Path) -> None:
    """Hors projet : recherche des fichiers workflow.yaml (ancien layout)."""
    from hydra_etl.workflow.parser import load_workflow
    workflows = sorted(search_dir.rglob("workflow.yaml"))
    info(t("workflow.list.header") + f"  {c(C.CY, str(search_dir))}")
    click.echo(c(C.DM, "  " + "─" * 56))
    if not workflows:
        info(t("workflow.list.none_found"))
        return
    for wf_path in workflows:
        try:
            wf = load_workflow(wf_path)
            click.echo(f"  {c(C.CY, wf.name):<30} {c(C.DM, str(wf_path.relative_to(search_dir)))}  "
                       f"{c(C.DM, t('workflow.list.steps', count=len(wf.steps)))}")
        except Exception:
            click.echo(f"  {c(C.RD, '?')} {wf_path.relative_to(search_dir)}")
    click.echo()
    info(t("workflow.list.summary", count=len(workflows)))
    click.echo()


# ─────────────────────────────────────────────────────────────────────────────
# Groupe de commandes : job
# ─────────────────────────────────────────────────────────────────────────────

@cli.group("job", invoke_without_command=False, help=t("help.job.docstring"))
@_lang_option
def cmd_job() -> None:
    """Groupe job."""
    pass


_position_option = click.option(
    "-p", "--position", "position", type=int, default=None, metavar="N",
    help=t("help.job.position"))


def _echo_attach(res) -> None:
    success_box(t("job.attach.success", job=res.step, workflow=res.workflow, position=res.position))
    if res.after:
        info(t("job.attach.after", step=res.after))
    else:
        info(t("job.attach.first"))
    if res.rewired:
        info(t("job.attach.rewired", step=res.rewired, job=res.step))
    if res.not_rewired:
        click.echo(f"  {c(C.YL, '⚠')}  {t('job.attach.not_rewired', step=res.not_rewired, job=res.step)}")


def _echo_next(root: Path) -> None:
    here = Path.cwd().resolve() == root
    info(t("job.next", project="." if here else str(root)))
    click.echo()


def _print_project_jobs(root: Path) -> None:
    """Jobs d'un projet : état des fichiers et workflows qui les utilisent."""
    from hydra_etl.workflow.jobs import jobs_overview
    items = jobs_overview(root)
    info(t("job.list.title", name=c(C.CY, root.name)) + f"  {c(C.DM, str(root))}")
    click.echo(c(C.DM, "  " + "─" * 56))
    if not items:
        info(t("job.list.none"))
        click.echo()
        return
    width = max(len(i.name) for i in items)
    for it in items:
        wfs = ", ".join(sorted({w for w, _ in it.used_by}))
        if not it.exists:
            status = c(C.RD, "✗ " + t("job.list.missing_folder", workflows=wfs))
        elif it.missing:
            status = c(C.RD, "✗ " + t("job.list.incomplete", files=", ".join(it.missing)))
            if wfs:
                status += c(C.DM, "  " + t("job.list.used_by", workflows=wfs))
        elif wfs:
            status = c(C.GR, "✓ ") + t("job.list.used_by", workflows=wfs)
        else:
            status = c(C.YL, "○ " + t("job.list.free"))
        click.echo(f"  {c(C.WH, it.name.ljust(width))}  {status}")
    click.echo()
    free = sum(1 for i in items if i.exists and not i.missing and not i.used_by)
    info(t("job.list.summary", count=sum(1 for i in items if i.exists), free=free))
    info(t("job.list.run_hint"))
    click.echo()


@cmd_job.command("list", help=t("help.job.list.docstring"))
@_lang_option
@click.argument("path", required=False, metavar="[PROJECT]")
@_project_option
def cmd_job_list(path: Optional[str], project: Optional[str]) -> None:
    """Liste les jobs du projet et les workflows qui les utilisent."""
    root = _project_or_exit(project or path)
    _print_project_jobs(root)


@cmd_job.command("add", help=t("help.job.add.docstring"))
@_lang_option
@click.argument("name")
@click.argument("workflow", required=False)
@_position_option
@click.option("--template", "-t", default="csv",
              type=click.Choice(VALID_TEMPLATES, case_sensitive=False),
              show_default=True, help=t("help.init.template"))
@_project_option
def cmd_job_add(name: str, workflow: Optional[str], position: Optional[int],
                template: str, project: Optional[str]) -> None:
    """Crée jobs/<NAME>/ et, si WORKFLOW est donné, l'y attache."""
    from hydra_etl.workflow.jobs import (_load_doc, _workflow_file, attach_job, check_job_name,
                                         create_job)
    from hydra_etl.workflow.project import ProjectError
    root = _project_or_exit(project)
    if position is not None and not workflow:
        error_box(t("job.position_needs_workflow"))
        sys.exit(1)
    try:
        name = check_job_name(name)
        # Tout vérifier AVANT de créer quoi que ce soit.
        if workflow:
            n = len(_load_doc(_workflow_file(root, workflow))["workflow"]["steps"])
            if position is not None and not 1 <= position <= n + 1:
                raise ProjectError([f"position {position} is out of range: workflow '{workflow}' "
                                    f"has {n} step(s), use 1 to {n + 1}"])
        target, created = create_job(root, name, template)
    except ProjectError as e:
        _project_error_exit(e)
    for f in created:
        ok(f"jobs/{name}/{f}")
    success_box(t("job.add.success", name=name, path=str(target.relative_to(root))))
    if workflow:
        try:
            _echo_attach(attach_job(root, name, workflow, position))
        except ProjectError as e:
            _project_error_exit(e)
    else:
        info(t("job.add.free", name=name))
    _echo_next(root)


@cmd_job.command("attach", help=t("help.job.attach.docstring"))
@_lang_option
@click.argument("name")
@click.argument("workflow")
@_position_option
@_project_option
def cmd_job_attach(name: str, workflow: str, position: Optional[int], project: Optional[str]) -> None:
    """Attache un job existant à un workflow."""
    from hydra_etl.workflow.jobs import attach_job
    from hydra_etl.workflow.project import ProjectError
    root = _project_or_exit(project)
    try:
        res = attach_job(root, name, workflow, position)
    except ProjectError as e:
        _project_error_exit(e)
    _echo_attach(res)
    _echo_next(root)


@cmd_job.command("detach", help=t("help.job.detach.docstring"))
@_lang_option
@click.argument("name")
@click.argument("workflow", required=False)
@_project_option
def cmd_job_detach(name: str, workflow: Optional[str], project: Optional[str]) -> None:
    """Détache un job d'un workflow, ou de tous."""
    from hydra_etl.workflow.jobs import detach_job, job_path, job_usage
    from hydra_etl.workflow.project import ProjectError
    root = _project_or_exit(project)
    usage = job_usage(root, name)
    if not usage and not job_path(root, name).is_dir():
        error_box(t("job.not_found", name=name, path=str(job_path(root, name).relative_to(root))))
        sys.exit(1)
    try:
        results = detach_job(root, name, workflow)
    except ProjectError as e:
        _project_error_exit(e)
    if not results:
        if workflow and usage:
            info(t("job.detach.not_in", job=name, workflow=workflow, others=", ".join(usage)))
        else:
            info(t("job.detach.free", job=name))
        return
    for r in results:
        ok(t("job.detach.success", job=name, workflow=r.workflow, steps=", ".join(r.steps)))
        for step, deps in r.rewired.items():
            info(t("job.detach.rewired", step=step, deps=", ".join(deps) if deps else "—"))
    left = job_usage(root, name)
    if not left:
        info(t("job.detach.now_free", job=name))
    click.echo()


@cli.command("serve", help="Start the Hydra API and the Studio.")
@_lang_option
@click.option("--host", default="127.0.0.1", show_default=True, help="Listen address.")
@click.option("--port", default=5678, show_default=True, type=int, help="Listen port.")
@click.option("--reload", is_flag=True, default=False, help="Hot reload (development only).")
@click.option("--open", "open_browser", is_flag=True, default=False,
              help="Open the Studio in your browser once the server is up.")
@click.option("--no-studio", is_flag=True, default=False,
              help="Serve the API only, without the visual editor.")
@click.option("--workspace", default=None, envvar="HYDRA_WORKSPACE",
              help="Root folder for Studio projects (default: ~/hydra-workspace).")
def cmd_serve(host: str, port: int, reload: bool, open_browser: bool,
              no_studio: bool, workspace: Optional[str]) -> None:
    """Start the Hydra API, and the Studio bundled with it."""
    try:
        import uvicorn
    except ImportError:
        click.echo("uvicorn is not installed. Run: pip install \"hydra-etl[server]\"", err=True)
        sys.exit(1)

    import os

    # Le répertoire courant de l'utilisateur est conservé : les chemins relatifs
    # des manifestes se résolvent depuis l'endroit d'où la commande est lancée.
    # (Un `os.chdir` vers le paquet installé écrirait dans site-packages.)
    if workspace:
        os.environ["HYDRA_WORKSPACE"] = workspace
    if no_studio:
        os.environ["HYDRA_NO_STUDIO"] = "1"

    from hydra_etl.api.studio import studio_is_bundled
    serving_studio = studio_is_bundled() and not no_studio

    print_banner()

    # L'adresse du Studio est l'information que l'utilisateur vient chercher :
    # elle est mise en avant, seule, avec une consigne explicite. Les autres
    # adresses viennent ensuite, en retrait.
    url = f"http://{host}:{port}"
    if serving_studio:
        click.echo(f"  {c(C.BD + C.GR, 'Hydra Studio is ready.')} "
                   f"{c(C.WH, 'Open this address in your browser:')}")
        click.echo()
        click.echo(f"      {c(C.BD + C.CY, url)}")
        click.echo()
    elif no_studio:
        click.echo(f"  {c(C.YL, 'Studio disabled')} — started with --no-studio")
        click.echo()
    else:
        click.echo(f"  {c(C.YL, 'Studio not bundled')} — open {url} to see how to build it")
        click.echo()

    click.echo(f"  {c(C.DM, 'API')}       {url}/api")
    click.echo(f"  {c(C.DM, 'Docs')}      {url}/docs")
    click.echo(f"  {c(C.DM, 'Workdir')}   {Path.cwd()}")
    click.echo()
    click.echo(f"  {c(C.DM, 'Press CTRL+C to stop.')}")
    click.echo()

    if open_browser:
        import threading
        import webbrowser
        url = f"http://{host}:{port}"
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    uvicorn.run(
        "hydra_etl.api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
