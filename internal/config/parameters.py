"""
internal/config/parameters.py — Résolveur de PARAMÈTRES Hydra.

Concept (cf. modèle Postman, couche statique) :
- Les paramètres sont des ENTRÉES en lecture seule, fixées AVANT l'exécution.
- Portées empilées avec précédence (la plus forte gagne) :
      run (--param)  >  job  >  workflow  >  project(default)
  résolues pour l'ENVIRONNEMENT actif (dev/prod...).
- Immuables pendant l'exécution -> distribuables sans store central
  (compatible architecture mosaïque/parallèle).

Grammaire unique de substitution :
    {{ param:NAME }}   -> valeur du paramètre résolu
    {{ env:NAME }}     -> variable d'environnement OS

Préservation de type : si une chaîne vaut EXACTEMENT un placeholder
(`"{{ param:batch_size }}"`), on renvoie la valeur TYPÉE (int, bool...).
Si le placeholder est intégré (`"schema_{{ param:x }}"`), substitution string.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


# {{ param:NAME }} / {{ env:NAME }}  (espaces tolérés, NAME alphanum . _ -)
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(param|env)\s*:\s*([A-Za-z0-9_.\-]+)\s*\}\}")
_FULL_RE = re.compile(r"^\s*\{\{\s*(param|env)\s*:\s*([A-Za-z0-9_.\-]+)\s*\}\}\s*$")

_ALLOWED_TYPES = {"int", "float", "string", "str", "bool", "boolean", "json", "any"}


class ParameterError(ValueError):
    """Erreur de déclaration, coercion ou résolution de paramètre."""


# ------------------------------------------------------------------
# Coercion de type
# ------------------------------------------------------------------

def coerce_value(value: Any, typ: str, name: str = "") -> Any:
    """Convertit `value` vers le type déclaré. Tolère les valeurs déjà typées."""
    t = (typ or "any").strip().lower()
    if value is None:
        return None
    try:
        if t in ("string", "str"):
            return str(value)
        if t == "int":
            if isinstance(value, bool):
                raise ValueError("bool n'est pas un int")
            return int(value)
        if t == "float":
            return float(value)
        if t in ("bool", "boolean"):
            if isinstance(value, bool):
                return value
            s = str(value).strip().lower()
            if s in ("true", "1", "yes", "on"):
                return True
            if s in ("false", "0", "no", "off"):
                return False
            raise ValueError(f"'{value}' n'est pas un booléen")
        if t == "json":
            if isinstance(value, (dict, list)):
                return value
            return json.loads(value)
        # any
        return value
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        raise ParameterError(
            f"paramètre '{name}': valeur {value!r} non convertible en {t}: {e}"
        ) from None


# ------------------------------------------------------------------
# Construction des valeurs effectives (déclarations + couches)
# ------------------------------------------------------------------

def build_effective(
    declarations: Mapping[str, Mapping[str, Any]],
    layers: List[Mapping[str, Any]],
) -> Dict[str, Any]:
    """
    Calcule les valeurs effectives des paramètres.

    - declarations : { name: {type, default, required, description} }
    - layers       : couches de valeurs, ordonnées de la PLUS FAIBLE à la PLUS
                     FORTE précédence, ex. [project, workflow, job, runtime].
                     Chaque couche est un dict { name: value }.

    Retourne { name: valeur_typée }. Lève ParameterError si un paramètre requis
    n'a ni valeur ni défaut.
    """
    # Fusion des couches (les dernières écrasent les premières)
    merged: Dict[str, Any] = {}
    for layer in layers:
        if not layer:
            continue
        for k, v in layer.items():
            if v is not None:
                merged[k] = v

    effective: Dict[str, Any] = {}
    for name, decl in declarations.items():
        decl = decl or {}
        typ = str(decl.get("type", "any"))
        has_value = name in merged
        raw = merged.get(name, decl.get("default"))
        if raw is None:
            if decl.get("required") and not has_value:
                raise ParameterError(f"paramètre requis manquant: '{name}'")
            effective[name] = None
            continue
        effective[name] = coerce_value(raw, typ, name)

    # Valeurs fournies pour des paramètres non déclarés : tolérées (type 'any')
    for name, v in merged.items():
        if name not in effective:
            effective[name] = v

    return effective


# ------------------------------------------------------------------
# Résolveur (substitution récursive)
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ParameterResolver:
    """Substitue {{ param:x }} / {{ env:x }} dans une structure issue du YAML."""

    params: Mapping[str, Any] = field(default_factory=dict)
    env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    strict: bool = True
    # Contrôle indépendant pour les placeholders {{ param:x }}.
    # None -> hérite de `strict`. Permet d'être tolérant sur {{ env:x }}
    # (strict=False) tout en exigeant que les paramètres déclarés résolvent
    # (strict_params=True) -> évite le host=None silencieux.
    strict_params: Optional[bool] = None

    # -- API publique --

    def resolve(self, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: self.resolve(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self.resolve(v) for v in data]
        if isinstance(data, str):
            return self._resolve_string(data)
        return data

    # -- interne --

    def _lookup(self, kind: str, key: str) -> Any:
        if kind == "param":
            if key in self.params:
                return self.params[key]
            strict_p = self.strict if self.strict_params is None else self.strict_params
            if strict_p:
                raise ParameterError(f"paramètre non résolu: '{key}'")
            return None
        # env
        if key in self.env:
            return self.env[key]
        if self.strict:
            raise ParameterError(f"variable d'environnement manquante: '{key}'")
        return None

    def _resolve_string(self, s: str) -> Any:
        m = _FULL_RE.match(s)
        if m:
            # Chaîne = un seul placeholder -> on préserve le TYPE
            return self._lookup(m.group(1), m.group(2))
        # Placeholder(s) intégré(s) -> substitution texte
        return _PLACEHOLDER_RE.sub(
            lambda mm: str(self._lookup(mm.group(1), mm.group(2))), s
        )
