"""
i18n — Hydra ETL internationalisation module.

Zero external dependencies. Language detection priority:
  1. CLI option --lang (pre-scanned from sys.argv at import time)
  2. Environment variable HYDRA_LANG
  3. System locale (cross-platform)
  4. Fallback → en

Usage:
    from cli.i18n import t, set_lang

    t("key")
    t("key_with_param", name="Alice", count=3)
    set_lang("fr")   # override (called by --lang Click callback)
"""
from __future__ import annotations

import json
import locale
import os
import sys
from functools import lru_cache
from pathlib import Path

_LOCALES_DIR = Path(__file__).parent / "locales"
_SUPPORTED = frozenset({"en", "es"})
_FALLBACK = "en"

# Global override set by --lang CLI option (takes precedence over everything)
_lang_override: str | None = None


@lru_cache(maxsize=8)
def _load(lang: str) -> dict[str, str]:
    """Charge le fichier JSON d'une langue (résultat mis en cache)."""
    path = _LOCALES_DIR / f"{lang}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def detect_locale() -> str:
    """
    Détecte la langue active selon l'ordre de priorité défini.
    Appelée dynamiquement à chaque appel de t().
    """
    # 1. Override explicite (set par --lang callback ou set_lang())
    if _lang_override:
        return _lang_override

    # 2. Pre-scan sys.argv pour --lang (permet de traduire les textes --help)
    argv = sys.argv[1:]
    for i, arg in enumerate(argv):
        if arg == "--lang" and i + 1 < len(argv):
            code = argv[i + 1][:2].lower()
            if code in _SUPPORTED:
                return code
        elif arg.startswith("--lang="):
            code = arg[7:][:2].lower()
            if code in _SUPPORTED:
                return code

    # 3. Variable d'environnement HYDRA_LANG
    env = os.environ.get("HYDRA_LANG", "")
    if env:
        code = env[:2].lower()
        if code in _SUPPORTED:
            return code

    # 4. Locale système (cross-platform)
    try:
        loc = locale.getdefaultlocale()[0] or ""
        code = loc[:2].lower()
        if code in _SUPPORTED:
            return code
    except Exception:
        pass

    return _FALLBACK


def t(key: str, **kwargs: object) -> str:
    """
    Retourne la traduction de la clé pour la langue active.

    Fallback clé par clé : si manquante dans la langue active → anglais → clé brute.
    Les paramètres sont interpolés via str.format().
    """
    lang = detect_locale()
    msg = _load(lang).get(key) or _load(_FALLBACK).get(key) or key
    if kwargs:
        try:
            return msg.format(**kwargs)
        except (KeyError, IndexError):
            return msg
    return msg


def set_lang(lang: str | None) -> None:
    """
    Force la langue (appelé par le callback Click --lang).
    Vide le cache LRU pour recharger si nécessaire.
    """
    global _lang_override
    if lang:
        code = lang[:2].lower()
        _lang_override = code if code in _SUPPORTED else None
    else:
        _lang_override = None
