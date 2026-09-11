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
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping


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
            raise SecretResolutionError(f"Variable d'environnement manquante: {key}")
        return os.environ[key]

    def _get_secret(self, key: str) -> str:
        """
        Récupère un secret obligatoire depuis le mapping 'secrets'.
        """
        if key not in self.secrets:
            raise SecretResolutionError(f"Secret manquant: {key}")
        return str(self.secrets[key])
