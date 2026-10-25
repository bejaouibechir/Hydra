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
from hydra_etl.internal.connector.undo import (
    DBUndo, UndoConflict, UndoUnavailable, backup_table_name,
)


class DBLoadSession(LoadSession):
    """Chargement d'une table par un job, sur une seule connexion."""

    def __init__(self, connector: "BaseDBConnector", *, table: str, mode: str,
                 key: Optional[List[str]], atomic: bool, undo: bool = False, **extra: Any) -> None:
        super().__init__(target=connector._load_target(table), table=table, mode=mode, atomic=atomic)
        self._c = connector
        self.conn = None
        self.cur = None
        self.ctx: Dict[str, Any] = {}
        try:
            self.conn = connector._connect()
            self.cur = self.conn.cursor()
            if undo:
                # avant toute écriture : de quoi revenir en arrière (rollback du workflow)
                self.undo_record = connector._undo_begin(self.cur, table, mode, key)
                self._undo_connector = connector
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
            rec = self.undo_record
            if rec is not None and rec.mode in ("append", "upsert") and not rec.created:
                self._c._undo_capture(self.cur, rec, batch)
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
        if self.undo_record is not None:
            self.undo_record.count_after = self._c._count_rows(self.cur, self.table)
        self.conn.commit()
        self._close()

    def _abort(self) -> None:
        try:
            if self.conn is not None:
                self.conn.rollback()
            self._c._load_aborted(self.ctx)
            rec = self.undo_record
            if rec is not None:
                if not self.atomic and self.batches_committed > 0:
                    # échec après des lots déjà validés : le rollback du workflow les annulera
                    rec.partial = True
                    rec.count_after = self._c._count_rows(self.cur, self.table)
                    self.conn.commit()
                else:
                    self._c._discard_undo(rec)
                    self.undo_record = None
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

    # Annulation après publication (rollback d'un workflow, undo.py) : append
    # exige load.key (lignes retrouvées par leur clé).
    undo_load_modes = ATOMIC_MODES_ALL

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

    def begin_load(self, *, table: str, mode: str = "append", key: Optional[List[str]] = None,
                   atomic: bool = False, undo: bool = False, **extra: Any) -> DBLoadSession:
        table, key = self._check_load_args(table, mode, key)
        if undo and mode == "append" and not key:
            raise UndoUnavailable(
                f"{self.__class__.__name__} [{self.name}]: append into '{table}' with rollback: true "
                f"needs load.key (the columns that identify a row), to remove exactly the rows "
                f"this run added")
        return DBLoadSession(self, table=table, mode=mode, key=key, atomic=atomic, undo=undo, **extra)

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

    # ------------------------------------------------------------------
    # Annulation d'un chargement publié (undo.py) — dialecte par crochets
    # ------------------------------------------------------------------

    def _q_table(self, table: str) -> str:
        """Nom de table (éventuellement schema.table) cité pour le SQL."""
        raise NotImplementedError

    def _q_col(self, column: str) -> str:
        raise NotImplementedError

    def _bak_ref(self, table: str, bak: str) -> str:
        """Table de sauvegarde dans le même schéma que `table`."""
        return bak

    def _table_exists(self, cur, table: str) -> bool:
        try:
            cur.execute(self._build_columns_query(table))
            cur.fetchall()
            return True
        except Exception:
            self._reset_after_error(cur)
            return False

    def _reset_after_error(self, cur) -> None:
        """Après une requête en échec dans une transaction (PostgreSQL : transaction
        avortée) ; les autres bases n'ont rien à faire."""
        return None

    def _backup_table_sql(self, src_q: str, bak_q: str) -> str:
        return f"CREATE TABLE {bak_q} AS SELECT * FROM {src_q}"

    def _empty_table_sql(self, q: str) -> str:
        return f"DELETE FROM {q}"

    def _insert_override(self) -> str:
        """PostgreSQL : OVERRIDING SYSTEM VALUE (colonnes GENERATED ALWAYS)."""
        return ""

    def _identity_insert(self, cur, q: str, table: str, on: bool) -> None:
        """SQL Server : SET IDENTITY_INSERT autour d'une remise de lignes."""
        return None

    @staticmethod
    def _rows_as_dicts(cur) -> List[Dict[str, Any]]:
        rows = cur.fetchall() or []
        if rows and isinstance(rows[0], dict):
            return [dict(r) for r in rows]
        cols = [d[0] for d in (cur.description or [])]
        return [dict(zip(cols, r)) for r in rows]

    def _count_rows(self, cur, table: str) -> Optional[int]:
        try:
            cur.execute(f"SELECT COUNT(*) AS n FROM {self._q_table(table)}")
            row = cur.fetchone()
            return int(row["n"] if isinstance(row, dict) else row[0])
        except Exception:
            self._reset_after_error(cur)
            return None

    def _undo_begin(self, cur, table: str, mode: str, key: Optional[List[str]]) -> DBUndo:
        rec = DBUndo(target=table, mode=mode, key=list(key or []))
        if not self._table_exists(cur, table):
            rec.created = True               # annuler = supprimer la table créée par le job
            return rec
        if mode == "replace":
            rec.backup_table = self._bak_ref(table, backup_table_name(table))
            cur.execute(self._backup_table_sql(self._q_table(table), self._q_table(rec.backup_table)))
        return rec

    def _where_keys(self, key: List[str], keys: List[tuple]):
        if len(key) == 1:
            return f"{self._q_col(key[0])} IN ({', '.join(['%s'] * len(keys))})", [k[0] for k in keys]
        one = "(" + " AND ".join(f"{self._q_col(c)} = %s" for c in key) + ")"
        return " OR ".join([one] * len(keys)), [v for k in keys for v in k]

    def _select_by_keys(self, cur, table: str, key: List[str], keys: List[tuple],
                        cols: str = "*") -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            where, params = self._where_keys(key, chunk)
            cur.execute(f"SELECT {cols} FROM {self._q_table(table)} WHERE {where}", params)
            out.extend(self._rows_as_dicts(cur))
        return out

    def _delete_by_keys(self, cur, table: str, key: List[str], keys: List[tuple]) -> None:
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            where, params = self._where_keys(key, chunk)
            cur.execute(f"DELETE FROM {self._q_table(table)} WHERE {where}", params)

    def _undo_capture(self, cur, rec: DBUndo, batch: Batch) -> None:
        """Avant d'écrire un lot : clés insérées (append) ou lignes d'avant (upsert)."""
        rows = [r for r in batch]
        keys = [tuple(r.get(c) for c in rec.key) for r in rows]
        seen = getattr(rec, "_seen", None)
        if seen is None:
            seen = set()
            object.__setattr__(rec, "_seen", seen)
        fresh = list(dict.fromkeys(k for k in keys if k not in seen))
        if not fresh:
            return
        if rec.mode == "append":
            cols = ", ".join(self._q_col(c) for c in rec.key)
            existing = self._select_by_keys(cur, rec.target, rec.key, fresh, cols)
            if existing:
                ex = tuple(existing[0].get(c) for c in rec.key)
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: {len(existing)} row(s) to append "
                    f"have a key already in '{rec.target}' (e.g. {ex}). With rollback: true, "
                    f"append only adds new keys so that they can be removed exactly; use "
                    f"mode: upsert, or remove these rows.")
            rec.inserted_keys.extend([list(k) for k in fresh])
        else:
            existing = self._select_by_keys(cur, rec.target, rec.key, fresh)
            found = {tuple(r.get(c) for c in rec.key) for r in existing}
            rec.old_rows.extend(existing)
            rec.inserted_keys.extend([list(k) for k in fresh if k not in found])
        seen.update(fresh)

    def _restore_rows(self, cur, q: str, table: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        cols = list(rows[0].keys())
        sql = (f"INSERT INTO {q} ({', '.join(self._q_col(c) for c in cols)}) {self._insert_override()}"
               f"VALUES ({', '.join(['%s'] * len(cols))})")
        self._identity_insert(cur, q, table, True)
        try:
            cur.executemany(sql, [tuple(r.get(c) for c in cols) for r in rows])
        finally:
            self._identity_insert(cur, q, table, False)

    def _undo_load(self, rec: DBUndo) -> str:
        """Remet la table dans son état d'avant le job (voir undo.py)."""
        conn = self._connect()
        cur = conn.cursor()
        q = self._q_table(rec.target)
        try:
            if rec.count_after is not None:
                now = self._count_rows(cur, rec.target)
                if now is not None and now != rec.count_after:
                    raise UndoConflict(
                        f"'{rec.target}' changed after this run wrote it ({rec.count_after} rows "
                        f"then, {now} now): not restored, to keep the other changes"
                        + (f"; its previous content is kept in '{rec.backup_table}'"
                           if rec.backup_table else ""))
            if rec.created:
                cur.execute(f"DROP TABLE {q}")
                conn.commit()
                return f"{rec.target}: table removed (created by this run)"
            if rec.mode == "replace":
                bq = self._q_table(rec.backup_table)
                cur.execute(self._build_columns_query(rec.backup_table))
                cols = [d[0] for d in (cur.description or [])]
                cur.fetchall()                       # MySQL : lire le résultat (vide) avant la suite
                cl = ", ".join(self._q_col(c) for c in cols)
                cur.execute(self._empty_table_sql(q))
                self._identity_insert(cur, q, rec.target, True)
                try:
                    cur.execute(f"INSERT INTO {q} ({cl}) {self._insert_override()}SELECT {cl} FROM {bq}")
                finally:
                    self._identity_insert(cur, q, rec.target, False)
                conn.commit()
                cur.execute(f"DROP TABLE {bq}")
                conn.commit()
                return f"{rec.target}: previous content restored"
            keys = [tuple(k) for k in rec.inserted_keys]
            keys += [tuple(r.get(c) for c in rec.key) for r in rec.old_rows]
            self._delete_by_keys(cur, rec.target, rec.key, keys)
            self._restore_rows(cur, q, rec.target, rec.old_rows)
            conn.commit()
            return (f"{rec.target}: {len(rec.inserted_keys)} added row(s) removed"
                    + (f", {len(rec.old_rows)} row(s) restored" if rec.old_rows else ""))
        except BaseException:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                cur.close()
                conn.close()
            except Exception:
                pass

    def _discard_undo(self, rec: DBUndo) -> None:
        """Workflow réussi (ou chargement abandonné) : supprimer la sauvegarde."""
        if not rec.backup_table:
            return
        conn = self._connect()
        cur = conn.cursor()
        try:
            if self._table_exists(cur, rec.backup_table):
                cur.execute(f"DROP TABLE {self._q_table(rec.backup_table)}")
                conn.commit()
        finally:
            try:
                cur.close()
                conn.close()
            except Exception:
                pass
