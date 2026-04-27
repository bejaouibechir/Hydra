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
- Transaction: 1 batch = 1 transaction, rollback si échec

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

from internal.connector.base_db_connector import BaseDBConnector, Batch


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
                f"{self.__class__.__name__} [{self.name}]: driver manquant. "
                f"Installez 'psycopg2-binary'. Erreur: {e}"
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
                f"{self.__class__.__name__} [{self.name}]: 'connection.user' est requis."
            )
        if not database:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'connection.database' est requis."
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
                f"{self.__class__.__name__} [{self.name}]: échec connexion DB.\n"
                f"  DSN : {self._build_connection_string()}\n"
                f"  Erreur : {type(e).__name__}: {e}"
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
                f"{self.__class__.__name__} [{self.name}]: 'incremental' non supporté Sprint 2."
            )
        
        if not query and not table:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"fournir 'query' ou 'table' pour extract_batches."
            )
        
        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'batch_size' doit être >= 1."
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
                f"{self.__class__.__name__} [{self.name}]: échec extraction.\n"
                f"  Table/Query : {table or query[:50]}\n"
                f"  Erreur : {type(e).__name__}: {e}"
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
    
    def load_batches(
        self,
        batches: Iterable[Batch],
        *,
        table: str,
        mode: str = "append",
        key: Optional[List[str]] = None,
        update_columns: Optional[List[str]] = None,
    ) -> None:
        """
        Charge des batches vers PostgreSQL.
        
        Args:
            batches: Itérable de batches (list[dict])
            table: Nom table (peut être "schema.table")
            mode: "append" | "replace" | "upsert"
            key: Colonnes clés pour upsert (requis si mode=upsert)
            update_columns: Colonnes à updater (défaut: toutes sauf key)
        
        Raises:
            ValueError: Si validation échoue ou erreur SQL
        
        Transaction:
            - 1 batch = 1 transaction
            - Rollback si échec, job s'arrête
        """
        # Validation
        if not isinstance(table, str) or not table.strip():
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'table' doit être un nom non vide."
            )
        
        table = table.strip()
        schema, table_name = self._parse_table(table)
        
        if mode not in ("append", "replace", "upsert"):
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: mode '{mode}' non supporté. "
                f"Supportés: append, replace, upsert."
            )
        
        if mode == "upsert":
            if not key or not all(isinstance(k, str) and k.strip() for k in key):
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"mode=upsert exige 'key' (liste de colonnes non vides)."
                )
            # Nettoyer key
            key = [k.strip() for k in key]
        
        conn = self._connect()
        try:
            cursor = conn.cursor()
            
            # Replace: TRUNCATE avant le premier batch
            if mode == "replace":
                truncate_sql = f'TRUNCATE TABLE {self._quote_identifier(schema, table_name)}'
                cursor.execute(truncate_sql)
                conn.commit()
            
            # Upsert: validation pré-flight contrainte unique
            if mode == "upsert":
                self._validate_upsert_key(
                    cursor=cursor,
                    schema=schema,
                    table=table_name,
                    key=key
                )
            
            # Traitement des batches
            first_columns: Optional[List[str]] = None
            
            for batch in batches:
                if not batch:
                    continue
                
                # Détecter colonnes du premier batch
                if first_columns is None:
                    first_columns = self._infer_columns_from_batch(batch)
                    
                    # Validation update_columns si fourni
                    if mode == "upsert" and update_columns is not None:
                        overlap = set(update_columns) & set(key)
                        if overlap:
                            raise ValueError(
                                f"{self.__class__.__name__} [{self.name}]: "
                                f"update_columns ne peut pas contenir des colonnes key: {overlap}"
                            )
                
                # Construire SQL selon mode
                if mode == "upsert":
                    sql, values = self._build_upsert_sql(
                        schema=schema,
                        table=table_name,
                        columns=first_columns,
                        key=key,
                        batch=batch,
                        update_columns=update_columns,
                    )
                else:
                    # append ou replace (après truncate)
                    sql, values = self._build_insert_sql(
                        schema=schema,
                        table=table_name,
                        columns=first_columns,
                        batch=batch,
                    )
                
                # Exécution avec transaction par batch
                try:
                    cursor.executemany(sql, values)
                    conn.commit()  # ✅ COMMIT si batch OK
                except Exception as e:
                    conn.rollback()  # ✅ ROLLBACK batch entier
                    raise ValueError(
                        f"{self.__class__.__name__} [{self.name}]: échec chargement batch.\n"
                        f"  Table : {schema}.{table_name}\n"
                        f"  Mode  : {mode}\n"
                        f"  Erreur : {type(e).__name__}: {e}"
                    ) from e
            
            cursor.close()
        
        except Exception as e:
            # Rollback best-effort
            try:
                conn.rollback()
            except Exception:
                pass
            
            # Si erreur pas encore ValueError, wrapper
            if not isinstance(e, ValueError):
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: échec chargement.\n"
                    f"  Table : {schema}.{table_name}\n"
                    f"  Mode  : {mode}\n"
                    f"  Erreur : {type(e).__name__}: {e}"
                ) from e
            else:
                raise
        
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
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
                f"{self.__class__.__name__} [{self.name}]: identifiant vide."
            )
        
        # Pattern: lettres, chiffres, underscore. Commence par lettre ou underscore.
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"identifiant invalide '{name}'. "
                f"Utilisez uniquement [a-zA-Z0-9_] et commencez par lettre/underscore."
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
                f"{self.__class__.__name__} [{self.name}]: batch vide."
            )
        
        first = batch[0]
        if not isinstance(first, dict) or not first:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"première ligne du batch invalide (attendu dict non vide)."
            )
        
        cols = list(first.keys())
        # Nettoyage
        cols = [c.strip() for c in cols if isinstance(c, str) and c.strip()]
        
        if not cols:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"aucune colonne détectée dans le batch."
            )
        
        return cols
    
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
                    f"row invalide (attendu dict), reçu {type(row).__name__}."
                )
            tup = tuple(row.get(c, None) for c in columns)
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
                    f"row invalide (attendu dict), reçu {type(row).__name__}."
                )
            tup = tuple(row.get(c, None) for c in columns)
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
            tup = tuple(row.get(c, None) for c in columns)
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
                array_agg(kcu.column_name ORDER BY kcu.ordinal_position) as constraint_cols
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
                f"Upsert impossible: aucune contrainte PRIMARY KEY/UNIQUE sur {schema}.{table}.\n"
                f"Action requise:\n"
                f"  CREATE UNIQUE INDEX idx_{table}_{'_'.join(key)} ON {schema}.{table}({', '.join(key)});"
            )
        
        # Vérifier match exact
        key_set = set(key)
        
        for constraint in constraints:
            # CORRECTION BUG 1: Parser constraint_cols correctement
            # PostgreSQL peut retourner soit une liste Python, soit une string array "{id}" ou "{region,product_id}"
            constraint_cols = constraint['constraint_cols']
            
            # Convertir en liste Python
            if isinstance(constraint_cols, list):
                # Déjà une liste Python (cas normal avec RealDictCursor)
                constraint_cols_list = constraint_cols
            elif isinstance(constraint_cols, str):
                # String PostgreSQL array format: "{id}" ou "{region,product_id}"
                # Enlever les accolades et split par virgule
                constraint_cols_list = constraint_cols.strip('{}').split(',')
            else:
                # Fallback: essayer de convertir en liste
                try:
                    constraint_cols_list = list(constraint_cols)
                except:
                    constraint_cols_list = [str(constraint_cols)]
            
            # Nettoyer les espaces
            constraint_cols_list = [col.strip() for col in constraint_cols_list]
            constraint_cols_set = set(constraint_cols_list)
            
            if constraint_cols_set == key_set:
                # ✅ Match exact trouvé
                return
        
        # ❌ Aucun match exact
        available = [
            f"{c['constraint_name']}: {c['constraint_cols']}"
            for c in constraints
        ]
        
        raise ValueError(
            f"{self.__class__.__name__} [{self.name}]: "
            f"Upsert impossible: key={key} ne correspond à aucune contrainte unique.\n"
            f"Table: {schema}.{table}\n"
            f"Contraintes disponibles:\n" +
            "\n".join(f"  - {a}" for a in available) +
            f"\n\nAction requise:\n"
            f"  CREATE UNIQUE INDEX idx_{table}_{'_'.join(key)} ON {schema}.{table}({', '.join(key)});"
        )