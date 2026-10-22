"""
Résolution de variables et secrets dans la config (MVP).

Ce module fait uniquement 2 choses :
1) Remplacer ${ENV:VAR_NAME}  -> valeur de variable d'environnement
2) Remplacer ${SECRET:KEY}    -> valeur depuis un dictionnaire secrets fourni

Pourquoi ce design ?
- Le parser doit recevoir une config "résolue" avant validation Pydantic.
- On évite de mélanger la logique de lecture des fichiers (loader) avec la logique
  de substitution (resolver).
- On garde la porte ouverte à des resolvers chaînés (Vault/AWS/Azure) plus tard.

Règles MVP :
- Si une variable/secret est manquant -> exception explicite.
- Substitution récursive sur dict / list / str.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


# Regex stricte :
# - ${ENV:XXX}
# - ${SECRET:xxx.yyy}
_PLACEHOLDER_RE = re.compile(r"\$\{(ENV|SECRET):([A-Za-z0-9_.-]+)\}")


class SecretResolutionError(ValueError):
    """
    Erreur levée quand une substitution échoue (env ou secret manquant).
    """
    pass


@dataclass(frozen=True)
class SecretResolver:
    """
    Resolver MVP.

    - secrets : dictionnaire (clé -> valeur) injecté
      Exemple:
        {
          "db.password": "p@ss",
          "api.token": "xxx"
        }
    """

    secrets: Mapping[str, Any]
    # Secrets du fichier du projet (.hydra/secrets ou HYDRA_SECRETS_FILE) :
    # consultés EN DERNIER, une variable d'environnement l'emporte.
    fallback: Mapping[str, Any] = field(default_factory=dict)

    def resolve(self, data: Any) -> Any:
        """
        Résout récursivement les placeholders dans une structure Python issue du YAML.
        """
        if isinstance(data, dict):
            return {k: self.resolve(v) for k, v in data.items()}

        if isinstance(data, list):
            return [self.resolve(v) for v in data]

        if isinstance(data, str):
            return self._resolve_string(data)

        # Types non concernés : int/float/bool/None...
        return data

    def _resolve_string(self, value: str) -> str:
        """
        Résout les placeholders dans une chaîne.

        Cas gérés :
        - chaîne entière = placeholder => on remplace
        - placeholder intégré dans une chaîne => remplacement partiel

        Exemple :
        "mysql://${ENV:DB_HOST}:3306" -> "mysql://localhost:3306"
        """
        def repl(match: re.Match[str]) -> str:
            kind = match.group(1)
            key = match.group(2)

            if kind == "ENV":
                return self._get_env(key)

            if kind == "SECRET":
                return self._get_secret(key)

            # Théoriquement impossible avec la regex actuelle
            raise SecretResolutionError(f"Type de placeholder inconnu: {kind}")

        # Remplacement global dans la chaîne
        return _PLACEHOLDER_RE.sub(repl, value)

    def _get_env(self, key: str) -> str:
        """
        Récupère une variable d'environnement obligatoire.
        """
        if key not in os.environ:
            raise SecretResolutionError(f"Missing environment variable: {key}")
        return os.environ[key]

    @staticmethod
    def _env_name(key: str) -> str:
        """
        Nom de variable d'environnement correspondant a une cle de secret.

        'db.password' et 'db-password' donnent tous deux 'DB_PASSWORD'.
        Une cle deja en majuscules ('DB_PASSWORD') est inchangee.
        """
        return re.sub(r"[.\-]", "_", key).upper()

    def _get_secret(self, key: str) -> str:
        """
        Recupere un secret obligatoire, cherche dans cet ordre :

        1) le mapping 'secrets' injecte (coffre applicatif, Vault, AWS...) ;
        2) la variable d'environnement correspondante, normalisee
           ('db.password' -> 'DB_PASSWORD') ;
        3) la variable d'environnement portant exactement le nom de la cle ;
        4) le fichier de secrets du projet (`fallback`) : .hydra/secrets, ou le
           fichier désigné par HYDRA_SECRETS_FILE / --secrets-file.

        L'environnement (CI, coffre-fort, shell, .env) l'emporte donc sur le
        fichier : le fichier sert en local, sans rien changer en production.
        """
        if key in self.secrets:
            return str(self.secrets[key])

        env_name = self._env_name(key)
        if env_name in os.environ:
            return os.environ[env_name]

        if key in os.environ:
            return os.environ[key]

        if key in self.fallback:
            return str(self.fallback[key])
        if env_name in self.fallback:
            return str(self.fallback[env_name])

        raise SecretResolutionError(
            f"Missing secret: {key} — not in the environment ({env_name}) "
            f"nor in the project secrets file (.hydra/secrets or {SECRETS_FILE_ENV})"
        )


# ---------------------------------------------------------------------------
# Fichier de secrets du projet
# ---------------------------------------------------------------------------

SECRETS_FILE_ENV = "HYDRA_SECRETS_FILE"
PROJECT_SECRETS_FILE = Path(".hydra") / "secrets"
_SECRET_KEY_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")

SECRETS_TEMPLATE = """\
# Project secrets, read by ${SECRET:name} in jobs and workflows.
# One per line: name=value. Lines starting with # are ignored.
# This file is listed in .gitignore: never commit it.
# An environment variable wins over this file: ${SECRET:db.password} first
# reads DB_PASSWORD from the environment (CI, vault, shell, .env).
# To keep the secrets elsewhere, set HYDRA_SECRETS_FILE=<path> or pass
# --secrets-file <path> to hdrctl run.
#
# db.password=change-me
"""

GITIGNORE_LINES = ("# Hydra: never commit secrets", ".hydra/secrets", ".env")


def parse_secrets_text(text: str, source: str = "secrets") -> Dict[str, str]:
    """`name=value` par ligne ; `#` commente ; guillemets autour de la valeur
    retirés. Les erreurs citent la ligne, jamais la valeur."""
    out: Dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise SecretResolutionError(f"{source}, line {lineno}: expected name=value")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not _SECRET_KEY_RE.match(key):
            raise SecretResolutionError(f"{source}, line {lineno}: invalid secret name '{key}'")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        out[key] = value
    return out


def load_secrets_file(path: Path) -> Dict[str, str]:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise SecretResolutionError(f"cannot read secrets file {path}: {e}") from None
    return parse_secrets_text(text, str(path))


def _project_root(start: Path) -> Optional[Path]:
    d = Path(start).resolve()
    for _ in range(7):
        if (d / ".hydra").is_dir():
            return d
        if d.parent == d:
            return None
        d = d.parent
    return None


def project_secrets(*anchors: Optional[Path]) -> Dict[str, str]:
    """Secrets du fichier du projet. HYDRA_SECRETS_FILE (ou --secrets-file)
    désigne un fichier hors du projet ; sinon .hydra/secrets du projet qui
    contient le premier `anchor` trouvé. Pas de fichier : {}."""
    explicit = os.environ.get(SECRETS_FILE_ENV)
    if explicit:
        f = Path(explicit).expanduser()
        if not f.is_file():
            raise SecretResolutionError(f"secrets file not found: {f} (set by {SECRETS_FILE_ENV})")
        return load_secrets_file(f)
    for a in anchors:
        if a is None:
            continue
        root = _project_root(Path(a))
        if root is not None:
            f = root / PROJECT_SECRETS_FILE
            return load_secrets_file(f) if f.is_file() else {}
    return {}


def scaffold_secrets(root: Path) -> list:
    """Crée .hydra/secrets (modèle commenté) et ajoute les lignes de
    GITIGNORE_LINES au .gitignore du projet. N'écrase rien. Retourne les
    fichiers créés ou modifiés (chemins relatifs)."""
    root = Path(root)
    changed = []
    f = root / PROJECT_SECRETS_FILE
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(SECRETS_TEMPLATE, encoding="utf-8")
        changed.append(PROJECT_SECRETS_FILE.as_posix())
    gi = root / ".gitignore"
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.is_file() else []
    missing = [ln for ln in GITIGNORE_LINES if ln not in existing]
    if missing:
        text = "\n".join(existing + ([""] if existing and existing[-1] else []) + missing) + "\n"
        gi.write_text(text.lstrip("\n"), encoding="utf-8")
        changed.append(".gitignore")
    return changed
