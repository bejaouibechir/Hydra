"""
internal/config/env_admin.py — Gestion des environnements, des variables
globales, des paramètres et des secrets (CLI `hdrctl env|param|secret`, API).

Où vivent les données :
  ~/.hydra/env                     variables globales communes (tous les projets)
  ~/.hydra/env.<env>               variables globales propres à un environnement
  <projet>/parameters.yaml         déclarations + valeurs par défaut
  <projet>/environments/<env>.yaml valeurs des paramètres pour <env>
  <projet>/.hydra/secrets          secrets communs (ou HYDRA_SECRETS_FILE)
  <projet>/.hydra/secrets.<env>    secrets propres à <env>

Les écritures sont atomiques. Avant une suppression ou un renommage, les
fichiers touchés sont copiés dans ~/.hydra/_backups/<horodatage>/.
"""
from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from hydra_etl.internal.config.loader import (
    check_env_name, global_env_file, global_env_names, hydra_home, parse_env_file,
)
from hydra_etl.internal.fs_atomic import atomic_write_text

VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PARAM_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
PARAM_TYPES = ("string", "int", "float", "bool", "json", "any")


class EnvAdminError(ValueError):
    """Erreur de gestion (nom invalide, élément absent, conflit…)."""


# ----------------------------------------------------------------------
# Outils
# ----------------------------------------------------------------------

def _env_name(name: str) -> str:
    try:
        return check_env_name(name)
    except ValueError as e:
        raise EnvAdminError(str(e)) from None


def check_var_name(name: str) -> str:
    n = (name or "").strip()
    if not VAR_NAME_RE.match(n):
        raise EnvAdminError(
            f"invalid variable name '{name}': use letters, digits and '_' (not starting with a digit)")
    return n


def _format_env_value(value: str) -> str:
    value = str(value)
    if "\n" in value or "\r" in value:
        raise EnvAdminError("a value cannot contain a line break")
    if value != value.strip() or value[:1] in ("'", '"', "#") or " #" in value:
        q = "'" if '"' in value else '"'
        return f"{q}{value}{q}"
    return value


def _key_of(line: str) -> Optional[str]:
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    if s.startswith("export "):
        s = s[7:].lstrip()
    return s.split("=", 1)[0].strip()


def backup_files(paths: List[Path], label: str) -> Optional[Path]:
    """Copie les fichiers existants dans ~/.hydra/_backups/<ts>-<label>/."""
    existing = [Path(p) for p in paths if Path(p).is_file()]
    if not existing:
        return None
    dest = hydra_home() / "_backups" / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}"
    dest.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(existing):
        target = dest / p.name
        if target.exists():
            target = dest / f"{i}-{p.name}"
        shutil.copy2(p, target)
    return dest


# ----------------------------------------------------------------------
# Variables globales (~/.hydra/env, ~/.hydra/env.<env>)
# ----------------------------------------------------------------------

GLOBAL_HEADER = (
    "# Hydra global environment variables{scope}.\n"
    "# Shared by every project on this machine. One KEY=VALUE per line.\n"
    "# Order: env < env.<environment> < project .env < job .env < --env-file\n"
)


def global_vars(env: Optional[str] = None) -> Dict[str, str]:
    return parse_env_file(global_env_file(_env_name(env) if env else None))


def set_global_var(env: Optional[str], key: str, value: str) -> Path:
    key = check_var_name(key)
    path = global_env_file(_env_name(env) if env else None)
    if path.is_file():
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    else:
        lines = GLOBAL_HEADER.format(scope=f" for '{env}'" if env else " (all environments)").splitlines()
    new = f"{key}={_format_env_value(value)}"
    for i, ln in enumerate(lines):
        if _key_of(ln) == key:
            lines[i] = new
            break
    else:
        lines.append(new)
    atomic_write_text(path, "\n".join(lines) + "\n")
    return path


def unset_global_var(env: Optional[str], key: str) -> bool:
    path = global_env_file(_env_name(env) if env else None)
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    kept = [ln for ln in lines if _key_of(ln) != key]
    if len(kept) == len(lines):
        return False
    atomic_write_text(path, "\n".join(kept) + ("\n" if kept else ""))
    return True


# ----------------------------------------------------------------------
# Environnements
# ----------------------------------------------------------------------

@dataclass
class EnvInfo:
    name: str
    global_file: bool = False          # ~/.hydra/env.<name> existe
    global_vars: int = 0
    project_file: bool = False         # environments/<name>.yaml existe
    params: int = 0
    secrets_file: bool = False         # .hydra/secrets.<name> existe
    secrets: int = 0


def project_env_names(root: Optional[Path]) -> List[str]:
    if not root:
        return []
    d = Path(root) / "environments"
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.yaml") if p.is_file())


def _env_files(root: Optional[Path], name: str) -> Dict[str, Path]:
    files = {"global": global_env_file(name)}
    if root:
        files["project"] = Path(root) / "environments" / f"{name}.yaml"
        files["secrets"] = Path(root) / ".hydra" / f"secrets.{name}"
    return files


def list_environments(root: Optional[Path] = None) -> List[EnvInfo]:
    names = sorted(set(global_env_names()) | set(project_env_names(root))
                   | set(_secret_env_names(root)))
    out: List[EnvInfo] = []
    for n in names:
        try:
            _env_name(n)
        except EnvAdminError:
            continue
        f = _env_files(root, n)
        info = EnvInfo(name=n)
        if f["global"].is_file():
            info.global_file = True
            info.global_vars = len(parse_env_file(f["global"]))
        if root and f["project"].is_file():
            info.project_file = True
            info.params = len(_read_block(f["project"]))
        if root and f["secrets"].is_file():
            info.secrets_file = True
            try:
                info.secrets = len(_secret_names(f["secrets"]))
            except Exception:
                info.secrets = 0
        out.append(info)
    return out


def create_environment(name: str, root: Optional[Path] = None,
                       global_only: bool = False) -> List[Path]:
    """Crée ~/.hydra/env.<name> et, dans un projet, environments/<name>.yaml."""
    name = _env_name(name)
    created: List[Path] = []
    g = global_env_file(name)
    if not g.exists():
        atomic_write_text(g, GLOBAL_HEADER.format(scope=f" for '{name}'"))
        created.append(g)
    if root and not global_only:
        p = Path(root) / "environments" / f"{name}.yaml"
        if not p.exists():
            atomic_write_text(p, yaml.safe_dump({"parameters": {}}, sort_keys=False))
            created.append(p)
    if not created:
        raise EnvAdminError(f"environment '{name}' already exists")
    return created


def rename_environment(old: str, new: str, root: Optional[Path] = None) -> List[Tuple[Path, Path]]:
    old, new = _env_name(old), _env_name(new)
    if old == new:
        raise EnvAdminError("the new name is the same as the old one")
    src, dst = _env_files(root, old), _env_files(root, new)
    moves = [(src[k], dst[k]) for k in src if src[k].is_file()]
    if not moves:
        raise EnvAdminError(f"environment '{old}' not found")
    clash = [d for _, d in moves if d.exists()]
    if clash:
        raise EnvAdminError(f"environment '{new}' already exists ({clash[0]})")
    backup_files([s for s, _ in moves], f"rename-{old}")
    for s, d in moves:
        d.parent.mkdir(parents=True, exist_ok=True)
        s.replace(d)
    return moves


def delete_environment(name: str, root: Optional[Path] = None,
                       keep_secrets: bool = False) -> Tuple[List[Path], Optional[Path]]:
    """Supprime les fichiers de l'environnement (sauvegardés avant)."""
    name = _env_name(name)
    f = _env_files(root, name)
    if keep_secrets:
        f.pop("secrets", None)
    paths = [p for p in f.values() if p.is_file()]
    if not paths:
        raise EnvAdminError(f"environment '{name}' not found")
    saved = backup_files(paths, f"delete-{name}")
    for p in paths:
        p.unlink()
    return paths, saved


# ----------------------------------------------------------------------
# Paramètres
# ----------------------------------------------------------------------

def _load_yaml(path: Path) -> Any:
    if not path.is_file():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except yaml.YAMLError as e:
        raise EnvAdminError(f"{path}: invalid YAML: {e}") from None


def _read_block(path: Path) -> Dict[str, Any]:
    data = _load_yaml(path)
    if isinstance(data, dict):
        block = data.get("parameters", data)
        return dict(block) if isinstance(block, dict) else {}
    return {}


def _write_block(path: Path, block: Dict[str, Any]) -> None:
    data = _load_yaml(path)
    if isinstance(data, dict) and "parameters" not in data and data:
        data = {"parameters": block}            # ancien format à plat
    elif not isinstance(data, dict):
        data = {}
    data["parameters"] = block
    atomic_write_text(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


@dataclass
class ParamsView:
    declarations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    environments: Dict[str, Dict[str, Any]] = field(default_factory=dict)


def read_parameters(root: Path) -> ParamsView:
    view = ParamsView()
    for k, v in _read_block(Path(root) / "parameters.yaml").items():
        view.declarations[k] = v if isinstance(v, dict) else {"default": v}
    for n in project_env_names(root):
        view.environments[n] = _read_block(Path(root) / "environments" / f"{n}.yaml")
    return view


def check_param_name(name: str) -> str:
    n = (name or "").strip()
    if not PARAM_NAME_RE.match(n):
        raise EnvAdminError(f"invalid parameter name '{name}': use letters, digits, '.', '_' or '-'")
    return n


def parse_cli_value(raw: str, typ: Optional[str] = None, name: str = "") -> Any:
    """'100' -> 100, 'true' -> True… ; avec un type déclaré, conversion stricte."""
    from hydra_etl.internal.config.parameters import ParameterError, coerce_value
    if typ and typ not in ("any",):
        try:
            return coerce_value(raw, typ, "")
        except ParameterError:
            raise EnvAdminError(f"parameter '{name}': '{raw}' is not a valid {typ}") from None
    try:
        v = yaml.safe_load(raw)
    except yaml.YAMLError:
        return raw
    return v if isinstance(v, (int, float, bool, str, list, dict)) or v is None else raw


def _infer_type(v: Any) -> str:
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, (list, dict)):
        return "json"
    return "string"


def set_parameter(root: Path, name: str, raw_value: Optional[str], env: Optional[str] = None, *,
                  typ: Optional[str] = None, description: Optional[str] = None,
                  required: Optional[bool] = None) -> Path:
    """Sans env : déclaration/défaut dans parameters.yaml. Avec env : valeur
    dans environments/<env>.yaml."""
    name = check_param_name(name)
    if typ is not None and typ not in PARAM_TYPES:
        raise EnvAdminError(f"invalid type '{typ}': {', '.join(PARAM_TYPES)}")
    root = Path(root)
    decl_path = root / "parameters.yaml"
    decls = _read_block(decl_path)
    decl = decls.get(name)
    decl = dict(decl) if isinstance(decl, dict) else ({"default": decl} if decl is not None else None)
    declared_type = typ or (decl or {}).get("type")
    if env:
        env = _env_name(env)
        if raw_value is None:
            raise EnvAdminError("a value is required with --env")
        value = parse_cli_value(raw_value, declared_type, name)
        path = root / "environments" / f"{env}.yaml"
        block = _read_block(path)
        block[name] = value
        _write_block(path, block)
        if decl is None or typ or description is not None or required is not None:
            d = decl or {"type": typ or _infer_type(value)}
            if typ:
                d["type"] = typ
            if description is not None:
                d["description"] = description
            if required is not None:
                d["required"] = required
            decls[name] = d
            _write_block(decl_path, decls)
        return path
    d = decl or {}
    if typ:
        d["type"] = typ
    if raw_value is not None:
        value = parse_cli_value(raw_value, declared_type, name)
        d["default"] = value
        d.setdefault("type", _infer_type(value))
    else:
        d.setdefault("type", "string")
    if description is not None:
        d["description"] = description
    if required is not None:
        d["required"] = required
    # ordre lisible : type, default, required, description
    ordered = {k: d[k] for k in ("type", "default", "required", "description") if k in d}
    ordered.update({k: v for k, v in d.items() if k not in ordered})
    decls[name] = ordered
    _write_block(decl_path, decls)
    return decl_path


def unset_parameter(root: Path, name: str, env: Optional[str] = None) -> List[Path]:
    """Avec env : retire la valeur de cet environnement. Sans env : retire la
    déclaration et les valeurs de tous les environnements."""
    root = Path(root)
    targets = [root / "environments" / f"{_env_name(env)}.yaml"] if env else \
        [root / "parameters.yaml"] + [root / "environments" / f"{n}.yaml" for n in project_env_names(root)]
    changed: List[Path] = []
    for p in targets:
        block = _read_block(p)
        if name in block:
            block.pop(name)
            _write_block(p, block)
            changed.append(p)
    if not changed:
        raise EnvAdminError(f"parameter '{name}' not found" + (f" in environment '{env}'" if env else ""))
    return changed


# ----------------------------------------------------------------------
# Secrets (noms seulement — les valeurs ne sortent jamais)
# ----------------------------------------------------------------------

def _secret_env_names(root: Optional[Path]) -> List[str]:
    if not root:
        return []
    d = Path(root) / ".hydra"
    if not d.is_dir():
        return []
    out = []
    for p in d.glob("secrets.*"):
        suffix = p.name[len("secrets."):]
        if p.is_file() and "." not in suffix and suffix not in ("yaml", "yml"):
            out.append(suffix)
    return sorted(out)


def _secret_names(path: Path) -> List[str]:
    from hydra_etl.internal.config.secrets import load_secrets_file
    return list(load_secrets_file(path))


def secrets_path(root: Path, env: Optional[str] = None) -> Path:
    from hydra_etl.internal.config.secrets import env_secrets_file, secrets_file_for
    return env_secrets_file(root, _env_name(env)) if env else secrets_file_for(root)


@dataclass
class SecretEntry:
    name: str
    scope: str                      # "common" ou le nom de l'environnement
    overridden_by: Optional[str] = None


def list_secrets(root: Path, env: Optional[str] = None) -> List[SecretEntry]:
    from hydra_etl.internal.config.secrets import env_override
    out: List[SecretEntry] = []
    common = secrets_path(root)
    names_env: List[str] = []
    if env:
        pe = secrets_path(root, env)
        if pe.is_file():
            names_env = _secret_names(pe)
    if common.is_file():
        for n in _secret_names(common):
            if n not in names_env:
                out.append(SecretEntry(n, "common", env_override(n)))
    for n in names_env:
        out.append(SecretEntry(n, env, env_override(n)))      # type: ignore[arg-type]
    return sorted(out, key=lambda e: e.name)


def set_secret_value(root: Path, name: str, value: str, env: Optional[str] = None) -> Path:
    from hydra_etl.internal.config.secrets import SecretResolutionError, set_secret
    path = secrets_path(root, env)
    try:
        set_secret(path, name, value)
    except SecretResolutionError as e:
        raise EnvAdminError(str(e)) from None
    return path


def delete_secret_value(root: Path, name: str, env: Optional[str] = None) -> Path:
    from hydra_etl.internal.config.secrets import SecretResolutionError, delete_secret
    path = secrets_path(root, env)
    try:
        if not delete_secret(path, name):
            raise EnvAdminError(f"secret '{name}' not found in {path.name}")
    except SecretResolutionError as e:
        raise EnvAdminError(str(e)) from None
    return path


def replace_global_vars(env: Optional[str], values: Dict[str, str]) -> Path:
    """Remplace toutes les variables du fichier (commentaires conservés en tête)."""
    for k in values:
        check_var_name(k)
    path = global_env_file(_env_name(env) if env else None)
    if path.is_file():
        head = [ln for ln in path.read_text(encoding="utf-8-sig").splitlines()
                if ln.strip().startswith("#") or not ln.strip()]
    else:
        head = GLOBAL_HEADER.format(scope=f" for '{env}'" if env else " (all environments)").splitlines()
    while head and not head[-1].strip():
        head.pop()
    lines = head + [f"{k}={_format_env_value(v)}" for k, v in values.items()]
    atomic_write_text(path, "\n".join(lines) + "\n")
    return path
