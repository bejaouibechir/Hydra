"""
Registry d'engines (MVP).

Objectif :
- Centraliser l'enregistrement et la récupération des TransformEngine
  (pandas, duckdb, ...).
- Permettre l'extension plus tard via plugins.

MVP :
- On enregistre PandasEngine par défaut.
- DuckDB reste optionnel (placeholder dans ce repo).
"""

from __future__ import annotations

from typing import Dict, Type

from hydra_etl.internal.transform.engine_interface import TransformEngine
from hydra_etl.internal.engines.pandas_engine import PandasEngine


class EngineRegistry:
    """
    Registre simple : name -> classe d'engine.
    """

    def __init__(self) -> None:
        self._engines: Dict[str, Type[TransformEngine]] = {}

    def register(self, name: str, engine_cls: Type[TransformEngine]) -> None:
        """
        Enregistre un engine.
        - name : identifiant stable (ex: "pandas")
        - engine_cls : classe TransformEngine
        """
        key = name.strip().lower()
        if not key:
            raise ValueError("EngineRegistry.register: name ne peut pas être vide.")
        if not issubclass(engine_cls, TransformEngine):
            raise TypeError("EngineRegistry.register: engine_cls doit hériter de TransformEngine.")
        self._engines[key] = engine_cls

    def get(self, name: str) -> Type[TransformEngine]:
        """
        Récupère la classe d'un engine.
        """
        key = name.strip().lower()
        if key not in self._engines:
            known = ", ".join(sorted(self._engines.keys())) or "(aucun)"
            raise KeyError(f"Engine inconnu: {name!r}. Connus: {known}")
        return self._engines[key]

    def create(self, name: str) -> TransformEngine:
        """
        Instancie un engine par son nom.
        """
        cls = self.get(name)
        return cls(name=name.strip().lower())


# Registry global (simple pour MVP)
registry = EngineRegistry()
registry.register("pandas", PandasEngine)
