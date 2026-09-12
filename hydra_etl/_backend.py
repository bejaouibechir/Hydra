"""
Aiguillage Python / Rust (plan d'intégration Rust, étape 5).

Une opération accélérable (ex. ``csv.read``) a toujours une implémentation
Python de référence ; l'implémentation Rust est optionnelle. Le choix se fait
par opération, avec cette priorité :

    1. paramètre ``backend=`` passé à l'appel (dynamique) ;
    2. ``overrides`` du fichier de configuration ;
    3. ``default`` du fichier de configuration ;
    4. variable d'environnement ``HYDRA_BACKEND`` ;
    5. ``python``.

Fichier de configuration : ``HYDRA_BACKENDS_FILE`` si défini, sinon
``hydra.backends.yaml`` dans le répertoire courant. Il est lu une seule fois
(``reload()`` pour les tests)::

    default: python
    overrides:
      csv.read: rust

Si Rust est demandé mais indisponible (module non installé, plateforme non
supportée), l'implémentation Python est utilisée et un avertissement est émis
une seule fois par opération et par processus. Jamais de repli silencieux.
"""

from __future__ import annotations

import functools
import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger("hydra_etl.backend")

BACKENDS = ("python", "rust")
_CONFIG_NAME = "hydra.backends.yaml"

_lock = threading.RLock()  # réentrant : _load_config peut appeler warn_once
_config: Optional[Tuple[Optional[str], Dict[str, str]]] = None
_warned: set = set()


def _t(key: str, **kwargs: Any) -> str:
    try:
        from hydra_etl.cli.i18n import t
        return t(key, **kwargs)
    except Exception:  # noqa: BLE001 - i18n indisponible : message anglais minimal
        return f"{key} {kwargs}"


def warn_once(key: str, message: str) -> None:
    """Avertissement (logger + warnings) émis une seule fois par clé et par processus."""
    with _lock:
        if key in _warned:
            return
        _warned.add(key)
    import warnings
    logger.warning(message)
    warnings.warn(message, RuntimeWarning, stacklevel=3)


def _normalize(value: Any, origin: str) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip().lower()
    if v in BACKENDS:
        return v
    warn_once(f"invalid:{origin}:{v}", _t("backend.invalid_value", value=value, origin=origin))
    return None


def _load_config() -> Tuple[Optional[str], Dict[str, str]]:
    path = Path(os.environ.get("HYDRA_BACKENDS_FILE") or _CONFIG_NAME)
    if not path.is_file():
        return None, {}
    try:
        import yaml
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        warn_once(f"config:{path}", _t("backend.config_unreadable", path=str(path), error=str(exc)))
        return None, {}
    if not isinstance(raw, dict):
        warn_once(f"config:{path}", _t("backend.config_unreadable", path=str(path), error="not a mapping"))
        return None, {}
    default = _normalize(raw.get("default"), str(path))
    overrides: Dict[str, str] = {}
    for op, val in (raw.get("overrides") or {}).items():
        v = _normalize(val, f"{path}:{op}")
        if v:
            overrides[str(op)] = v
    return default, overrides


def _get_config() -> Tuple[Optional[str], Dict[str, str]]:
    global _config
    if _config is None:
        with _lock:
            if _config is None:
                _config = _load_config()
    return _config


def reload() -> None:
    """Relit la configuration et réarme les avertissements (tests)."""
    global _config
    with _lock:
        _config = None
        _warned.clear()


def resolve(operation: str, backend: Optional[str] = None) -> str:
    """Backend demandé pour `operation` (sans vérifier sa disponibilité)."""
    explicit = _normalize(backend, "backend=") if backend is not None else None
    if explicit:
        return explicit
    default, overrides = _get_config()
    if operation in overrides:
        return overrides[operation]
    if default:
        return default
    return _normalize(os.environ.get("HYDRA_BACKEND"), "HYDRA_BACKEND") or "python"


@functools.lru_cache(maxsize=None)
def native_status() -> Tuple[bool, str]:
    """(disponible, raison) pour le module natif hydra_native et pyarrow."""
    try:
        import hydra_native  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return False, f"hydra_native not installed ({type(exc).__name__})"
    try:
        import pyarrow  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return False, f"pyarrow not installed ({type(exc).__name__})"
    return True, ""


def dual(operation: str, rust: str) -> Callable:
    """
    Décore la méthode Python de référence d'une opération.

    `rust` est le nom de la méthode sœur qui implémente la version Rust, avec la
    même signature. Le wrapper accepte un argument supplémentaire ``backend=``.
    """

    def deco(py_func: Callable) -> Callable:
        @functools.wraps(py_func)
        def wrapper(self, *args: Any, backend: Optional[str] = None, **kwargs: Any):
            if resolve(operation, backend) == "rust":
                ok, reason = native_status()
                if ok:
                    return getattr(self, rust)(*args, **kwargs)
                warn_once(f"unavailable:{operation}",
                          _t("backend.rust_unavailable", operation=operation, reason=reason))
            return py_func(self, *args, **kwargs)

        wrapper.__hydra_operation__ = operation  # type: ignore[attr-defined]
        return wrapper

    return deco
