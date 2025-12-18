"""
Tests d'adhérence aux interfaces vitales.

But :
- Vérifier que les interfaces sont instanciables via une implémentation minimale.
- Vérifier que les méthodes obligatoires existent.
- Éviter une régression future (ex: renommage de méthode).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional

import pytest

from internal.connector.interface import Batch, Connector
from internal.transform.engine_interface import StepResult, TransformEngine


class DummyConnector(Connector):
    """
    Connecteur minimal pour tests :
    - extract_batches : renvoie 2 lots fixes
    - load_batches : consomme sans rien faire
    - test_connection : ne lève pas d'erreur
    """

    def test_connection(self) -> None:
        # Simule une connexion OK
        return None

    def extract_batches(
        self,
        *,
        query: Optional[str] = None,
        table: Optional[str] = None,
        batch_size: int = 10_000,
        incremental: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Batch]:
        # Simule 2 lots de données
        yield [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
        yield [{"id": 3, "name": "C"}]

    def load_batches(
        self,
        batches: Iterable[Batch],
        *,
        table: str,
        mode: str = "append",
        key: Optional[List[str]] = None,
    ) -> None:
        # Consomme les batches sans persister (test dummy)
        for _ in batches:
            pass


class DummyEngine(TransformEngine):
    """
    Moteur minimal pour tests :
    - apply_step : renvoie le dataset inchangé, avec des stats simples.
    """

    def apply_step(
        self,
        dataset: Any,
        step: Dict[str, Any],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> StepResult:
        # Stat minimale : on note juste le type d'étape
        return StepResult(output=dataset, stats={"ok": True, "step": self._infer_step_type(step)})


def test_connector_contract_smoke():
    """
    Vérifie qu'un connecteur minimal respecte le contrat :
    - test_connection()
    - extract_batches()
    - load_batches()
    """
    c = DummyConnector(name="dummy", config={})

    # Ne doit pas lever d'erreur
    c.test_connection()

    # extract_batches doit être itérable et produire des lots
    batches = list(c.extract_batches(table="t"))
    assert len(batches) == 2
    assert batches[0][0]["id"] == 1

    # load_batches doit accepter un itérable
    c.load_batches(batches, table="t", mode="append")


def test_transform_engine_contract_smoke():
    """
    Vérifie qu'un moteur minimal respecte le contrat :
    - apply_step() obligatoire
    - apply_pipeline() fonctionne par défaut
    """
    e = DummyEngine(name="dummy-engine")

    dataset = {"any": "thing"}  # volontairement Any
    step = {"select": {"columns": ["id"]}}

    # apply_step
    r1 = e.apply_step(dataset, step)
    assert r1.output == dataset
    assert r1.stats["ok"] is True

    # apply_pipeline
    r2 = e.apply_pipeline(dataset, [step, {"filter": {"expr": "id > 1"}}])
    assert r2.output == dataset
    assert len(r2.stats["steps"]) == 2
