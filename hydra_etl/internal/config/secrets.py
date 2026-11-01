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

    def _lookup(self, key: str) -> Optional[str]:
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

        # Fournisseur du projet (.hydra/secrets.yaml : sops...), en dernier.
        lookup = getattr(self.fallback, "lookup", None)
        if lookup is not None:
            for k in (key, env_name):
                v = lookup(k)
                if v is not None:
                    return str(v)
        return None

    def _get_secret(self, key: str) -> str:
        """
        Recupere un secret obligatoire, cherche dans cet ordre :

        1) le mapping 'secrets' injecte (coffre applicatif, Vault, AWS...) ;
        2) la variable d'environnement correspondante, normalisee
           ('db.password' -> 'DB_PASSWORD') ;
        3) la variable d'environnement portant exactement le nom de la cle ;
        4) le fichier de secrets du projet (`fallback`) : .hydra/secrets, ou le
           fichier désigné par HYDRA_SECRETS_FILE / --secrets-file (en clair
           ou chiffré par SOPS) ;
        5) le fournisseur choisi dans .hydra/secrets.yaml (sops...).

        L'environnement (CI, coffre-fort, shell, .env) l'emporte donc sur le
        fichier : le fichier sert en local, sans rien changer en production.
        """
        value = self._lookup(key)
        if value is not None:
            # Toute valeur lue est masquée ensuite dans les logs et messages
            # (visibilité du projet, voir masking.py).
            from hydra_etl.internal.config.masking import register
            register(value, getattr(self.fallback, "visibility", None), name=key)
            return value

        env_name = self._env_name(key)
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

GITIGNORE_LINES = ("# Hydra: never commit secrets", ".hydra/secrets", ".env", ".env.*", "!.env.example")


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


def load_secrets_file(path: Path, age_key_file: Optional[str] = None) -> Dict[str, str]:
    """Fichier `name=value` en clair, ou chiffré par SOPS (détecté au contenu :
    dotenv, YAML ou JSON ; déchiffré par sops, le clair ne touche pas le disque)."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise SecretResolutionError(f"cannot read secrets file {path}: {e}") from None
    from hydra_etl.internal.config.secret_providers import (
        SecretProviderError, is_sops_encrypted, sops_decrypt)
    if is_sops_encrypted(text):
        try:
            return sops_decrypt(path, age_key_file=age_key_file)
        except SecretProviderError as e:
            raise SecretResolutionError(str(e)) from None
    return parse_secrets_text(text, str(path))


def is_encrypted_file(path: Path) -> bool:
    from hydra_etl.internal.config.secret_providers import is_sops_encrypted
    try:
        return Path(path).is_file() and is_sops_encrypted(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        return False


class ProjectSecrets(dict):
    """Secrets du fichier local (dict, comme avant) + le fournisseur et la
    visibilité réglés dans .hydra/secrets.yaml. `lookup` interroge le
    fournisseur (déchiffré / appelé au premier besoin seulement)."""

    def __init__(self, values: Optional[Mapping[str, str]] = None, *,
                 root: Optional[Path] = None, settings: Any = None, provider: Any = None) -> None:
        super().__init__(values or {})
        self.root = root
        self.settings = settings
        self.provider = provider
        self.visibility = getattr(settings, "visibility", None)

    def lookup(self, key: str) -> Optional[str]:
        if self.provider is None:
            return None
        from hydra_etl.internal.config.secret_providers import SecretProviderError
        try:
            return self.provider.get(key)
        except SecretProviderError as e:
            raise SecretResolutionError(str(e)) from None


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
    contient le premier `anchor` trouvé. Pas de fichier : {}.

    Rend un ProjectSecrets (dict) qui porte aussi les réglages de
    .hydra/secrets.yaml (visibilité, fournisseur). Toutes les valeurs du
    fichier sont enregistrées pour être masquées, même celles qu'aucun
    ${SECRET:...} n'utilise (un script peut les lire autrement)."""
    from hydra_etl.internal.config.masking import VisibilityError, register, resolve_visibility
    from hydra_etl.internal.config.secret_providers import (
        SecretProviderError, build_provider, load_settings)
    root: Optional[Path] = None
    for a in anchors:
        if a is not None:
            root = _project_root(Path(a))
            if root is not None:
                break
    try:
        settings = load_settings(root)
        visibility = resolve_visibility(settings.visibility)
        settings.visibility = visibility
        provider = build_provider(root, settings) if root is not None else None
    except (SecretProviderError, VisibilityError) as e:
        raise SecretResolutionError(str(e)) from None
    age_key = (settings.options.get("sops") or {}).get("age_key_file") \
        if isinstance(settings.options.get("sops"), dict) else None

    values: Dict[str, str] = {}
    explicit = os.environ.get(SECRETS_FILE_ENV)
    if explicit:
        f = Path(explicit).expanduser()
        if not f.is_file():
            raise SecretResolutionError(f"secrets file not found: {f} (set by {SECRETS_FILE_ENV})")
        values = load_secrets_file(f, age_key)
    elif root is not None:
        f = root / PROJECT_SECRETS_FILE
        if f.is_file():
            values = load_secrets_file(f, age_key)
    for k, v in values.items():
        register(v, visibility, name=k)
    if provider is not None and hasattr(provider, "_on_load"):
        provider._on_load = lambda vals: [register(v, visibility, name=k) for k, v in vals.items()]
    return ProjectSecrets(values, root=root, settings=settings, provider=provider)


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


# ---------------------------------------------------------------------------
# Édition du fichier (Studio : onglet Secrets). Les commentaires et l'ordre des
# lignes sont conservés ; seule la ligne du secret visé change.
# ---------------------------------------------------------------------------

def secrets_file_for(project_root: Path) -> Path:
    """Fichier utilisé pour ce projet : HYDRA_SECRETS_FILE s'il est défini,
    sinon <projet>/.hydra/secrets."""
    explicit = os.environ.get(SECRETS_FILE_ENV)
    return Path(explicit).expanduser() if explicit else Path(project_root) / PROJECT_SECRETS_FILE


def check_secret_name(name: str) -> str:
    n = (name or "").strip()
    if not _SECRET_KEY_RE.match(n):
        raise SecretResolutionError(
            f"invalid secret name '{name}': use letters, digits, '.', '_' or '-'")
    return n


def _format_value(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise SecretResolutionError("a secret value cannot contain a line break")
    needs = (value != value.strip() or value[:1] in ("'", '"', "#"))
    if not needs:
        return value
    q = "'" if value.startswith('"') or value.endswith('"') else '"'
    return f"{q}{value}{q}"


def _key_of(line: str) -> Optional[str]:
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    if s.startswith("export "):
        s = s[7:].lstrip()
    return s.split("=", 1)[0].strip()


def set_secret(path: Path, name: str, value: str) -> None:
    """Ajoute ou remplace `name=value` dans le fichier (créé si absent)."""
    name = check_secret_name(name)
    path = Path(path)
    _refuse_encrypted(path)
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.is_file() else \
        SECRETS_TEMPLATE.splitlines()
    new = f"{name}={_format_value(str(value))}"
    for i, ln in enumerate(lines):
        if _key_of(ln) == name:
            lines[i] = new
            break
    else:
        lines.append(new)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _refuse_encrypted(path: Path) -> None:
    if is_encrypted_file(path):
        raise SecretResolutionError(
            f"{path} is encrypted with sops: edit it with `sops {path}`")


def delete_secret(path: Path, name: str) -> bool:
    path = Path(path)
    if not path.is_file():
        return False
    _refuse_encrypted(path)
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    kept = [ln for ln in lines if _key_of(ln) != name]
    if len(kept) == len(lines):
        return False
    path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return True


def env_override(name: str) -> Optional[str]:
    """Nom de la variable d'environnement qui l'emporte sur ce secret, s'il y en a une."""
    norm = SecretResolver._env_name(name)
    if norm in os.environ:
        return norm
    if name in os.environ:
        return name
    return None
