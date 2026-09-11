"""
Connecteur MySQL/MariaDB - Version Sprint 1 avec support upsert.

Changements Sprint 1 (Backlogs 2.1, 2.2):
- Ajout _build_upsert_sql() pour génération SQL upsert
- Ajout _validate_upsert_params() pour validation
- Modification load_batches() pour supporter mode upsert
- Support clés simples et composites
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Iterator, Tuple, Sequence
from hydra_etl.internal.connector.base_db_connector import BaseDBConnector
from hydra_etl.internal.connector.interface import Batch


class MySQLMariaDBConnector(BaseDBConnector):
    """
    Connecteur unique pour MySQL et MariaDB.
    
    Version Sprint 1:
    - Support modes: append, replace, upsert
    - Upsert via INSERT ... ON DUPLICATE KEY UPDATE
    - Clés simples et composites
    
    Notes:
    - MySQL & MariaDB compatibles au niveau protocole/SQL
    - Un seul connecteur pour les deux
    """
    
    # ============================================================
    # Connexion / DSN / introspection
    # ============================================================
    
    def _connect(self):
        """
        Ouvre une connexion via mysql-connector-python.
        
        Configuration:
        - Encodage utf8mb4 par défaut
        - autocommit=False (commit explicite)
        - Password non loggé
        """
        try:
            import mysql.connector  # type: ignore
        except Exception as e:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: driver manquant. "
                f"Installez 'mysql-connector-python'. Erreur: {type(e).__name__}: {e}"
            ) from e
        
        cfg = self._conn_cfg
        
        host = cfg.get("host", "127.0.0.1")
        port = int(cfg.get("port", 3306))
        user = cfg.get("user")
        password = cfg.get("password")
        database = cfg.get("database")
        
        # Validation
        if not user:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'connection.user' requis"
            )
        if not database:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'connection.database' requis"
            )
        
        try:
            conn = mysql.connector.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                charset="utf8mb4",
                # Collation compatible MySQL ET MariaDB. Sans ce paramètre,
                # mysql-connector-python 8.x négocie 'utf8mb4_0900_ai_ci'
                # (défaut MySQL 8) que MariaDB ne connaît pas -> erreur 1273.
                collation="utf8mb4_general_ci",
                use_unicode=True,
                autocommit=False,
            )
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
        port = cfg.get("port", 3306)
        user = cfg.get("user", "?")
        database = cfg.get("database", "?")
        return f"mysql://{user}:***@{host}:{port}/{database}"
    
    def _build_columns_query(self, table: str) -> str:
        """Requête d'inspection des colonnes."""
        return f"SELECT * FROM {self._q(table)} LIMIT 0"
    
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
        Produit des batches de Row (dict colonne → valeur).
        
        MVP:
        - incremental ignoré (support reporté)
        """
        if incremental:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"incremental extraction non supporté (reporté)"
            )
        
        if query and table:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"'query' et 'table' mutuellement exclusifs"
            )
        
        if not query and not table:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"'query' ou 'table' requis"
            )
        
        # Construire requête
        if query:
            sql = query.strip()
        else:
            sql = f"SELECT * FROM {self._q(table.strip())}"
        
        # Exécuter et streamer
        conn = self._connect()
        try:
            yield from self._execute_query_batches(
                conn=conn,
                query=sql,
                batch_size=batch_size,
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
    # ============================================================
    # Load - Version Sprint 1 avec upsert
    # ============================================================
    
    def load_batches(
        self,
        batches: Iterable[Batch],
        *,
        table: str,
        mode: str = "append",
        key: Optional[List[str]] = None,
    ) -> None:
        """
        Charge des batches vers MySQL/MariaDB.
        
        Modes supportés (Sprint 1):
        - append: INSERT simple
        - replace: TRUNCATE puis INSERT
        - upsert: INSERT ... ON DUPLICATE KEY UPDATE
        
        Args:
            batches: Iterable de batches (listes de dicts)
            table: Nom de la table cible
            mode: Mode de chargement (append|replace|upsert)
            key: Colonnes de clé (requis si mode=upsert)
        
        Raises:
            ValueError: Si validation échoue ou erreur SQL
        """
        # Validation table
        if not isinstance(table, str) or not table.strip():
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"'table' doit être un nom non vide"
            )
        table = table.strip()
        
        # Validation mode
        if mode not in ("append", "replace", "upsert"):
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"mode '{mode}' non supporté. "
                f"Supportés: append, replace, upsert"
            )
        
        # Validation upsert → key requis
        if mode == "upsert":
            self._validate_upsert_params(table, key)
        
        conn = self._connect()
        try:
            cur = conn.cursor()
            
            # Mode replace : TRUNCATE avant le premier INSERT
            if mode == "replace":
                cur.execute(f"TRUNCATE TABLE {self._q(table)}")
                conn.commit()
            
            # Insertion batch par batch
            first_columns: Optional[List[str]] = None
            
            for batch in batches:
                # Tolérer batch vide
                if not batch:
                    continue
                
                # Déduire colonnes du premier batch
                if first_columns is None:
                    first_columns = self._infer_columns_from_batch(batch)
                
                # Construire SQL selon mode
                if mode == "upsert":
                    sql, values = self._build_upsert_many_sql(
                        table=table,
                        columns=first_columns,
                        key_columns=key,
                        batch=batch,
                    )
                else:
                    # append ou replace (après TRUNCATE)
                    sql, values = self._build_insert_many_sql(
                        table=table,
                        columns=first_columns,
                        batch=batch,
                    )
                
                # Exécuter
                cur.executemany(sql, values)
                conn.commit()
            
            cur.close()
        
        except Exception as e:
            # Rollback best-effort
            try:
                conn.rollback()
            except Exception:
                pass
            
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: échec chargement.\n"
                f"  Table : {table}\n"
                f"  Mode  : {mode}\n"
                f"  Erreur : {type(e).__name__}: {e}"
            ) from e
        
        finally:
            try:
                conn.close()
            except Exception:
                pass
    
    # ============================================================
    # Helpers SQL - Version Sprint 1 avec upsert
    # ============================================================
    
    def _q(self, identifier: str) -> str:
        """
        Quote un identifiant SQL avec backticks.
        
        Validation minimaliste anti-injection.
        """
        ident = (identifier or "").strip()
        if not ident:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"identifiant SQL vide"
            )
        
        # Interdire caractères dangereux
        forbidden = ["`", ";", "--", "/*", "*/"]
        for x in forbidden:
            if x in ident:
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"identifiant SQL invalide: {identifier!r}"
                )
        
        return f"`{ident}`"
    
    def _infer_columns_from_batch(self, batch: Batch) -> List[str]:
        """
        Déduit colonnes depuis la première ligne du batch.
        
        Python 3.7+ garantit l'ordre d'insertion dict.
        """
        first = batch[0]
        if not isinstance(first, dict) or not first:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"batch invalide (première ligne vide ou non dict)"
            )
        
        cols = list(first.keys())
        # Nettoyage minimal
        cols = [c.strip() for c in cols if isinstance(c, str) and c.strip()]
        
        if not cols:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"aucune colonne détectée dans le batch"
            )
        
        return cols
    
    def _build_insert_many_sql(
        self,
        *,
        table: str,
        columns: List[str],
        batch: Batch
    ) -> Tuple[str, List[Tuple[Any, ...]]]:
        """
        Construit INSERT ... VALUES (%s,...) pour executemany.
        
        Args:
            table: Nom table
            columns: Colonnes cibles (ordre fixe)
            batch: Liste de dicts
        
        Returns:
            (sql, values) pour executemany
        """
        quoted_cols = ", ".join(self._q(c) for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO {self._q(table)} ({quoted_cols}) VALUES ({placeholders})"
        
        values: List[Tuple[Any, ...]] = []
        for row in batch:
            if not isinstance(row, dict):
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"Row invalide (attendu dict), reçu {type(row).__name__}"
                )
            tup = tuple(row.get(c, None) for c in columns)
            values.append(tup)
        
        return sql, values
    
    # ============================================================
    # Méthodes Upsert - Sprint 1 Backlog 2.1
    # ============================================================
    
    def _build_upsert_sql(
        self,
        table: str,
        columns: List[str],
        key_columns: List[str],
    ) -> str:
        """
        Génère SQL INSERT ... ON DUPLICATE KEY UPDATE.
        
        Stratégie:
        - INSERT INTO table (cols) VALUES (%s, ...)
        - ON DUPLICATE KEY UPDATE non_key_cols=VALUES(non_key_cols)
        
        Règles:
        - Clés exclues de UPDATE (pas besoin màj)
        - Support clés simples et composites
        
        Args:
            table: Nom table
            columns: Toutes les colonnes
            key_columns: Colonnes de clé (PK ou UNIQUE)
        
        Returns:
            SQL upsert pour executemany
        
        Raises:
            ValueError: Si validation échoue
        """
        # Validation paramètres
        if not table or not isinstance(table, str):
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"table must be non-empty string"
            )
        
        if not columns or not isinstance(columns, list):
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"columns must be non-empty list"
            )
        
        if not key_columns or not isinstance(key_columns, list):
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"key_columns must be non-empty list for upsert"
            )
        
        # Validation: key_columns dans columns
        key_set = set(key_columns)
        col_set = set(columns)
        
        missing_keys = key_set - col_set
        if missing_keys:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"key columns {sorted(missing_keys)} not found in data columns {sorted(columns)}. "
                f"Key columns must exist in the data."
            )
        
        # Validation: au moins une colonne non-clé
        non_key_columns = [col for col in columns if col not in key_set]
        if not non_key_columns:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"all columns are key columns. Upsert requires at least one non-key column to update. "
                f"Columns: {columns}, Keys: {key_columns}"
            )
        
        # Construction SQL
        table_quoted = self._q(table)
        columns_quoted = ", ".join(self._q(col) for col in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        
        insert_clause = (
            f"INSERT INTO {table_quoted} ({columns_quoted}) "
            f"VALUES ({placeholders})"
        )
        
        # Clause UPDATE : seulement colonnes non-clé
        update_pairs = [
            f"{self._q(col)}=VALUES({self._q(col)})"
            for col in non_key_columns
        ]
        update_clause = ", ".join(update_pairs)
        
        # SQL final
        upsert_sql = f"{insert_clause} ON DUPLICATE KEY UPDATE {update_clause}"
        
        return upsert_sql
    
    def _build_upsert_many_sql(
        self,
        *,
        table: str,
        columns: List[str],
        key_columns: List[str],
        batch: Batch
    ) -> Tuple[str, List[Tuple[Any, ...]]]:
        """
        Construit SQL upsert + values pour executemany.
        
        Combine _build_upsert_sql() avec extraction values du batch.
        
        Args:
            table: Nom table
            columns: Toutes colonnes
            key_columns: Colonnes clé
            batch: Liste de dicts
        
        Returns:
            (sql, values) pour executemany
        """
        sql = self._build_upsert_sql(table, columns, key_columns)
        
        values: List[Tuple[Any, ...]] = []
        for row in batch:
            if not isinstance(row, dict):
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"Row invalide (attendu dict), reçu {type(row).__name__}"
                )
            tup = tuple(row.get(c, None) for c in columns)
            values.append(tup)
        
        return sql, values
    
    def _validate_upsert_params(
        self,
        table: str,
        key_columns: Optional[List[str]],
    ) -> None:
        """
        Valide paramètres pour upsert.
        
        Vérifications:
        - table non vide
        - key_columns non None et non vide
        - key_columns sans strings vides
        
        Args:
            table: Nom table
            key_columns: Colonnes clé
        
        Raises:
            ValueError: Si validation échoue
        """
        # Table validation
        if not table or not isinstance(table, str) or not table.strip():
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"table must be non-empty string"
            )
        
        # Key columns validation
        if key_columns is None:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"key_columns required for upsert mode. "
                f"Specify PRIMARY KEY or UNIQUE KEY columns.\n"
                f"Example: key: [id] or key: [region, product_id]"
            )
        
        if not isinstance(key_columns, list) or not key_columns:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"key_columns cannot be empty for upsert"
            )
        
        # Vérifier pas de strings vides
        for col in key_columns:
            if not col or not isinstance(col, str) or not col.strip():
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"key_columns cannot contain empty strings. Got: {key_columns}"
                )