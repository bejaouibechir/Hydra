"""
Contrat standard des connecteurs SmartETL / Hydra.

But :
- Imposer une API minimale et stable aux connecteurs (DB, CSV, JSON, API...).
- Garantir que l'executor peut orchestrer n'importe quelle source/destination
  sans connaître les détails techniques.

Principes :
- extract_batches() : produit des lots (batches) de lignes.
- load_batches()    : consomme des lots (batches) de lignes.
- test_connection() : diagnostic rapide utilisé par la CLI et les checks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Optional


# -------------------------------
# Types minimaux manipulés par le core
# -------------------------------

Row = Dict[str, Any]
Batch = List[Row]


@dataclass(frozen=True)
class ConnectorCapabilities:
    """
    Capacités déclaratives du connecteur.

    L'idée :
    - L'executor/engine peut adapter son comportement sans heuristiques.
    - On évite d'ajouter des méthodes partout : on déclare des flags.
    """

    # True si le connecteur sait faire des transactions (utile côté destination)
    supports_transactions: bool = False

    # True si le connecteur sait faire de l'upsert natif (sinon fallback possible)
    supports_upsert: bool = False

    # True si le connecteur peut lire en mode "incremental" (CDC, timestamp, etc.)
    supports_incremental: bool = False


# -------------------------------
# Contrat du connecteur
# -------------------------------

class Connector(ABC):
    """
    Interface de base.

    Un connecteur peut être utilisé :
    - comme source (extract)
    - comme destination (load)
    - ou les deux

    Le core n'impose aucune librairie (mysql-connector, pandas, etc.).
    """

    # Projection : un connecteur qui sait ne lire qu'un sous-ensemble de
    # colonnes passe ce drapeau à True et honore set_projection().
    supports_projection: bool = False

    def set_projection(self, columns: Optional[List[str]]) -> None:
        """Restreint la lecture aux colonnes indiquées (None = toutes).

        La restriction est *souple* : une colonne demandée mais absente du
        fichier n'est pas une erreur ici — l'opération qui en a besoin
        produira son propre message, comme avant. Un connecteur qui ne sait
        pas projeter ignore simplement l'appel.
        """
        return None

    def reader_is_columnar(self, table: Optional[str] = None) -> bool:
        """True si la lecture produit des lots par colonnes, sans dict par ligne."""
        return False

    def writer_is_columnar(self, table: Optional[str] = None) -> bool:
        """True si l'écriture consomme des lots par colonnes, sans dict par ligne."""
        return False

    def reader_releases_gil(self, table: Optional[str] = None) -> bool:
        """True si la lecture relâche le GIL (lecteur natif, pilote C...).

        L'executor s'en sert pour décider s'il vaut la peine de lire le lot
        suivant dans un thread pendant que le lot courant est transformé.
        """
        return False

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        # name : identifiant stable (ex: "src_orders", "dest_dwh")
        # config: configuration résolue (secrets déjà substitués)
        self.name = name
        self.config = config

    @property
    def capabilities(self) -> ConnectorCapabilities:
        """
        Retourne les capacités du connecteur.
        Par défaut : aucune capacité spéciale.
        """
        return ConnectorCapabilities()

    @abstractmethod
    def test_connection(self) -> None:
        """
        Doit lever une exception explicite si la connexion échoue.

        Utilisé par :
        - CLI (etl test-connection)
        - validations d'environnement
        """
        raise NotImplementedError

    @abstractmethod
    def extract_batches(
        self,
        *,
        query: Optional[str] = None,
        table: Optional[str] = None,
        batch_size: int = 10_000,
        incremental: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Batch]:
        """
        Produit des lots de lignes.

        Paramètres :
        - query : SQL brut si applicable
        - table : table à lire si applicable
        - batch_size : taille cible d'un lot (contrat : best effort)
        - incremental : infos pour lecture incrémentale (cursor, timestamp, LSN...)

        Règles :
        - Doit renvoyer un Iterator (streaming) pour éviter de charger tout en RAM.
        - Chaque Row est un dict colonne->valeur.
        """
        raise NotImplementedError

    @abstractmethod
    def load_batches(
        self,
        batches: Iterable[Batch],
        *,
        table: str,
        mode: str = "append",
        key: Optional[List[str]] = None,
    ) -> None:
        """
        Consomme des lots de lignes et les charge dans une destination.

        Paramètres :
        - batches : itérable de Batch (streaming compatible)
        - table   : table/ressource cible
        - mode    : append | replace | upsert | truncate_then_load (MVP: append/replace)
        - key     : colonnes clés pour upsert (si mode=upsert)

        Règles :
        - Doit lever une exception claire si le chargement échoue.
        - Le mode exact sera validé côté parser/config, ici on applique.
        """
        raise NotImplementedError
