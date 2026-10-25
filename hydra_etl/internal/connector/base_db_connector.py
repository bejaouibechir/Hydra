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
- begin_load() / load_batches() : session de chargement (load_session.py) —
  une connexion par job ; sans tout ou rien, commit après chaque lot ; en
  tout ou rien, une seule transaction validée par publish(). Les classes
  filles fournissent _check_load_args(), _load_prepare() et _load_write().
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Sequence

from hydra_etl.internal.connector.interface import Batch, Connector, Row
from hydra_etl.internal.connector.load_session import ATOMIC_MODES_ALL, LoadSession


class DBLoadSession(LoadSession):
    """Chargement d'une table par un job, sur une seule connexion."""

    def __init__(self, connector: "BaseDBConnector", *, table: str, mode: str,
                 key: Optional[List[str]], atomic: bool, **extra: Any) -> None:
        super().__init__(target=connector._load_target(table), table=table, mode=mode, atomic=atomic)
        self._c = connector
        self.conn = None
        self.cur = None
        self.ctx: Dict[str, Any] = {}
        try:
            self.conn = connector._connect()
            self.cur = self.conn.cursor()
            self.ctx = connector._load_prepare(self.cur, table=table, mode=mode, key=key,
                                               atomic=atomic, commit=self._commit, **extra)
            self._commit()
        except BaseException as e:
            self.abort()
            err = connector._load_error(e, table, mode) if isinstance(e, Exception) else e
            if err is e:
                raise
            raise err from e

    def _commit(self) -> None:
        """Valide maintenant, sauf en tout ou rien (validation à publish())."""
        if not self.atomic:
            self.conn.commit()

    def _stage(self, batch: Batch) -> None:
        try:
            self._c._load_write(self.cur, self.ctx, batch, commit=self._commit)
            self._commit()
        except Exception as e:
            try:
                self.conn.rollback()        # le lot en cours (ou tout, en tout ou rien)
            except Exception:
                pass
            err = self._c._load_error(e, self.table, self.mode, batch=True)
            if err is e:
                raise
            raise err from e

    def _publish(self) -> None:
        self.conn.commit()
        self._close()

    def _abort(self) -> None:
        try:
            if self.conn is not None:
                self.conn.rollback()
            self._c._load_aborted(self.ctx)
        finally:
            self._close()

    def _close(self) -> None:
        for obj in (self.cur, self.conn):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
        self.cur = self.conn = None


class BaseDBConnector(Connector):
    """
    Base class DB volontairement très mince.

    Règles :
    - Ne dépend d'aucun driver (mysql-connector, psycopg2, cx_Oracle, etc.).
    - Les classes filles fournissent la connexion et les requêtes spécifiques.
    - Toutes les erreurs sont normalisées en ValueError pour cohérence côté core.
    """

    # Une seule transaction pour tout le job : possible dans les trois modes ;
    # par défaut pour replace seulement (append/upsert : `load.atomic: true`).
    atomic_load_modes = ATOMIC_MODES_ALL
    atomic_default_modes = frozenset({"replace"})

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        # Constructeur standard (contrat Connector)
        super().__init__(name=name, config=config)

        # On extrait la section connection (le parser doit la garantir, mais on reste safe).
        connection = config.get("connection")
        if not isinstance(connection, dict):
            raise ValueError(f"{self.__class__.__name__} [{self.name}]: 'connection' must be a mapping (dict).")

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
                f"{self.__class__.__name__} [{self.name}]: connection test failed.\n"
                f"  DSN : {dsn}\n"
                f"  Error: {type(e).__name__}: {e}"
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
            raise ValueError(f"{self.__class__.__name__} [{self.name}]: 'query' must be a non-empty SQL string.")
        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError(f"{self.__class__.__name__} [{self.name}]: 'batch_size' must be an integer >= 1.")

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
            raise ValueError(f"{self.__class__.__name__} [{self.name}]: 'table' must be a non-empty name.")

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
    # ------------------------------------------------------------------
    # Chargement (session par job, voir load_session.py)
    # ------------------------------------------------------------------

    def begin_load(self, *, table: str, mode: str = "append",
                   key: Optional[List[str]] = None, atomic: bool = False, **extra: Any) -> DBLoadSession:
        table, key = self._check_load_args(table, mode, key)
        return DBLoadSession(self, table=table, mode=mode, key=key, atomic=atomic, **extra)

    def load_batches(self, batches: Iterable[Batch], *, table: str, mode: str = "append",
                     key: Optional[List[str]] = None, **extra: Any) -> None:
        """Charge des lots (lot par lot validés, comportement historique)."""
        session = self.begin_load(table=table, mode=mode, key=key, atomic=False, **extra)
        try:
            for batch in batches:
                session.stage(batch)
            session.publish()
        except BaseException:
            session.abort()
            raise

    def _load_target(self, table: str) -> str:
        """Clé du verrou de destination : base + table."""
        try:
            dsn = self._build_connection_string()
        except Exception:
            dsn = self.name
        return f"{self.__class__.__name__}:{dsn}:{table}"

    def _check_load_args(self, table: str, mode: str, key: Optional[List[str]]):
        """Valide table / mode / key AVANT toute connexion ; renvoie (table, key)."""
        raise NotImplementedError

    def _load_prepare(self, cur, *, table: str, mode: str, key: Optional[List[str]],
                      atomic: bool, commit: Callable[[], None], **extra: Any) -> Dict[str, Any]:
        """Avant le premier lot (vider la table en replace, vérifier la clé
        d'upsert…). Renvoie le contexte passé à _load_write."""
        raise NotImplementedError

    def _load_write(self, cur, ctx: Dict[str, Any], batch: Batch, *,
                    commit: Callable[[], None]) -> None:
        """Écrit un lot (sans valider : la session s'en charge)."""
        raise NotImplementedError

    def _load_aborted(self, ctx: Dict[str, Any]) -> None:
        """Après rollback d'un chargement abandonné (ex. table créée hors transaction)."""
        return None

    # False : un ValueError déjà explicite passe tel quel (PostgreSQL) ;
    # True : tout est enveloppé dans « load failed » (MySQL, SQL Server).
    _wrap_load_value_errors = True

    def _load_error(self, e: Exception, table: str, mode: str, batch: bool = False) -> ValueError:
        if (not self._wrap_load_value_errors and isinstance(e, ValueError)
                and f"[{self.name}]" in str(e)):
            return e
        if isinstance(e, ValueError) and str(e).startswith(f"{self.__class__.__name__} [{self.name}]: load failed"):
            return e
        what = "batch load failed" if batch else "load failed"
        return ValueError(
            f"{self.__class__.__name__} [{self.name}]: {what}.\n"
            f"  Table : {table}\n"
            f"  Mode  : {mode}\n"
            f"  Error: {type(e).__name__}: {e}"
        )
