"""Les langues de la CLI : fichiers présents = langues supportées, mêmes clés,
mêmes variables {placeholders}, plus aucune trace de l'ancienne commande `hydra`."""
from __future__ import annotations

import json
import re
import string
from pathlib import Path

import pytest

from hydra_etl.cli import i18n

LOCALES = Path(i18n.__file__).parent / "locales"


def _load(lang: str) -> dict:
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


def _fields(text: str) -> set:
    try:
        return {f for _, f, _, _ in string.Formatter().parse(text) if f}
    except ValueError:
        return set()


def test_files_match_supported_languages():
    assert {p.stem for p in LOCALES.glob("*.json")} == set(i18n._SUPPORTED)


@pytest.mark.parametrize("lang", sorted(i18n._SUPPORTED - {"en"}))
def test_same_keys_as_english(lang):
    en, other = _load("en"), _load(lang)
    assert sorted(set(en) - set(other)) == [], "missing translations"
    assert sorted(set(other) - set(en)) == [], "keys unknown to en.json"


@pytest.mark.parametrize("lang", sorted(i18n._SUPPORTED - {"en"}))
def test_same_placeholders_as_english(lang):
    en, other = _load("en"), _load(lang)
    diff = {k: (_fields(en[k]), _fields(other[k])) for k in en
            if k in other and _fields(en[k]) != _fields(other[k])}
    assert diff == {}


@pytest.mark.parametrize("lang", sorted(i18n._SUPPORTED))
def test_no_legacy_hydra_command(lang):
    legacy = re.compile(r"(?<![\w./-])hydra (test|validate|list|clear|workflow|run|init|serve)\b")
    hits = [k for k, v in _load(lang).items() if legacy.search(v)]
    assert hits == []


@pytest.mark.parametrize("lang", sorted(i18n._SUPPORTED))
def test_lang_help_lists_supported_languages(lang):
    text = _load(lang)["help.lang"]
    for code in i18n._SUPPORTED:
        assert code in text
