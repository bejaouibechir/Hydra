"""
Connecteur Microsoft SQL Server.

Pilote : pymssql
-----------------
pymssql embarque FreeTDS dans ses roues binaires : `pip install "hydra-etl[mssql]"`
suffit, sans pilote ODBC système à installer à côté. C'est ce qui permet à SQL Server
de tenir la promesse de Hydra ETL — une commande, rien à déployer. pyodbc, plus
complet (Azure AD, Always Encrypted), exige l'installation séparée de msodbcsql :
il sera ajouté en option si un utilisateur réel le demande, pas avant.

Portabilité
-----------
SQL Server parle TDS sur TCP 1433 quel que soit son système d'accueil : Windows,
conteneur Linux, Docker sur Mac. Le connecteur ne s'en préoccupe pas. Ce qui varie
d'un serveur à l'autre est traité ici :

- **Instances nommées.** Sous Windows on joint souvent `MACHINE\\SQLEXPRESS`, résolu
  par le service SQL Browser. Sous Linux et Docker c'est toujours `hôte:port`. Les
  deux formes sont acceptées, via `host` contenant une barre oblique inverse ou via
  la clé `instance`.
- **Classement.** Les tables créées automatiquement utilisent `NVARCHAR`, jamais
  `VARCHAR` : le même INSERT accentué se comporte alors pareil sur un serveur
  Windows en Latin1 et sur une image Linux en UTF-8.
- **Dates.** `DATETIME2` plutôt que `DATETIME` (précision 3 ms, plage démarrant en
  1753), et `use_datetime2=True` côté pilote pour que la conversion corresponde.
- **Version du protocole.** `tds_version` est exposée : les images récentes et les
  anciennes n'acceptent pas les mêmes.

UPSERT
------
T-SQL a `MERGE`, et c'est la réponse évidente. Elle n'est pas retenue : `MERGE`
traîne des problèmes de concurrence documentés et n'est sûr qu'avec des indications
de verrouillage explicites, au point que beaucoup d'équipes SQL Server l'ont banni.
On fait `UPDATE` puis `INSERT ... WHERE NOT EXISTS` dans une transaction : plus
verbeux, prévisible, et c'est ce qu'un DBA attend de voir.
"""

from __future__ import annotations

import re
import socket
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from hydra_etl.internal.connector.base_db_connector import BaseDBConnector
from hydra_etl.internal.connector.interface import Batch

# Identifiants : on valide strictement plutôt que d'échapper finement, comme le
# connecteur PostgreSQL. Un nom qui sort de ce motif est refusé, pas assaini.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_DEFAULT_SCHEMA = "dbo"
_DEFAULT_PORT = 1433
_SQL_BROWSER_PORT = 1434
_SQL_BROWSER_TIMEOUT = 2.0


def _parse_sql_browser_response(data: bytes, instance: str) -> Optional[int]:
    """Extrait le port TCP d'une reponse SSRP, ou None si elle ne le donne pas.

    Le corps decrit une instance par bloc, chaque bloc etant une suite de
    champs ``cle;valeur`` et se terminant par un double point-virgule ::

        ServerName;MACHINE;InstanceName;SQLEXPRESS;IsClustered;No;
        Version;16.0.1000.6;tcp;14330;;

    Un serveur peut en heberger plusieurs et les decrire toutes dans le meme
    datagramme. D'ou le decoupage en blocs avant le decoupage en champs : lire
    les champs d'un seul tenant desaligne les paires des le second bloc, et on
    rendrait alors le port d'une autre instance. Connecter silencieusement
    l'utilisateur a la mauvaise base serait pire que de ne rien rendre.
    """
    if len(data) < 3 or data[0] != 0x05:
        return None

    wanted = instance.lower()
    for block in data[3:].decode("ascii", errors="replace").split(";;"):
        fields = block.split(";")
        if len(fields) < 2:
            continue
        entries = {
            fields[i].lower(): fields[i + 1] for i in range(0, len(fields) - 1, 2)
        }
        if entries.get("instancename", "").lower() != wanted:
            continue
        raw = entries.get("tcp")
        if raw is None:
            return None  # instance trouvee, mais elle n'ecoute pas en TCP
        try:
            port = int(raw)
        except ValueError:
            return None
        return port if 0 < port < 65536 else None
    return None


def _query_sql_browser(
    host: str, instance: str, timeout: float = _SQL_BROWSER_TIMEOUT
) -> Optional[int]:
    """Demande au service SQL Browser le port TCP d'une instance nommee.

    Protocole SSRP (MS-SQLR) : un datagramme UDP vers le port 1434, dont le
    premier octet 0x04 signifie « decris-moi cette instance ». C'est ce que
    font les pilotes Microsoft et que FreeTDS ne fait pas ; l'implementer ici
    permet de garder pymssql, donc aucun pilote systeme a installer, sans
    imposer a l'utilisateur de trouver le port lui-meme.

    Rend None sans lever d'exception si le service ne repond pas : le port
    1434 est souvent ferme par un pare-feu, et SQL Browser peut etre arrete.
    L'appelant retombe alors sur le message d'aide.
    """
    try:
        request = b"\x04" + instance.encode("ascii")
    except UnicodeEncodeError:
        return None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(timeout)
        sock.sendto(request, (host, _SQL_BROWSER_PORT))
        data, _ = sock.recvfrom(4096)
    except (OSError, socket.timeout):
        return None
    finally:
        sock.close()

    return _parse_sql_browser_response(data, instance)



class SQLServerConnector(BaseDBConnector):
    """Connecteur SQL Server : extraction, chargement, upsert."""

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        super().__init__(name=name, config=config)
        schema = self._conn_cfg.get("schema") or _DEFAULT_SCHEMA
        self._default_schema = self._validate_identifier(str(schema))

    # ============================================================
    # Capacités
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
            "supports_incremental": False,
        }

    # ============================================================
    # Connexion
    # ============================================================

    def _split_instance(self) -> Tuple[str, Optional[str]]:
        """Rend (hôte, instance) — l'instance étant None pour une instance par défaut.

        Deux écritures acceptées :
        - ``host: MACHINE\\SQLEXPRESS``
        - ``host: MACHINE`` + ``instance: SQLEXPRESS``
        """
        cfg = self._conn_cfg
        host = str(cfg.get("host", "127.0.0.1")).strip()
        instance = cfg.get("instance")

        if "\\" in host:
            base, inst = host.split("\\", 1)
            return base.strip(), inst.strip() or None
        if instance:
            return host, self._validate_identifier(str(instance))
        return host, None

    def _resolve_server(self) -> Tuple[str, Optional[int]]:
        """Rend (serveur, port) tel qu'il sera passé à pymssql.

        FreeTDS, embarqué dans pymssql, ne traduit pas un nom d'instance en
        numéro de port : il vise 1433 et ignore le service SQL Browser. Or une
        instance nommée écoute sur un port dynamique, et c'est la configuration
        par défaut de SQL Express — donc du public visé.

        Hydra interroge donc SQL Browser lui-même, en UDP sur le port 1434,
        comme le font les pilotes Microsoft. Trois cas, dans cet ordre :

        - **port explicite** -> on l'utilise tel quel, sans rien demander à
          personne. C'est le chemin le plus rapide et le plus sûr.
        - **instance nommée sans port** -> requête SQL Browser. S'il répond, on
          connecte sur le port obtenu et l'utilisateur n'a rien eu à chercher.
        - **SQL Browser muet** (arrêté, ou UDP 1434 filtré) -> on tente quand
          même ``HOTE\\INSTANCE`` et `_connect` explique quoi faire.

        Le résultat est mémorisé : la construction du DSN appelle aussi cette
        méthode, et une requête réseau par message d'erreur serait absurde.
        """
        cached = getattr(self, "_resolved_server", None)
        if cached is not None:
            return cached

        cfg = self._conn_cfg
        host, instance = self._split_instance()
        explicit_port = cfg.get("port")

        if instance is None:
            result = (host, int(explicit_port or _DEFAULT_PORT))
        elif explicit_port:
            result = (host, int(explicit_port))
        else:
            timeout = float(cfg.get("browser_timeout", _SQL_BROWSER_TIMEOUT))
            discovered = _query_sql_browser(host, instance, timeout)
            if discovered is not None:
                result = (host, discovered)
            else:
                result = (f"{host}\\{instance}", None)

        self._resolved_server = result
        return result

    def _connect(self):
        try:
            import pymssql  # type: ignore
        except Exception as e:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: driver manquant. "
                f"Installez-le avec 'pip install \"hydra-etl[mssql]\"'. "
                f"Erreur: {type(e).__name__}: {e}"
            ) from e

        cfg = self._conn_cfg
        user = cfg.get("user")
        password = cfg.get("password")
        database = cfg.get("database")

        if not user:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'connection.user' requis"
            )
        if not database:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: 'connection.database' requis"
            )

        server, port = self._resolve_server()

        kwargs: Dict[str, Any] = {
            "server": server,
            "user": user,
            "password": password,
            "database": database,
            # UTF-8 de bout en bout : combiné à NVARCHAR côté table, le texte
            # accentué traverse à l'identique quel que soit le classement du serveur.
            "charset": str(cfg.get("charset", "UTF-8")),
            # Conversion des dates alignée sur DATETIME2.
            "use_datetime2": True,
            # Commit explicite, comme les autres connecteurs SQL de Hydra ETL.
            "autocommit": False,
            "appname": "hydra-etl",
            "login_timeout": int(cfg.get("login_timeout", 60)),
        }
        if port is not None:
            kwargs["port"] = port
        if cfg.get("tds_version"):
            kwargs["tds_version"] = str(cfg["tds_version"])
        if cfg.get("timeout") is not None:
            kwargs["timeout"] = int(cfg["timeout"])

        try:
            return pymssql.connect(**kwargs)
        except Exception as e:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: échec connexion DB.\n"
                f"  DSN : {self._build_connection_string()}\n"
                f"  Erreur : {type(e).__name__}: {e}"
                f"{self._named_instance_hint()}"
            ) from e

    def _named_instance_hint(self) -> str:
        """Conseil affiché quand une instance nommée est tentée sans port.

        Sans ce message, l'utilisateur ne voit qu'une erreur FreeTDS qui ne cite
        même pas le nom de l'instance, et n'a aucune piste.
        """
        _, instance = self._split_instance()
        if instance is None or self._conn_cfg.get("port"):
            return ""
        host, _ = self._split_instance()
        return (
            f"\n"
            f"  Instance nommée '{instance}' : Hydra a interrogé le service SQL\n"
            f"  Browser en UDP sur {host}:{_SQL_BROWSER_PORT} et n'a pas obtenu de\n"
            f"  réponse. Le service est peut-être arrêté, ou le port 1434 filtré par\n"
            f"  un pare-feu. Deux issues, au choix :\n"
            f"\n"
            f"  1. Démarrer 'SQL Server Browser' dans SQL Server Configuration Manager.\n"
            f"  2. Indiquer directement le port TCP de l'instance :\n"
            f"\n"
            f"      connection:\n"
            f"        host: {host}\n"
            f"        port: <port de l'instance>\n"
            f"\n"
            f"  Pour le trouver, exécutez dans SSMS, connecté à cette instance :\n"
            f"      SELECT local_tcp_port FROM sys.dm_exec_connections\n"
            f"      WHERE session_id = @@SPID;"
        )

    def _build_connection_string(self) -> str:
        """DSN lisible pour les diagnostics, sans mot de passe."""
        cfg = self._conn_cfg
        server, port = self._resolve_server()
        user = cfg.get("user", "?")
        database = cfg.get("database", "?")
        where = server if port is None else f"{server}:{port}"
        return f"mssql://{user}:***@{where}/{database}?schema={self._default_schema}"

    def _build_columns_query(self, table: str) -> str:
        """Requête d'inspection : TOP 0 est l'équivalent T-SQL de LIMIT 0."""
        schema, name = self._parse_table(table)
        return f"SELECT TOP 0 * FROM {self._quote_identifier(schema, name)}"

    # ============================================================
    # Identifiants
    # ============================================================

    def _validate_identifier(self, name: str) -> str:
        ident = (name or "").strip()
        if not ident:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: identifiant vide."
            )
        if not _IDENTIFIER_RE.match(ident):
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"identifiant invalide '{name}'. "
                f"Utilisez uniquement [A-Za-z0-9_] et commencez par une lettre "
                f"ou un underscore."
            )
        return ident

    def _parse_table(self, table: str) -> Tuple[str, str]:
        """Découpe ``schema.table``; sans schéma, retombe sur ``dbo``."""
        raw = (table or "").strip()
        if "." in raw:
            schema, name = raw.split(".", 1)
            return schema.strip(), name.strip()
        return self._default_schema, raw

    def _quote_identifier(self, schema: str, table: str) -> str:
        """Rend ``[schema].[table]``, après validation stricte des deux noms."""
        return f"[{self._validate_identifier(schema)}].[{self._validate_identifier(table)}]"

    def _quote_column(self, column: str) -> str:
        return f"[{self._validate_identifier(column)}]"

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

        if query:
            sql = query.strip()
        else:
            schema, name = self._parse_table(table)
            sql = f"SELECT * FROM {self._quote_identifier(schema, name)}"

        conn = self._connect()
        try:
            yield from self._execute_query_batches(
                conn=conn, query=sql, batch_size=batch_size
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass

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
    ) -> None:
        """Charge des batches vers SQL Server.

        - ``append``  : INSERT
        - ``replace`` : TRUNCATE puis INSERT
        - ``upsert``  : UPDATE puis INSERT ... WHERE NOT EXISTS, par batch,
          dans une transaction
        """
        if not isinstance(table, str) or not table.strip():
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"'table' doit être un nom non vide"
            )
        table = table.strip()

        if mode not in ("append", "replace", "upsert"):
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"mode '{mode}' non supporté. Supportés: append, replace, upsert"
            )

        if mode == "upsert":
            self._validate_upsert_params(table, key)

        schema, name = self._parse_table(table)
        quoted = self._quote_identifier(schema, name)

        conn = self._connect()
        try:
            cur = conn.cursor()
            first_columns: Optional[List[str]] = None
            truncated = False

            for batch in batches:
                if not batch:
                    continue

                if first_columns is None:
                    first_columns = self._infer_columns_from_batch(batch)
                    if self._auto_create_enabled():
                        self._auto_create_table(
                            cursor=cur,
                            schema=schema,
                            table=name,
                            columns=first_columns,
                            batch=batch,
                        )
                        conn.commit()
                    # TRUNCATE après création éventuelle, avant le premier INSERT.
                    if mode == "replace" and not truncated:
                        cur.execute(f"TRUNCATE TABLE {quoted}")
                        conn.commit()
                        truncated = True

                if mode == "upsert":
                    upd_sql, upd_vals = self._build_update_sql(
                        schema=schema, table=name,
                        columns=first_columns, key_columns=key, batch=batch,
                    )
                    ins_sql, ins_vals = self._build_insert_if_absent_sql(
                        schema=schema, table=name,
                        columns=first_columns, key_columns=key, batch=batch,
                    )
                    cur.executemany(upd_sql, upd_vals)
                    cur.executemany(ins_sql, ins_vals)
                else:
                    sql, values = self._build_insert_sql(
                        schema=schema, table=name,
                        columns=first_columns, batch=batch,
                    )
                    cur.executemany(sql, values)

                conn.commit()

            cur.close()

        except Exception as e:
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
    # Helpers
    # ============================================================

    def _auto_create_enabled(self) -> bool:
        """``create_table: false`` désactive la création automatique."""
        return bool(self.config.get("create_table", True))

    def _infer_columns_from_batch(self, batch: Batch) -> List[str]:
        first = batch[0]
        if not isinstance(first, dict) or not first:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"batch invalide (première ligne vide ou non dict)"
            )
        cols = [c.strip() for c in first.keys() if isinstance(c, str) and c.strip()]
        if not cols:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"aucune colonne détectée dans le batch"
            )
        return cols

    def _tsql_type(self, column: str, batch: Batch) -> str:
        """Type T-SQL déduit de la première valeur non nulle de la colonne.

        `NVARCHAR(MAX)` et `DATETIME2` sont choisis pour que le résultat soit
        identique sur un serveur Windows et sur une image Linux.
        """
        import datetime

        for row in batch:
            v = row.get(column) if isinstance(row, dict) else None
            if v is None:
                continue
            if isinstance(v, bool):
                return "BIT"
            if isinstance(v, int):
                return "BIGINT"
            if isinstance(v, float):
                return "FLOAT"
            if isinstance(v, (datetime.datetime, datetime.date)):
                return "DATETIME2"
            return "NVARCHAR(MAX)"
        return "NVARCHAR(MAX)"

    def _auto_create_table(
        self, *, cursor: Any, schema: str, table: str,
        columns: List[str], batch: Batch,
    ) -> None:
        """Crée la table si elle n'existe pas.

        T-SQL n'a pas de ``CREATE TABLE IF NOT EXISTS`` : on teste le catalogue.
        """
        quoted = self._quote_identifier(schema, table)
        col_defs = ", ".join(
            f"{self._quote_column(c)} {self._tsql_type(c, batch)}" for c in columns
        )
        cursor.execute(
            "IF OBJECT_ID(%s, 'U') IS NULL "
            f"CREATE TABLE {quoted} ({col_defs})",
            (f"{schema}.{table}",),
        )

    def _rows_to_tuples(self, batch: Batch, order: List[str]) -> List[Tuple[Any, ...]]:
        values: List[Tuple[Any, ...]] = []
        for row in batch:
            if not isinstance(row, dict):
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"Row invalide (attendu dict), reçu {type(row).__name__}"
                )
            values.append(tuple(row.get(c, None) for c in order))
        return values

    def _build_insert_sql(
        self, *, schema: str, table: str, columns: List[str], batch: Batch,
    ) -> Tuple[str, List[Tuple[Any, ...]]]:
        quoted = self._quote_identifier(schema, table)
        cols = ", ".join(self._quote_column(c) for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO {quoted} ({cols}) VALUES ({placeholders})"
        return sql, self._rows_to_tuples(batch, columns)

    # ------------------------------------------------------------------
    # UPSERT : UPDATE puis INSERT ... WHERE NOT EXISTS (pas MERGE)
    # ------------------------------------------------------------------

    def _split_key_columns(
        self, columns: List[str], key_columns: List[str]
    ) -> Tuple[List[str], List[str]]:
        """Sépare colonnes de clé et colonnes à mettre à jour, avec validations."""
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

        missing = set(key_columns) - set(columns)
        if missing:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"key columns {sorted(missing)} not found in data columns "
                f"{sorted(columns)}. Key columns must exist in the data."
            )

        non_key = [c for c in columns if c not in set(key_columns)]
        if not non_key:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"all columns are key columns. Upsert requires at least one "
                f"non-key column to update. Columns: {columns}, Keys: {key_columns}"
            )
        return list(key_columns), non_key

    def _build_update_sql(
        self, *, schema: str, table: str, columns: List[str],
        key_columns: List[str], batch: Batch,
    ) -> Tuple[str, List[Tuple[Any, ...]]]:
        """``UPDATE ... SET non_clés WHERE clés`` — premier temps de l'upsert."""
        keys, non_key = self._split_key_columns(columns, key_columns)
        quoted = self._quote_identifier(schema, table)
        set_clause = ", ".join(f"{self._quote_column(c)} = %s" for c in non_key)
        where_clause = " AND ".join(f"{self._quote_column(c)} = %s" for c in keys)
        sql = f"UPDATE {quoted} SET {set_clause} WHERE {where_clause}"
        return sql, self._rows_to_tuples(batch, non_key + keys)

    def _build_insert_if_absent_sql(
        self, *, schema: str, table: str, columns: List[str],
        key_columns: List[str], batch: Batch,
    ) -> Tuple[str, List[Tuple[Any, ...]]]:
        """``INSERT ... SELECT ... WHERE NOT EXISTS`` — second temps de l'upsert.

        Les lignes déjà mises à jour par le premier temps sont ignorées ici.
        """
        keys, _ = self._split_key_columns(columns, key_columns)
        quoted = self._quote_identifier(schema, table)
        cols = ", ".join(self._quote_column(c) for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        where_clause = " AND ".join(f"{self._quote_column(c)} = %s" for c in keys)
        sql = (
            f"INSERT INTO {quoted} ({cols}) "
            f"SELECT {placeholders} "
            f"WHERE NOT EXISTS (SELECT 1 FROM {quoted} WHERE {where_clause})"
        )
        return sql, self._rows_to_tuples(batch, columns + keys)

    def _validate_upsert_params(
        self, table: str, key_columns: Optional[List[str]]
    ) -> None:
        if not table or not isinstance(table, str) or not table.strip():
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"table must be non-empty string"
            )
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
        for col in key_columns:
            if not col or not isinstance(col, str) or not col.strip():
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"key_columns cannot contain empty strings. Got: {key_columns}"
                )
