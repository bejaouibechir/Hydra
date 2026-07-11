"""
Base minimale pour connecteurs SQL (MySQL/MariaDB aujourd'hui, PostgreSQL/Oracle demain).

Objectif (Option B ultra-minimale) :
- Mutualiser UNIQUEMENT ce qui est réellement commun aux connecteurs DB
- Ne pas imposer de pooling/retry/type-mapping global (reporté)
- Rester compatible avec le contrat Connector (extract_batches / load_batches / test_connection)

Cette base fournit :
- __init__() : normalisation de la section connection
- _build_connection_string() : abstrait (chaque DB a son DSN)
- test_connection() : template method (SELECT 1)
- _execute_query_batches() : helper générique (cursor.fetchmany)
- _get_table_columns() : inspection (via requête fournie par la classe fille)
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, Iterator, List, Optional, Sequence

from internal.connector.interface import Batch, Connector, Row


class BaseDBConnector(Connector):
    """
    Base class DB volontairement très mince.

    Règles :
    - Ne dépend d'aucun driver (mysql-connector, psycopg2, cx_Oracle, etc.).
    - Les classes filles fournissent la connexion et les requêtes spécifiques.
    - Toutes les erreurs sont normalisées en ValueError pour cohérence côté core.
    """

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        # Constructeur standard (contrat Connector)
        super().__init__(name=name, config=config)

        # On extrait la section connection (le parser doit la garantir, mais on reste safe).
        connection = config.get("connection")
        if not isinstance(connection, dict):
            raise ValueError(f"{self.__class__.__name__} [{self.name}]: 'connection' doit être un objet (dict).")

        # On conserve une copie défensive.
        self._conn_cfg: Dict[str, Any] = dict(connection)

    # ------------------------------------------------------------------
    # Hooks abstraits (dépendants du driver / dialecte)
    # ------------------------------------------------------------------

    @abstractmethod
    def _connect(self):
        """
        Retourne une connexion DB-API (ou équivalent driver) ouverte.

        Contrat attendu :
        - conn.cursor() -> cursor
        - conn.close()
        - cursor.execute(sql, params?) + cursor.fetchmany(n) + cursor.description
        """
        raise NotImplementedError

    @abstractmethod
    def _build_connection_string(self) -> str:
        """Construit un DSN lisible (utile pour logs/diagnostics)."""
        raise NotImplementedError

    @abstractmethod
    def _build_columns_query(self, table: str) -> str:
        """
        Retourne une requête SQL qui permet d'obtenir la liste des colonnes de `table`.

        Exemple MySQL/MariaDB :
        - SELECT * FROM `table` LIMIT 0
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Helpers partagés
    # ------------------------------------------------------------------

    def test_connection(self) -> None:
        """
        Test rapide de connectivité (template method).

        - Ouvre une connexion
        - Exécute SELECT 1
        - Ferme proprement
        """
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()  # best effort : certains drivers exigent une lecture
            cur.close()
            conn.close()
        except Exception as e:
            dsn = self._build_connection_string()
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: échec test_connection.\n"
                f"  DSN : {dsn}\n"
                f"  Erreur : {type(e).__name__}: {e}"
            ) from e

    def _execute_query_batches(
        self,
        *,
        conn,
        query: str,
        batch_size: int,
        params: Optional[Sequence[Any]] = None,
    ) -> Iterator[Batch]:
        """
        Exécute une requête et yield des batches de Row via fetchmany().

        Notes :
        - Convertit chaque ligne en dict (colonne -> valeur) grâce à cursor.description.
        - Le batch_size est best-effort mais doit rester >= 1.
        """
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"{self.__class__.__name__} [{self.name}]: 'query' doit être un SQL non vide.")
        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError(f"{self.__class__.__name__} [{self.name}]: 'batch_size' doit être un entier >= 1.")

        cur = conn.cursor()
        try:
            if params is None:
                cur.execute(query)
            else:
                cur.execute(query, params)

            # description : liste de tuples (name, type_code, ...). name est en [0].
            desc = cur.description or []
            columns = [d[0] for d in desc]

            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break

                batch: Batch = []
                for r in rows:
                    # r peut être tuple ou autre structure itérable compatible zip.
                    row_dict: Row = dict(zip(columns, r))
                    batch.append(row_dict)

                yield batch
        finally:
            # Toujours fermer le curseur (même si exception)
            try:
                cur.close()
            except Exception:
                pass

    def _get_table_columns(self, *, conn, table: str) -> List[str]:
        """
        Retourne la liste des colonnes d'une table.

        Implémentation :
        - Exécute une requête "0 row" (fournie par la classe fille)
        - Lit cursor.description
        """
        if not isinstance(table, str) or not table.strip():
            raise ValueError(f"{self.__class__.__name__} [{self.name}]: 'table' doit être un nom non vide.")

        query = self._build_columns_query(table.strip())

        cur = conn.cursor()
        try:
            cur.execute(query)
            desc = cur.description or []
            return [d[0] for d in desc]
        finally:
            try:
                cur.close()
            except Exception:
                pass