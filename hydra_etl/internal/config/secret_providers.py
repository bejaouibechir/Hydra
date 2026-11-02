"""
Fournisseurs de secrets et réglages du projet (`.hydra/secrets.yaml`).

Ordre de recherche d'un ``${SECRET:nom}`` (inchangé pour l'existant) :

1. variable d'environnement normalisée (``db.password`` -> ``DB_PASSWORD``) ;
2. variable d'environnement exacte ;
3. fichier local ``.hydra/secrets`` (ou HYDRA_SECRETS_FILE / --secrets-file),
   en clair ou chiffré par SOPS (détecté tout seul) ;
4. le fournisseur choisi dans ``.hydra/secrets.yaml``.

Réglages (`.hydra/secrets.yaml`, sans aucun secret, peut être commité) ::

    visibility: masked          # plain | masked | hidden
    provider: sops              # none (défaut) | sops
    sops:
      file: .hydra/secrets.sops.yaml   # relatif à la racine du projet
      age_key_file: ~/.config/sops/age/keys.txt   # optionnel

Ajouter un fournisseur (coffre externe) : sous-classer ``SecretProvider`` et
l'enregistrer avec ``register_provider("nom", fabrique)``. La fabrique reçoit
la racine du projet et le bloc de réglages qui porte son nom.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

SETTINGS_FILE = Path(".hydra") / "secrets.yaml"
SOPS_BIN_ENV = "HYDRA_SOPS_BIN"
SOPS_INSTALL_HINT = "install it from https://github.com/getsops/sops/releases (and age from https://github.com/FiloSottile/age)"
# Coffres externes prévus : refusés avec un message clair tant qu'ils ne sont pas livrés.
PLANNED_PROVIDERS = ("vault", "azure-keyvault", "aws-secrets-manager")


class SecretProviderError(ValueError):
    """Erreur de fournisseur. Ne cite jamais une valeur de secret."""


# ── Interface ───────────────────────────────────────────────────────────────
class SecretProvider(ABC):
    """Source de secrets. `get` rend None quand le nom est inconnu."""

    name: str = "provider"

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        ...

    def keys(self) -> List[str]:
        """Noms connus (vide si le fournisseur ne sait pas lister)."""
        return []

    def describe(self) -> str:
        return self.name


class MappingProvider(SecretProvider):
    name = "mapping"

    def __init__(self, values: Dict[str, str], name: str = "mapping") -> None:
        self._values = dict(values)
        self.name = name

    def get(self, key: str) -> Optional[str]:
        return self._values.get(key)

    def keys(self) -> List[str]:
        return list(self._values)


# ── SOPS (+ age) ────────────────────────────────────────────────────────────
_SOPS_DOTENV_RE = re.compile(r"^\s*sops_(version|lastmodified|mac)\s*=", re.M)
_SOPS_JSON_RE = re.compile(r'"sops"\s*:\s*\{')
_SOPS_YAML_RE = re.compile(r"^sops:\s*$", re.M)


def is_sops_encrypted(text: str) -> bool:
    """Le contenu porte les métadonnées SOPS (dotenv, YAML ou JSON) ?"""
    return bool(_SOPS_DOTENV_RE.search(text) or _SOPS_YAML_RE.search(text)
                or _SOPS_JSON_RE.search(text))


def sops_format(path: Path, declared: Optional[str] = None) -> str:
    if declared:
        f = str(declared).strip().lower()
        if f not in ("dotenv", "yaml", "json"):
            raise SecretProviderError(f"sops.format: '{declared}' (expected dotenv, yaml or json)")
        return f
    ext = Path(path).suffix.lower()
    return {".yaml": "yaml", ".yml": "yaml", ".json": "json"}.get(ext, "dotenv")


def sops_binary() -> str:
    explicit = os.environ.get(SOPS_BIN_ENV)
    found = explicit or shutil.which("sops")
    if not found:
        raise SecretProviderError(f"sops is not installed or not on PATH: {SOPS_INSTALL_HINT}")
    return found


def flatten(data: Any, prefix: str = "") -> Dict[str, str]:
    """{"db": {"password": "x"}} -> {"db.password": "x"} ; listes : index."""
    out: Dict[str, str] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            if not prefix and k == "sops":
                continue
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            out.update(flatten(v, f"{prefix}.{i}"))
    elif data is not None and prefix:
        if isinstance(data, bool):
            out[prefix] = "true" if data else "false"
        else:
            out[prefix] = str(data)
    return out


def sops_decrypt(path: Path, fmt: Optional[str] = None,
                 age_key_file: Optional[str] = None) -> Dict[str, str]:
    """Déchiffre un fichier SOPS et rend ses secrets à plat (nom -> valeur).
    Le clair ne touche jamais le disque : il passe par la sortie de sops."""
    path = Path(path)
    if not path.is_file():
        raise SecretProviderError(f"sops: encrypted secrets file not found: {path}")
    kind = sops_format(path, fmt)
    env = dict(os.environ)
    if age_key_file:
        env["SOPS_AGE_KEY_FILE"] = str(Path(age_key_file).expanduser())
    cmd = [sops_binary(), "--decrypt", "--input-type", kind, "--output-type", "json", str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise SecretProviderError(f"sops: cannot run {cmd[0]}: {e}") from None
    if proc.returncode != 0:
        last = next((ln.strip() for ln in reversed(proc.stderr.splitlines()) if ln.strip()), "")
        hint = ""
        if "no identity matched" in proc.stderr.lower() or "failed to get the data key" in proc.stderr.lower():
            hint = (" — no age key can open this file: set SOPS_AGE_KEY_FILE (or sops.age_key_file "
                    "in .hydra/secrets.yaml) to the private key of one of its recipients")
        raise SecretProviderError(f"sops: cannot decrypt {path}: {last[:300]}{hint}")
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        raise SecretProviderError(f"sops: unreadable output while decrypting {path}") from None
    return flatten(data)


class SopsProvider(SecretProvider):
    """Fichier chiffré par SOPS (age, PGP, KMS... : c'est sops qui choisit).
    Déchiffré une seule fois, au premier secret demandé."""

    name = "sops"

    def __init__(self, file: Path, fmt: Optional[str] = None,
                 age_key_file: Optional[str] = None,
                 on_load: Optional[Callable[[Dict[str, str]], None]] = None) -> None:
        self.file = Path(file)
        self.fmt = fmt
        self.age_key_file = age_key_file
        self._values: Optional[Dict[str, str]] = None
        self._on_load = on_load

    def _load(self) -> Dict[str, str]:
        if self._values is None:
            self._values = sops_decrypt(self.file, self.fmt, self.age_key_file)
            if self._on_load:
                self._on_load(self._values)
        return self._values

    def get(self, key: str) -> Optional[str]:
        return self._load().get(key)

    def keys(self) -> List[str]:
        return list(self._load())

    def describe(self) -> str:
        return f"sops ({self.file})"


# ── Registre des fournisseurs ───────────────────────────────────────────────
ProviderFactory = Callable[..., SecretProvider]   # (root, block, settings, env=None)
_PROVIDERS: Dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    _PROVIDERS[name] = factory


def _sops_factory(root: Path, block: Dict[str, Any], settings: "SecretsSettings",
                  env: Optional[str] = None) -> SecretProvider:
    file = block.get("file")
    if not file:
        raise SecretProviderError(f"{settings.source}: provider 'sops' needs sops.file "
                                  "(path of the encrypted file, relative to the project)")
    file = str(file)
    if "{env}" in file:
        if not env:
            raise SecretProviderError(f"{settings.source}: sops.file uses {{env}} but no environment is "
                                      "selected (--env or HYDRA_ENV)")
        file = file.replace("{env}", env)
    p = Path(file).expanduser()
    if not p.is_absolute():
        p = Path(root) / p
    return SopsProvider(p, block.get("format"), block.get("age_key_file"))


register_provider("sops", _sops_factory)


# ── Réglages du projet ──────────────────────────────────────────────────────
@dataclass
class SecretsSettings:
    visibility: Optional[str] = None       # None : défaut (masked) ou HYDRA_SECRETS_VISIBILITY
    provider: str = "none"
    options: Dict[str, Any] = field(default_factory=dict)
    source: str = str(SETTINGS_FILE)


_KNOWN_KEYS = {"visibility", "provider"}


def load_settings(root: Optional[Path]) -> SecretsSettings:
    """Lit `.hydra/secrets.yaml` ; absent -> réglages par défaut."""
    from hydra_etl.internal.config.masking import VisibilityError, check_visibility
    if root is None:
        return SecretsSettings()
    f = Path(root) / SETTINGS_FILE
    if not f.is_file():
        return SecretsSettings()
    import yaml
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8-sig")) or {}
    except Exception as e:  # noqa: BLE001
        raise SecretProviderError(f"{f}: invalid YAML ({e})") from None
    if not isinstance(data, dict):
        raise SecretProviderError(f"{f}: expected a mapping (visibility, provider, ...)")
    s = SecretsSettings(source=str(f))
    if data.get("visibility") is not None:
        try:
            s.visibility = check_visibility(data["visibility"], str(f))
        except VisibilityError as e:
            raise SecretProviderError(str(e)) from None
    prov = str(data.get("provider") or "none").strip().lower()
    if prov != "none" and prov not in _PROVIDERS:
        if prov in PLANNED_PROVIDERS:
            raise SecretProviderError(f"{f}: provider '{prov}' is not available in this version of Hydra "
                                      f"(available: none, {', '.join(sorted(_PROVIDERS))})")
        raise SecretProviderError(f"{f}: unknown provider '{prov}' "
                                  f"(available: none, {', '.join(sorted(_PROVIDERS))})")
    s.provider = prov
    unknown = [k for k in data if k not in _KNOWN_KEYS and k not in _PROVIDERS and k not in PLANNED_PROVIDERS]
    if unknown:
        raise SecretProviderError(f"{f}: unknown key(s): {', '.join(map(str, unknown))} "
                                  "(expected visibility, provider and the provider block)")
    s.options = data
    return s


def build_provider(root: Path, settings: SecretsSettings, env: Optional[str] = None) -> Optional[SecretProvider]:
    if settings.provider == "none":
        return None
    block = settings.options.get(settings.provider) or {}
    if not isinstance(block, dict):
        raise SecretProviderError(f"{settings.source}: '{settings.provider}' must be a mapping")
    factory = _PROVIDERS[settings.provider]
    import inspect
    try:
        takes_env = len(inspect.signature(factory).parameters) >= 4
    except (TypeError, ValueError):
        takes_env = False
    # fournisseur enregistré avant 0.18 : (root, block, settings), sans env
    return factory(Path(root), block, settings, env) if takes_env else factory(Path(root), block, settings)
