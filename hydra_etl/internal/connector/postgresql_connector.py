"""
PostgreSQL Connector - Sprint 2 - Version corrigée

Implémentation complète du connector PostgreSQL avec support upsert via ON CONFLICT.

Corrections appliquées:
- Bug 1: Parsing constraint_cols depuis PostgreSQL array format
- Bug 2: Gestion LIKE avec % dans queries paramétrées

Fonctionnalités Sprint 2:
- Extract: requêtes et tables avec pagination LIMIT/OFFSET
- Load: modes append, replace, upsert
- Upsert: ON CONFLICT (key) DO UPDATE avec validation stricte
- Validation pré-flight: vérification contrainte unique réelle
- Schema support: public par défaut, notation schema.table acceptée
- Transaction: 1 batch = 1 transaction, rollback si échec ; en tout ou rien
  (load.atomic, défaut pour replace) : une transaction pour tout le job

Règles critiques:
1. Schema explicite (défaut "public")
2. Validation contrainte unique EXACTE (set matching)
3. Pas d'exclusion automatique colonnes IDENTITY (Sprint 2)
4. Transaction par batch avec rollback
5. psycopg2 + placeholders %s
6. Identifiants validés (alphanumeric + underscore)
7. Performance: executemany (Sprint 2), execute_values (Sprint 3+)
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from hydra_etl.internal.connector.base_db_connector import BaseDBConnector, Batch


def _pg_value(v: Any) -> Any:
    """Valeur liable par psycopg2 : dict / list deviennent du JSON (colonne JSONB)."""
    if isinstance(v, (dict, list)):
        from psycopg2.extras import Json  # type: ignore
        return Json(v)
    return v


def _pg_type(values: List[Any]) -> str:
    """Type PostgreSQL fidèle aux valeurs d'une colonne (création automatique de table).

    Entiers au-delà de 64 bits et décimaux exacts → NUMERIC (jamais de float) ;
    date seule → DATE ; datetime avec fuseau → TIMESTAMPTZ ; dict / list → JSONB.
    """
    import datetime as _dt
    import decimal as _dec
    import numbers as _num
    vals = [v for v in values if v is not None]
    try:
        import math
        vals = [v for v in vals if not (isinstance(v, float) and math.isnan(v))]
    except Exception:  # noqa: BLE001
        pass
    if not vals:
        return "TEXT"
    if all(isinstance(v, bool) for v in vals):
        return "BOOLEAN"
    if all(isinstance(v, _num.Integral) and not isinstance(v, bool) for v in vals):
        return "BIGINT" if all(-2 ** 63 <= int(v) < 2 ** 63 for v in vals) else "NUMERIC"
    if all(isinstance(v, (_dec.Decimal, _num.Integral)) and not isinstance(v, bool) for v in vals):
        return "NUMERIC"
    if all(isinstance(v, _num.Real) and not isinstance(v, (bool, _dec.Decimal)) for v in vals):
        return "DOUBLE PRECISION"
    if all(isinstance(v, _dt.datetime) for v in vals):
        return "TIMESTAMPTZ" if all(v.tzinfo is not None for v in vals) else "TIMESTAMP"
    if all(isinstance(v, _dt.date) and not isinstance(v, _dt.datetime) for v in vals):
        return "DATE"
    if all(isinstance(v, _dt.date) for v in vals):
        return "TIMESTAMP"
    if all(isinstance(v, (dict, list)) for v in vals):
        return "JSONB"
    return "TEXT"


class PostgreSQLConnector(BaseDBConnector):
    """
    Connecteur PostgreSQL avec support upsert ON CONFLICT.
    
    Capabilities:
    - supports_extract: True
    - supports_load: True
    - supports_upsert: True (via ON CONFLICT)
    
    Connection config:
        host: str (défaut "127.0.0.1")
        port: int (défaut 5432)
        user: str (requis)
        password: str (optionnel)
        database: str (requis)
        schema: str (défaut "public")
    
    Extract config:
        query: str OU table: str (exclusif)
        batch_size: int (défaut 10000)
    
    Load config:
        table: str (requis, peut être "schema.table")
        mode: "append" | "replace" | "upsert"
        key: List[str] (requis si mode=upsert)
        batch_size: int (défaut 10000)
    
    Exemples:
        >>> # Extract
        >>> conn.extract_batches(table="users", batch_size=1000)
        
        >>> # Load append
        >>> conn.load_batches(batches, table="users", mode="append")
        
        >>> # Load upsert
        >>> conn.load_batches(batches, table="users", mode="upsert", key=["id"])
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name=name, config=config)
        self._conn_cfg = config.get("connection", {})
        
        # Parser schema si présent dans connection
        self._default_schema = self._conn_cfg.get("schema", "public")
    
    # ============================================================
    # Capabilities
    # ============================================================
    
    def supports_extract(self) -> bool:
        return True
    
    def supports_load(self) -> bool:
        return True
    
    def get_capabilities(self) -> Dict[str, Any]:
        return {
            "supports_extract": True,
            "supports_load": True,
            "supports_upsert": True,
            "supports_incremental": False,  # Sprint 3+
        }
    
    # ============================================================
    # Connection
    # ============================================================
    
    def _connect(self):
        """
        Établit une connexion PostgreSQL via psycopg2.
        
        Returns:
            Connection psycopg2 avec autocommit=False
        
        Raises:
            ValueError: Si driver manquant ou connexion échoue
        """
        try:
            import psycopg2  # type: ignore
            import psycopg2.extras  # type: ignore
        except ImportError as e:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: driver missing. "
                f"Install it with 'pip install \"hydra-etl[postgres]\"'. "
                f"Error: {e}"
            ) from e
        
        cfg = self._conn_cfg
        
        host = cfg.get("host", "127.0.0.1")
        port = int(cfg.get("port", 5432))
        user = cfg.get("user")
        password = cfg.get("password")
        database = cfg.get("database")
        
        # Validation
        if not user:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'connection.user' is required."
            )
        if not database:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'connection.database' is required."
            )
        
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                # Options PostgreSQL
                options=f"-c search_path={self._default_schema}",
                cursor_factory=psycopg2.extras.RealDictCursor,  # dict rows
            )
            conn.autocommit = False  # Transaction explicite
            return conn
        except Exception as e:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: database connection failed.\n"
                f"  DSN : {self._build_connection_string()}\n"
                f"  Error: {type(e).__name__}: {e}"
            ) from e
    
    def _build_connection_string(self) -> str:
        """DSN lisible pour diagnostics (sans mot de passe)."""
        cfg = self._conn_cfg
        host = cfg.get("host", "127.0.0.1")
        port = cfg.get("port", 5432)
        user = cfg.get("user", "?")
        database = cfg.get("database", "?")
        schema = cfg.get("schema", "public")
        return f"postgresql://{user}:***@{host}:{port}/{database}?schema={schema}"
    
    def _build_columns_query(self, table: str) -> str:
        """
        Requête d'inspection des colonnes.
        
        Retourne une requête qui permet d'obtenir la liste des colonnes de la table.
        PostgreSQL: SELECT * FROM table LIMIT 0
        
        Args:
            table: Nom de la table (peut être "schema.table")
        
        Returns:
            Requête SQL pour inspecter les colonnes
        """
        schema, table_name = self._parse_table(table)
        return f'SELECT * FROM {self._quote_identifier(schema, table_name)} LIMIT 0'
    
    # ============================================================
    # Extract
    # ============================================================
    
    def extract_batches(
        self,
        *,
        query: Optional[str] = None,
        table: Optional[str] = None,
        batch_size: int = 10_000,
        incremental: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Batch]:
        """
        Extrait des batches depuis PostgreSQL.
        
        Args:
            query: Requête SQL custom (prioritaire sur table)
            table: Nom de table (peut être "schema.table")
            batch_size: Taille des batches
            incremental: Non supporté Sprint 2
        
        Yields:
            Batch: Liste de dict {colonne: valeur}
        
        Raises:
            ValueError: Si paramètres invalides ou erreur SQL
        """
        if incremental:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'incremental' is not supported yet."
            )
        
        if not query and not table:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"'query' or 'table' is required to extract."
            )
        
        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'batch_size' must be >= 1."
            )
        
        conn = self._connect()
        try:
            # Cas 1: query custom
            if query:
                yield from self._execute_query_batches(
                    conn=conn, 
                    query=query.strip(), 
                    batch_size=batch_size
                )
                return
            
            # Cas 2: table avec pagination
            assert table is not None
            schema, table_name = self._parse_table(table.strip())
            offset = 0
            
            while True:
                sql = f'SELECT * FROM {self._quote_identifier(schema, table_name)} LIMIT %s OFFSET %s'
                
                emitted_any = False
                for batch in self._execute_query_batches(
                    conn=conn,
                    query=sql,
                    params=(batch_size, offset),
                    batch_size=batch_size,
                ):
                    emitted_any = True
                    yield batch
                
                if not emitted_any:
                    break
                
                offset += batch_size
        
        except Exception as e:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: extraction failed.\n"
                f"  Table/Query : {table or query[:50]}\n"
                f"  Error: {type(e).__name__}: {e}"
            ) from e
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
    def _execute_query_batches(
        self,
        *,
        conn,
        query: str,
        params: Optional[Tuple] = None,
        batch_size: int,
    ) -> Iterator[Batch]:
        """
        Exécute une requête et yield les résultats par batches.
        
        Utilise fetchmany pour streaming efficace.
        
        CORRECTION BUG 2: Gestion correcte des params pour éviter erreur avec LIKE %
        """
        cursor = conn.cursor()
        try:
            # Si pas de params, ne pas passer de tuple vide pour éviter erreur avec %
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                
                # Convertir RealDictRow en dict standard
                batch = [dict(row) for row in rows]
                yield batch
        
        finally:
            cursor.close()
    
    # ============================================================
    # Load
    # ============================================================
    
    # ============================================================
    # Load (session par job : base_db_connector.DBLoadSession)
    # ============================================================

    _wrap_load_value_errors = False

    def _check_load_args(self, table: str, mode: str, key: Optional[List[str]]):
        if not isinstance(table, str) or not table.strip():
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'table' must be a non-empty name."
            )
        table = table.strip()
        self._parse_table(table)
        if mode not in ("append", "replace", "upsert"):
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: mode '{mode}' is not supported. "
                f"Supported: append, replace, upsert."
            )
        if mode == "upsert":
            if not key or not all(isinstance(k, str) and k.strip() for k in key):
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"mode=upsert requires 'key' (a non-empty list of columns)."
                )
            key = [k.strip() for k in key]
        return table, key

    def _load_prepare(self, cur, *, table, mode, key, atomic, commit, update_columns=None, **_):
        """replace : TRUNCATE si la table existe (annulable : en tout ou rien,
        dans la transaction du job), création au 1er lot sinon. upsert :
        vérification de la contrainte unique."""
        schema, table_name = self._parse_table(table)
        ctx = {"schema": schema, "table": table_name, "mode": mode, "key": key,
               "update_columns": update_columns, "columns": None, "create": False}
        if mode == "append":
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s)",
                (schema, table_name),
            )
            if not cur.fetchone()["exists"]:
                ctx["create"] = True          # table absente → créée au 1er lot (comme replace / upsert)
        if mode == "replace":
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s)",
                (schema, table_name),
            )
            if cur.fetchone()["exists"]:
                cur.execute(f'TRUNCATE TABLE {self._quote_identifier(schema, table_name)}')
            else:
                ctx["create"] = True          # table absente → créer au 1er lot
        if mode == "upsert":
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s)",
                (schema, table_name),
            )
            if cur.fetchone()["exists"]:
                self._validate_upsert_key(cursor=cur, schema=schema, table=table_name, key=key)
            else:
                ctx["create"] = True          # table absente → créée au 1er lot, clé primaire = key
        return ctx

    def _load_write(self, cur, ctx, batch, *, commit):
        schema, table_name, mode = ctx["schema"], ctx["table"], ctx["mode"]
        changes = None
        if mode == "upsert" and batch and isinstance(batch[0], dict) and "_op" in batch[0]:
            # lot d'une source CDC : suppressions et mises à jour partielles à part
            batch, changes = self._split_changes(batch, ctx["key"])
            if not batch:
                self._apply_changes(cur, ctx, changes)
                return
        if ctx["columns"] is None:
            ctx["columns"] = self._infer_columns_from_batch(batch)
            if ctx["create"]:
                # DDL transactionnel en PostgreSQL : annulé avec le reste en tout ou rien
                self._auto_create_table(cur, schema, table_name, ctx["columns"], batch,
                                        key=ctx["key"] if mode == "upsert" else None)
                commit()
                ctx["create"] = False
            uc = ctx["update_columns"]
            if mode == "upsert" and uc is not None:
                overlap = set(uc) & set(ctx["key"])
                if overlap:
                    raise ValueError(
                        f"{self.__class__.__name__} [{self.name}]: "
                        f"update_columns cannot contain key columns: {overlap}"
                    )
        self._check_int_ranges(cur, ctx, batch)
        if mode == "upsert":
            sql, values = self._build_upsert_sql(
                schema=schema, table=table_name, columns=ctx["columns"], key=ctx["key"],
                batch=batch, update_columns=ctx["update_columns"],
            )
        else:
            sql, values = self._build_insert_sql(
                schema=schema, table=table_name, columns=ctx["columns"], batch=batch,
            )
        self._write_rows(cur, sql, values, mode=mode, key=ctx["key"], columns=ctx["columns"])
        if changes is not None:
            self._apply_changes(cur, ctx, changes)

    # ── Changements d'une source CDC (colonne _op) appliqués en upsert ──
    _CDC_COLUMNS = ("_op", "_lsn", "_commit_time")

    def _split_changes(self, batch, key):
        """État final de chaque clé dans le lot (le dernier changement l'emporte) :
        lignes à écrire en upsert, clés à supprimer, mises à jour partielles
        (valeur TOAST inchangée, absente du journal)."""
        from hydra_etl.internal.connector.postgresql_cdc_connector import UNCHANGED
        final: Dict[tuple, Tuple[str, Dict[str, Any]]] = {}
        for row in batch:
            k = tuple(row.get(c) for c in key)
            if any(v is None for v in k):
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: a change has no value for the key "
                    f"{list(key)}; the source table needs a primary key (or REPLICA IDENTITY FULL)")
            data = {c: v for c, v in row.items() if c not in self._CDC_COLUMNS}
            if row.get("_op") == "delete":
                final.pop(k, None)
                final[k] = ("delete", data)
                continue
            if any(v is UNCHANGED for v in data.values()):
                prev = final.get(k)
                if prev is not None and prev[0] == "upsert":
                    data = {c: (prev[1].get(c) if v is UNCHANGED else v) for c, v in data.items()}
                    action = "upsert"
                else:
                    action = "partial"
            else:
                action = "upsert"
            final.pop(k, None)
            final[k] = (action, data)
        upserts = [d for a, d in final.values() if a == "upsert"]
        return upserts, {"delete": [k for k, (a, _) in final.items() if a == "delete"],
                         "partial": [d for a, d in final.values() if a == "partial"]}

    def _apply_changes(self, cur, ctx, changes) -> None:
        from hydra_etl.internal.connector.postgresql_cdc_connector import UNCHANGED
        if not changes["delete"] and not changes["partial"]:
            return
        if ctx.get("create"):
            return                      # table pas encore créée : rien à supprimer ni à modifier
        q = self._quote_identifier(ctx["schema"], ctx["table"])
        key = ctx["key"]
        if changes["delete"]:
            from psycopg2.extras import execute_values  # type: ignore
            cols = ", ".join(self._quote_column(k) for k in key)
            if hasattr(cur, "mogrify"):
                execute_values(cur, f"DELETE FROM {q} WHERE ({cols}) IN (VALUES %s)",
                               changes["delete"], page_size=1000)
            else:
                cur.executemany(f"DELETE FROM {q} WHERE ({cols}) = ({', '.join(['%s'] * len(key))})",
                                changes["delete"])
        for row in changes["partial"]:
            sets = [c for c, v in row.items() if c not in key and v is not UNCHANGED]
            if not sets:
                continue
            sql = (f"UPDATE {q} SET " + ", ".join(f"{self._quote_column(c)} = %s" for c in sets)
                   + " WHERE " + " AND ".join(f"{self._quote_column(k)} = %s" for k in key))
            cur.execute(sql, [_pg_value(row[c]) for c in sets] + [row[k] for k in key])

    _VALUES_RE = re.compile(r"VALUES\s*\(\s*(?:%s\s*,\s*)*%s\s*\)")

    def _write_rows(self, cur, sql: str, values: List[Tuple[Any, ...]], *, mode: str,
                    key: Optional[List[str]], columns: List[str]) -> None:
        """Envoie un lot en quelques requêtes multi-lignes (execute_values,
        1 000 lignes par requête) au lieu d'une requête par ligne.

        Exception, pour garder exactement le même résultat : en upsert, un lot
        qui contient deux fois la même clé passe ligne par ligne (une même
        requête ne peut pas mettre à jour deux fois la même ligne)."""
        if not values:
            return
        m = self._VALUES_RE.search(sql)
        if m is None or not hasattr(cur, "mogrify"):     # curseur sans mogrify : doublure de test
            cur.executemany(sql, values)
            return
        if mode == "upsert" and key:
            idx = [columns.index(k) for k in key if k in columns]
            if len(idx) == len(key) and len({tuple(v[i] for i in idx) for v in values}) != len(values):
                cur.executemany(sql, values)
                return
        from psycopg2.extras import execute_values  # type: ignore
        execute_values(cur, sql[:m.start()] + "VALUES %s" + sql[m.end():], values, page_size=1000)

    _INT_RANGES = {"smallint": 2 ** 15, "integer": 2 ** 31, "bigint": 2 ** 63}

    def _check_int_ranges(self, cur, ctx, batch) -> None:
        """Avant d'écrire un lot : un entier qui ne tient pas dans une colonne
        smallint / integer / bigint est signalé avec la colonne, la valeur et
        la correction (au lieu de « bigint out of range » sans contexte)."""
        if "int_cols" not in ctx:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                (ctx["schema"], ctx["table"]),
            )
            ctx["int_cols"] = {r["column_name"]: r["data_type"] for r in cur.fetchall()
                               if r["data_type"] in self._INT_RANGES}
        if not ctx["int_cols"]:
            return
        import numbers
        for i, row in enumerate(batch, 1):
            if not isinstance(row, dict):
                continue
            for col, dtype in ctx["int_cols"].items():
                v = row.get(col)
                if isinstance(v, numbers.Integral) and not isinstance(v, bool):
                    lim = self._INT_RANGES[dtype]
                    if not (-lim <= int(v) < lim):
                        raise ValueError(
                            f"{self.__class__.__name__} [{self.name}]: the value {v} (row {i} of the batch) "
                            f"does not fit in column '{col}', which is {dtype} in "
                            f"{ctx['schema']}.{ctx['table']}. Nothing of this batch was written. "
                            f"Widen the column first, for example:\n"
                            f"  ALTER TABLE {ctx['schema']}.{ctx['table']} ALTER COLUMN {col} TYPE NUMERIC(38,0);")

    # ── Annulation (rollback d'un workflow, voir undo.py) ──────────
    def _q_table(self, table: str) -> str:
        schema, name = self._parse_table(table)
        return self._quote_identifier(schema, name)

    def _q_col(self, column: str) -> str:
        return self._quote_column(column)

    def _bak_ref(self, table: str, bak: str) -> str:
        schema, _ = self._parse_table(table)
        return f"{schema}.{bak}"

    def _table_exists(self, cur, table: str) -> bool:
        schema, name = self._parse_table(table)
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name = %s)", (schema, name))
        return bool(cur.fetchone()["exists"])

    def _backup_table_sql(self, src_q: str, bak_q: str) -> str:
        return f"CREATE TABLE {bak_q} AS TABLE {src_q}"

    def _empty_table_sql(self, q: str) -> str:
        return f"TRUNCATE TABLE {q}"

    def _insert_override(self) -> str:
        return "OVERRIDING SYSTEM VALUE "

    # ============================================================
    # Helpers SQL
    # ============================================================
    
    def _parse_table(self, table: str) -> Tuple[str, str]:
        """
        Parse nom table avec notation schema.table optionnelle.
        
        Args:
            table: "users" ou "sales.users"
        
        Returns:
            (schema, table_name)
        
        Examples:
            >>> _parse_table("users")
            ("public", "users")
            >>> _parse_table("sales.customers")
            ("sales", "customers")
        """
        if "." in table:
            parts = table.split(".", 1)
            return (parts[0].strip(), parts[1].strip())
        else:
            return (self._default_schema, table)
    
    def _validate_identifier(self, name: str) -> str:
        """
        Valide qu'un identifiant est safe (alphanumeric + underscore).
        
        Sprint 2: Validation stricte pour éviter quoting complexe.
        
        Args:
            name: Nom de table/colonne/schema
        
        Returns:
            Name nettoyé
        
        Raises:
            ValueError: Si identifiant invalide
        """
        name = name.strip()
        if not name:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: empty identifier."
            )
        
        # Pattern: lettres, chiffres, underscore. Commence par lettre ou underscore.
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"invalid identifier '{name}'. "
                f"Use only [a-zA-Z0-9_] and start with a letter or an underscore."
            )
        
        return name
    
    def _quote_identifier(self, schema: str, table: str) -> str:
        """
        Quote un identifiant PostgreSQL (schema.table).
        
        Sprint 2: Utilise validation stricte au lieu de quoting complexe.
        
        Args:
            schema: Nom schema validé
            table: Nom table validé
        
        Returns:
            Identifiant quoté "schema"."table"
        """
        schema_clean = self._validate_identifier(schema)
        table_clean = self._validate_identifier(table)
        return f'"{schema_clean}"."{table_clean}"'
    
    def _quote_column(self, column: str) -> str:
        """Quote une colonne PostgreSQL."""
        column_clean = self._validate_identifier(column)
        return f'"{column_clean}"'
    
    def _infer_columns_from_batch(self, batch: Batch) -> List[str]:
        """
        Déduit les colonnes depuis la première ligne du batch.
        
        Args:
            batch: Liste de dict
        
        Returns:
            Liste de noms de colonnes
        
        Raises:
            ValueError: Si batch invalide
        """
        if not batch:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: empty batch."
            )
        
        first = batch[0]
        if not isinstance(first, dict) or not first:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"invalid first row in the batch (expected a non-empty dict)."
            )
        
        cols = list(first.keys())
        # Nettoyage
        cols = [c.strip() for c in cols if isinstance(c, str) and c.strip()]
        
        if not cols:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"no column found in the batch."
            )
        
        return cols
    
    def _auto_create_table(
        self,
        cursor: Any,
        schema: str,
        table: str,
        columns: List[str],
        batch: Batch,
        key: Optional[List[str]] = None,
    ) -> None:
        """Crée la table depuis le premier lot : types déduits de toutes ses
        valeurs (voir _pg_type) ; en upsert, la clé devient la clé primaire."""
        quoted_table = self._quote_identifier(schema, table)
        rows = [r for r in batch if isinstance(r, dict)]
        col_defs = ", ".join(
            f"{self._quote_column(c)} {_pg_type([r.get(c) for r in rows])}" for c in columns
        )
        if key:
            col_defs += f", PRIMARY KEY ({', '.join(self._quote_column(k) for k in key)})"
        cursor.execute(f"CREATE TABLE IF NOT EXISTS {quoted_table} ({col_defs})")

    def _build_insert_sql(
        self,
        *,
        schema: str,
        table: str,
        columns: List[str],
        batch: Batch,
    ) -> Tuple[str, List[Tuple[Any, ...]]]:
        """
        Construit INSERT standard pour mode append/replace.
        
        Args:
            schema: Schema cible
            table: Table cible
            columns: Colonnes à insérer
            batch: Données
        
        Returns:
            (sql, values) pour executemany
        """
        quoted_table = self._quote_identifier(schema, table)
        quoted_cols = ", ".join(self._quote_column(c) for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        
        sql = f"INSERT INTO {quoted_table} ({quoted_cols}) VALUES ({placeholders})"
        
        values: List[Tuple[Any, ...]] = []
        for row in batch:
            if not isinstance(row, dict):
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"invalid row (expected dict), got {type(row).__name__}."
                )
            tup = tuple(_pg_value(row.get(c, None)) for c in columns)
            values.append(tup)
        
        return sql, values
    
    def _build_upsert_sql(
        self,
        *,
        schema: str,
        table: str,
        columns: List[str],
        key: List[str],
        batch: Batch,
        update_columns: Optional[List[str]] = None,
    ) -> Tuple[str, List[Tuple[Any, ...]]]:
        """
        Construit INSERT ... ON CONFLICT ... DO UPDATE pour upsert PostgreSQL.
        
        Syntaxe:
            INSERT INTO table (cols) VALUES (...)
            ON CONFLICT (key_cols) DO UPDATE SET col = EXCLUDED.col, ...
        
        Args:
            schema: Schema cible
            table: Table cible
            columns: Toutes les colonnes du batch
            key: Colonnes clés (doivent matcher une contrainte unique)
            batch: Données
            update_columns: Colonnes à updater (None = toutes sauf key)
        
        Returns:
            (sql, values) pour executemany
        
        Raises:
            ValueError: Si aucune colonne updatable
        """
        # Déterminer colonnes à updater
        if update_columns is not None:
            updatable = update_columns
        else:
            # Par défaut: toutes sauf key
            updatable = [c for c in columns if c not in key]
        
        # Cas limite: aucune colonne updatable → DO NOTHING
        if not updatable:
            return self._build_upsert_do_nothing_sql(
                schema=schema,
                table=table,
                columns=columns,
                key=key,
                batch=batch,
            )
        
        # Construction SQL
        quoted_table = self._quote_identifier(schema, table)
        quoted_cols = ", ".join(self._quote_column(c) for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        
        # ON CONFLICT (key)
        conflict_cols = ", ".join(self._quote_column(k) for k in key)
        
        # DO UPDATE SET
        update_pairs = ", ".join(
            f"{self._quote_column(col)} = EXCLUDED.{self._quote_column(col)}"
            for col in updatable
        )
        
        sql = f"""
INSERT INTO {quoted_table} ({quoted_cols})
VALUES ({placeholders})
ON CONFLICT ({conflict_cols})
DO UPDATE SET {update_pairs}
        """.strip()
        
        # Extraction valeurs
        values: List[Tuple[Any, ...]] = []
        for row in batch:
            if not isinstance(row, dict):
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"invalid row (expected dict), got {type(row).__name__}."
                )
            tup = tuple(_pg_value(row.get(c, None)) for c in columns)
            values.append(tup)
        
        return sql, values
    
    def _build_upsert_do_nothing_sql(
        self,
        *,
        schema: str,
        table: str,
        columns: List[str],
        key: List[str],
        batch: Batch,
    ) -> Tuple[str, List[Tuple[Any, ...]]]:
        """
        Construit INSERT ... ON CONFLICT ... DO NOTHING.
        
        Utilisé quand aucune colonne updatable (colonnes = key uniquement).
        """
        quoted_table = self._quote_identifier(schema, table)
        quoted_cols = ", ".join(self._quote_column(c) for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        conflict_cols = ", ".join(self._quote_column(k) for k in key)
        
        sql = f"""
INSERT INTO {quoted_table} ({quoted_cols})
VALUES ({placeholders})
ON CONFLICT ({conflict_cols})
DO NOTHING
        """.strip()
        
        values: List[Tuple[Any, ...]] = []
        for row in batch:
            tup = tuple(_pg_value(row.get(c, None)) for c in columns)
            values.append(tup)
        
        return sql, values
    
    def _validate_upsert_key(
        self,
        *,
        cursor,
        schema: str,
        table: str,
        key: List[str],
    ) -> None:
        """
        Valide que la key correspond à une contrainte unique RÉELLE.
        
        CORRECTION BUG 1: Parsing correct des constraint_cols depuis PostgreSQL
        
        Règles:
        - Recherche PRIMARY KEY ou UNIQUE sur la table
        - Match EXACT des colonnes (set equality, ordre ignoré)
        - Refuse index partiels (WHERE clause)
        - Refuse index sur expressions
        
        Args:
            cursor: Cursor psycopg2
            schema: Schema cible
            table: Table cible
            key: Colonnes clés du YAML
        
        Raises:
            ValueError: Si aucune contrainte valide trouvée
        """
        # Requête constraints PRIMARY KEY / UNIQUE
        query = """
            SELECT 
                tc.constraint_name,
                array_agg(kcu.column_name::text ORDER BY kcu.ordinal_position) as constraint_cols
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
              AND tc.table_name = kcu.table_name
            WHERE tc.table_schema = %s
              AND tc.table_name = %s
              AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
            GROUP BY tc.constraint_name
        """
        
        cursor.execute(query, (schema, table))
        constraints = cursor.fetchall()
        
        if not constraints:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"upsert impossible: no PRIMARY KEY/UNIQUE constraint on {schema}.{table}.\n"
                f"Action required:\n"
                f"  CREATE UNIQUE INDEX idx_{table}_{'_'.join(key)} ON {schema}.{table}({', '.join(key)});"
            )
        
        # Vérifier match exact
        key_set = set(key)
        
        for constraint in constraints:
            constraint_name = constraint["constraint_name"]
            constraint_cols = constraint["constraint_cols"]
            if set(constraint_cols) == key_set:
                return  # Contrainte valide trouvee — match exact

        # Aucune contrainte ne correspond aux colonnes key
        available = ', '.join(
            f"{c['constraint_name']}({', '.join(c['constraint_cols'])})" for c in constraints
        )
        raise ValueError(
            f"{self.__class__.__name__} [{self.name}]: "
            f"no PRIMARY KEY/UNIQUE constraint matches key={list(key)}.\n"
            f"Constraints available on {schema}.{table}: {available}\n"
            f"Action required: CREATE UNIQUE INDEX idx_{table}_{'_'.join(key)} "
            f"ON {schema}.{table}({', '.join(key)});"
        )