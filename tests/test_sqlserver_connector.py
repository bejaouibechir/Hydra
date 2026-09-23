"""
Tests du connecteur SQL Server.

Aucun serveur n'est requis : ces tests portent sur le SQL produit, la validation
des identifiants et la résolution de l'adresse. Les tests qui exigent une
instance vivante sont dans tests/test_e2e_sqlserver.py.

Organisation :
1. Identifiants et guillemets crochets
2. Résolution de l'adresse, instances nommées comprises
3. INSERT
4. UPSERT : UPDATE puis INSERT ... WHERE NOT EXISTS
5. Validation des paramètres
6. Types T-SQL et création automatique
7. Protection contre l'injection SQL
8. Extraction
"""

from __future__ import annotations

import datetime

import pytest

from hydra_etl.internal.connector import sqlserver_connector as ssc
from hydra_etl.internal.connector.sqlserver_connector import SQLServerConnector


# ============================================================
# Fixtures
# ============================================================

def _make(**connection) -> SQLServerConnector:
    cfg = {"host": "localhost", "user": "sa", "password": "secret", "database": "test_db"}
    cfg.update(connection)
    return SQLServerConnector(name="test_mssql", config={"type": "sqlserver", "connection": cfg})


@pytest.fixture
def conn() -> SQLServerConnector:
    return _make()


# ============================================================
# 1. Identifiants et guillemets crochets
# ============================================================

def test_quote_identifier_uses_brackets(conn):
    assert conn._quote_identifier("dbo", "orders") == "[dbo].[orders]"


def test_quote_column_uses_brackets(conn):
    assert conn._quote_column("customer_id") == "[customer_id]"


def test_parse_table_defaults_to_dbo(conn):
    assert conn._parse_table("orders") == ("dbo", "orders")


def test_parse_table_reads_explicit_schema(conn):
    assert conn._parse_table("sales.orders") == ("sales", "orders")


def test_default_schema_can_be_configured():
    c = _make(schema="staging")
    assert c._parse_table("orders") == ("staging", "orders")


def test_columns_query_uses_top_zero(conn):
    # TOP 0 est l'équivalent T-SQL de LIMIT 0 : MySQL/PostgreSQL ne s'appliquent pas.
    assert conn._build_columns_query("sales.orders") == "SELECT TOP 0 * FROM [sales].[orders]"


def test_dsn_hides_the_password(conn):
    dsn = conn._build_connection_string()
    assert "secret" not in dsn
    assert dsn == "mssql://sa:***@localhost:1433/test_db?schema=dbo"


# ============================================================
# 2. Résolution de l'adresse et instances nommées
# ============================================================

def test_plain_host_keeps_its_port():
    assert _make(host="10.0.0.5", port=1433)._resolve_server() == ("10.0.0.5", 1433)


def test_custom_port_is_honoured():
    assert _make(host="10.0.0.5", port=14330)._resolve_server() == ("10.0.0.5", 14330)


@pytest.fixture
def browser_muet(monkeypatch):
    """SQL Browser arrete, ou UDP 1434 filtre : la requete ne rend rien.

    Sans ce leurre, chaque test d'instance nommee enverrait un vrai datagramme
    vers un hote inexistant et attendrait le delai complet.
    """
    monkeypatch.setattr(ssc, "_query_sql_browser", lambda *a, **k: None)


def test_backslash_host_is_a_named_instance(browser_muet):
    # SQL Browser muet : on transmet MACHINE\SQLEXPRESS tel quel et le message
    # d'aide prend le relais si la connexion echoue.
    server, port = _make(host="MACHINE\\SQLEXPRESS")._resolve_server()
    assert server == "MACHINE\\SQLEXPRESS"
    assert port is None


def test_instance_key_builds_a_named_instance(browser_muet):
    server, port = _make(host="MACHINE", instance="SQLEXPRESS")._resolve_server()
    assert server == "MACHINE\\SQLEXPRESS"
    assert port is None


def test_named_instance_dsn_omits_the_port(browser_muet):
    assert "1433" not in _make(host="MACHINE", instance="SQLEXPRESS")._build_connection_string()


def test_explicit_port_wins_over_a_named_instance():
    """FreeTDS ne sait pas traduire un nom d'instance en port : quand le port est
    donne, on l'utilise et on laisse tomber l'instance. C'est le seul chemin
    fiable, et c'est celui que SQL Express impose."""
    server, port = _make(host="MACHINE\\SQLEXPRESS", port=49732)._resolve_server()
    assert server == "MACHINE"
    assert port == 49732


def test_explicit_port_wins_with_the_instance_key_too():
    server, port = _make(host="MACHINE", instance="SQLEXPRESS", port=49732)._resolve_server()
    assert server == "MACHINE"
    assert port == 49732


def test_split_instance_reads_both_spellings():
    assert _make(host="M\\I")._split_instance() == ("M", "I")
    assert _make(host="M", instance="I")._split_instance() == ("M", "I")
    assert _make(host="M")._split_instance() == ("M", None)


def test_named_instance_without_port_gets_a_hint():
    """Sans ce message, l'utilisateur ne voit qu'une erreur FreeTDS qui ne cite
    meme pas le nom de l'instance."""
    hint = _make(host="MACHINE\\SQLEXPRESS")._named_instance_hint()
    assert "SQLEXPRESS" in hint
    assert "port" in hint
    assert "local_tcp_port" in hint, "le message doit donner la requete qui trouve le port"


def test_no_hint_when_a_port_is_given():
    assert _make(host="MACHINE\\SQLEXPRESS", port=49732)._named_instance_hint() == ""


def test_no_hint_without_a_named_instance():
    assert _make(host="10.0.0.5")._named_instance_hint() == ""


def test_instance_name_is_validated():
    with pytest.raises(ValueError):
        _make(host="MACHINE", instance="SQLEXPRESS; DROP TABLE users")._resolve_server()


# ============================================================
# 3. INSERT
# ============================================================

def test_insert_sql_shape(conn):
    sql, values = conn._build_insert_sql(
        schema="dbo", table="users",
        columns=["id", "name"], batch=[{"id": 1, "name": "a"}],
    )
    assert sql == "INSERT INTO [dbo].[users] ([id], [name]) VALUES (%s, %s)"
    assert values == [(1, "a")]


def test_insert_preserves_column_order(conn):
    sql, values = conn._build_insert_sql(
        schema="dbo", table="t",
        columns=["c", "a", "b"], batch=[{"a": 1, "b": 2, "c": 3}],
    )
    assert sql.index("[c]") < sql.index("[a]") < sql.index("[b]")
    assert values == [(3, 1, 2)]


def test_insert_fills_missing_columns_with_none(conn):
    _, values = conn._build_insert_sql(
        schema="dbo", table="t",
        columns=["id", "name", "email"], batch=[{"id": 1, "name": "a"}],
    )
    assert values == [(1, "a", None)]


def test_insert_rejects_a_non_dict_row(conn):
    with pytest.raises(ValueError):
        conn._build_insert_sql(schema="dbo", table="t", columns=["id"], batch=[(1,)])


# ============================================================
# 4. UPSERT
# ============================================================

def test_upsert_never_uses_merge(conn):
    """MERGE a des problèmes de concurrence documentés : il est volontairement exclu."""
    upd, _ = conn._build_update_sql(
        schema="dbo", table="t", columns=["id", "v"],
        key_columns=["id"], batch=[{"id": 1, "v": 2}],
    )
    ins, _ = conn._build_insert_if_absent_sql(
        schema="dbo", table="t", columns=["id", "v"],
        key_columns=["id"], batch=[{"id": 1, "v": 2}],
    )
    assert "MERGE" not in upd.upper()
    assert "MERGE" not in ins.upper()


def test_update_sql_simple_key(conn):
    sql, values = conn._build_update_sql(
        schema="dbo", table="users", columns=["id", "name", "email"],
        key_columns=["id"], batch=[{"id": 7, "name": "a", "email": "e"}],
    )
    assert sql == "UPDATE [dbo].[users] SET [name] = %s, [email] = %s WHERE [id] = %s"
    # Ordre des valeurs : colonnes mises à jour d'abord, clés ensuite.
    assert values == [("a", "e", 7)]


def test_update_sql_composite_key(conn):
    sql, values = conn._build_update_sql(
        schema="dbo", table="sales", columns=["region", "product_id", "qty"],
        key_columns=["region", "product_id"],
        batch=[{"region": "eu", "product_id": 3, "qty": 10}],
    )
    assert "SET [qty] = %s" in sql
    assert "WHERE [region] = %s AND [product_id] = %s" in sql
    assert values == [(10, "eu", 3)]


def test_insert_if_absent_sql_shape(conn):
    sql, values = conn._build_insert_if_absent_sql(
        schema="dbo", table="users", columns=["id", "name"],
        key_columns=["id"], batch=[{"id": 7, "name": "a"}],
    )
    assert sql == (
        "INSERT INTO [dbo].[users] ([id], [name]) "
        "SELECT %s, %s "
        "WHERE NOT EXISTS (SELECT 1 FROM [dbo].[users] WHERE [id] = %s)"
    )
    # Ordre des valeurs : toutes les colonnes, puis les clés pour le NOT EXISTS.
    assert values == [(7, "a", 7)]


def test_insert_if_absent_composite_key(conn):
    sql, values = conn._build_insert_if_absent_sql(
        schema="dbo", table="sales", columns=["region", "product_id", "qty"],
        key_columns=["region", "product_id"],
        batch=[{"region": "eu", "product_id": 3, "qty": 10}],
    )
    assert "WHERE [region] = %s AND [product_id] = %s" in sql
    assert values == [("eu", 3, 10, "eu", 3)]


def test_upsert_key_absent_from_columns_fails(conn):
    with pytest.raises(ValueError, match="not found in data columns"):
        conn._build_update_sql(
            schema="dbo", table="t", columns=["a", "b"],
            key_columns=["id"], batch=[{"a": 1, "b": 2}],
        )


def test_upsert_with_only_key_columns_fails(conn):
    with pytest.raises(ValueError, match="at least one"):
        conn._build_update_sql(
            schema="dbo", table="t", columns=["id"],
            key_columns=["id"], batch=[{"id": 1}],
        )


# ============================================================
# 5. Validation des paramètres
# ============================================================

def test_validate_upsert_params_accepts_a_valid_key(conn):
    conn._validate_upsert_params("users", ["id"])


def test_validate_upsert_params_rejects_missing_key(conn):
    with pytest.raises(ValueError, match="key_columns required"):
        conn._validate_upsert_params("users", None)


def test_validate_upsert_params_rejects_empty_key(conn):
    with pytest.raises(ValueError, match="cannot be empty"):
        conn._validate_upsert_params("users", [])


def test_validate_upsert_params_rejects_blank_key_name(conn):
    with pytest.raises(ValueError, match="empty strings"):
        conn._validate_upsert_params("users", ["id", "  "])


def test_load_rejects_an_unknown_mode(conn):
    with pytest.raises(ValueError, match="non supporté"):
        conn.load_batches([], table="t", mode="merge")


def test_load_rejects_an_empty_table_name(conn):
    with pytest.raises(ValueError, match="non vide"):
        conn.load_batches([], table="   ", mode="append")


def test_infer_columns_rejects_an_invalid_batch(conn):
    with pytest.raises(ValueError):
        conn._infer_columns_from_batch([{}])


# ============================================================
# 6. Types T-SQL et création automatique
# ============================================================

@pytest.mark.parametrize("value,expected", [
    (True, "BIT"),
    (42, "BIGINT"),
    (4.2, "FLOAT"),
    (datetime.datetime(2026, 1, 1, 12, 0), "DATETIME2"),
    (datetime.date(2026, 1, 1), "DATETIME2"),
    ("texte", "NVARCHAR(MAX)"),
])
def test_tsql_type_inference(conn, value, expected):
    assert conn._tsql_type("c", [{"c": value}]) == expected


def test_tsql_type_skips_none_values(conn):
    assert conn._tsql_type("c", [{"c": None}, {"c": 7}]) == "BIGINT"


def test_tsql_type_falls_back_to_nvarchar(conn):
    assert conn._tsql_type("c", [{"c": None}]) == "NVARCHAR(MAX)"


def test_booleans_are_not_mistaken_for_integers(conn):
    # bool est une sous-classe de int en Python : l'ordre des tests compte.
    assert conn._tsql_type("c", [{"c": True}]) == "BIT"


def test_auto_create_uses_nvarchar_never_varchar(conn):
    """NVARCHAR protège le texte accentué des différences de classement entre
    un serveur Windows en Latin1 et une image Linux en UTF-8."""
    captured = {}

    class Cur:
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params

    conn._auto_create_table(
        cursor=Cur(), schema="dbo", table="t",
        columns=["id", "label"], batch=[{"id": 1, "label": "café"}],
    )
    sql = captured["sql"]
    assert "NVARCHAR(MAX)" in sql
    assert "VARCHAR(MAX)" not in sql.replace("NVARCHAR(MAX)", "")
    assert "[id] BIGINT" in sql


def test_auto_create_guards_with_object_id(conn):
    """T-SQL n'a pas de CREATE TABLE IF NOT EXISTS : on interroge le catalogue."""
    captured = {}

    class Cur:
        def execute(self, sql, params=None):
            captured["sql"] = sql
            captured["params"] = params

    conn._auto_create_table(
        cursor=Cur(), schema="sales", table="orders",
        columns=["id"], batch=[{"id": 1}],
    )
    assert "IF OBJECT_ID(%s, 'U') IS NULL" in captured["sql"]
    assert "CREATE TABLE [sales].[orders]" in captured["sql"]
    # Le nom qualifié passe en paramètre, jamais concaténé dans le SQL.
    assert captured["params"] == ("sales.orders",)


def test_auto_create_can_be_disabled():
    c = SQLServerConnector(name="d", config={
        "type": "sqlserver", "create_table": False,
        "connection": {"host": "h", "user": "sa", "database": "db"},
    })
    assert c._auto_create_enabled() is False


# ============================================================
# 7. Protection contre l'injection SQL
# ============================================================

@pytest.mark.parametrize("bad", [
    "users; DROP TABLE x",
    "users--",
    "users/*",
    "us]ers",
    "[users",
    "us ers",
    "",
    "   ",
    "1users",
])
def test_invalid_identifiers_are_rejected(conn, bad):
    with pytest.raises(ValueError):
        conn._validate_identifier(bad)


def test_injection_in_a_table_name_is_rejected(conn):
    with pytest.raises(ValueError):
        conn._build_insert_sql(
            schema="dbo", table="users; DROP TABLE secrets",
            columns=["id"], batch=[{"id": 1}],
        )


def test_injection_in_a_column_name_is_rejected(conn):
    with pytest.raises(ValueError):
        conn._build_insert_sql(
            schema="dbo", table="users",
            columns=["id], [password"], batch=[{"id": 1}],
        )


def test_valid_identifiers_are_accepted(conn):
    for good in ("users", "_tmp", "Order_2026", "a1"):
        assert conn._validate_identifier(good) == good


# ============================================================
# 8. Extraction
# ============================================================

def test_extract_rejects_query_and_table_together(conn):
    with pytest.raises(ValueError, match="mutuellement exclusifs"):
        list(conn.extract_batches(query="SELECT 1", table="t"))


def test_extract_requires_query_or_table(conn):
    with pytest.raises(ValueError, match="requis"):
        list(conn.extract_batches())


def test_extract_rejects_incremental(conn):
    with pytest.raises(ValueError, match="incremental"):
        list(conn.extract_batches(table="t", incremental={"column": "updated_at"}))


# ============================================================
# 9. Capacités déclarées
# ============================================================

def test_capabilities(conn):
    caps = conn.get_capabilities()
    assert caps["supports_extract"] is True
    assert caps["supports_load"] is True
    assert caps["supports_upsert"] is True
    assert caps["supports_incremental"] is False


def test_registry_exposes_both_aliases():
    from hydra_etl.internal.connector.registry import CONNECTOR_REGISTRY
    for alias in ("sqlserver", "mssql"):
        c = CONNECTOR_REGISTRY[alias](
            "d", {"connection": {"host": "h", "user": "sa", "database": "db"}}
        )
        assert isinstance(c, SQLServerConnector)


# ============================================================
# 10. Orchestration de load_batches, avec une fausse connexion
#
# Les tests ci-dessus verifient le SQL produit. Ceux-ci verifient l'ordre des
# appels : creation de table, TRUNCATE, UPDATE avant INSERT, commits. C'est la
# partie qu'aucun test de generation ne couvre et que seul l'E2E verrait sinon.
# ============================================================

class _FakeCursor:
    def __init__(self, log):
        self._log = log

    def execute(self, sql, params=None):
        self._log.append(("execute", " ".join(sql.split()), params))

    def executemany(self, sql, values):
        self._log.append(("executemany", " ".join(sql.split()), list(values)))

    def close(self):
        self._log.append(("cursor.close", None, None))


class _FakeConn:
    def __init__(self, log):
        self._log = log

    def cursor(self):
        return _FakeCursor(self._log)

    def commit(self):
        self._log.append(("commit", None, None))

    def rollback(self):
        self._log.append(("rollback", None, None))

    def close(self):
        self._log.append(("conn.close", None, None))


@pytest.fixture
def traced(monkeypatch):
    """Rend (connecteur, journal des appels)."""
    c = _make()
    log = []
    monkeypatch.setattr(c, "_connect", lambda: _FakeConn(log))
    return c, log


def _verbs(log):
    return [entry[0] for entry in log]


def _sqls(log):
    return [entry[1] for entry in log if entry[1]]


def test_append_creates_the_table_then_inserts(traced):
    c, log = traced
    c.load_batches([[{"id": 1, "v": "a"}]], table="t", mode="append")
    sqls = _sqls(log)
    assert "IF OBJECT_ID(%s, 'U') IS NULL CREATE TABLE [dbo].[t]" in sqls[0]
    assert sqls[1].startswith("INSERT INTO [dbo].[t]")
    assert "TRUNCATE" not in " ".join(sqls)


def test_replace_truncates_after_create_before_insert(traced):
    c, log = traced
    c.load_batches([[{"id": 1}]], table="t", mode="replace")
    sqls = _sqls(log)
    create_at = next(i for i, s in enumerate(sqls) if "CREATE TABLE" in s)
    trunc_at = next(i for i, s in enumerate(sqls) if "TRUNCATE" in s)
    insert_at = next(i for i, s in enumerate(sqls) if s.startswith("INSERT"))
    assert create_at < trunc_at < insert_at


def test_replace_truncates_only_once_across_batches(traced):
    c, log = traced
    c.load_batches([[{"id": 1}], [{"id": 2}], [{"id": 3}]], table="t", mode="replace")
    assert sum(1 for s in _sqls(log) if "TRUNCATE" in s) == 1


def test_upsert_runs_update_before_insert(traced):
    c, log = traced
    c.load_batches([[{"id": 1, "v": "a"}]], table="t", mode="upsert", key=["id"])
    sqls = _sqls(log)
    upd = next(i for i, s in enumerate(sqls) if s.startswith("UPDATE"))
    ins = next(i for i, s in enumerate(sqls) if s.startswith("INSERT"))
    assert upd < ins, "l'INSERT ... WHERE NOT EXISTS doit suivre l'UPDATE"


def test_empty_batches_are_skipped(traced):
    c, log = traced
    c.load_batches([[], [], []], table="t", mode="append")
    assert not [s for s in _sqls(log) if s.startswith("INSERT")]


def test_columns_come_from_the_first_batch_only(traced):
    c, log = traced
    # Le second batch a une colonne de plus : elle est ignoree, comme pour MySQL.
    c.load_batches([[{"id": 1}], [{"id": 2, "extra": "x"}]], table="t", mode="append")
    inserts = [s for s in _sqls(log) if s.startswith("INSERT")]
    assert all("[extra]" not in s for s in inserts)


def test_create_table_is_skipped_when_disabled(monkeypatch):
    c = SQLServerConnector(name="d", config={
        "type": "sqlserver", "create_table": False,
        "connection": {"host": "h", "user": "sa", "database": "db"},
    })
    log = []
    monkeypatch.setattr(c, "_connect", lambda: _FakeConn(log))
    c.load_batches([[{"id": 1}]], table="t", mode="append")
    assert not [s for s in _sqls(log) if "CREATE TABLE" in s]


def test_connection_is_closed_on_failure(traced):
    c, log = traced
    with pytest.raises(ValueError, match="échec chargement"):
        # 'extra' n'est pas dans les colonnes de cle : l'upsert doit echouer.
        c.load_batches([[{"id": 1}]], table="t", mode="upsert", key=["absent"])
    assert "rollback" in _verbs(log)
    assert "conn.close" in _verbs(log)


# ---------------------------------------------------------------------------
# SQL Browser (SSRP) : la resolution d'une instance nommee en numero de port
# ---------------------------------------------------------------------------
#
# FreeTDS, embarque dans pymssql, ne fait pas cette resolution. Hydra la fait
# elle-meme pour que 'host: MACHINE\SQLEXPRESS' suffise, sans pilote systeme
# a installer. Ces tests couvrent le decodage de la reponse et le branchement
# dans _resolve_server, sans jamais toucher au reseau.


def _ssrp(payload: str) -> bytes:
    """Fabrique une reponse SSRP bien formee autour d'un corps donne."""
    body = payload.encode("ascii")
    return b"\x05" + len(body).to_bytes(2, "little") + body


def test_browser_response_yields_the_port():
    data = _ssrp(
        "ServerName;MACHINE;InstanceName;SQLEXPRESS;IsClustered;No;"
        "Version;16.0.1000.6;tcp;14330;;"
    )
    assert ssc._parse_sql_browser_response(data, "SQLEXPRESS") == 14330


def test_browser_response_is_case_insensitive_on_the_instance():
    data = _ssrp("ServerName;M;InstanceName;SqlExpress;tcp;14330;;")
    assert ssc._parse_sql_browser_response(data, "SQLEXPRESS") == 14330


def test_browser_response_picks_the_right_instance_among_several():
    """Un serveur peut heberger plusieurs instances et les decrire toutes.

    Rendre le port d'une autre instance connecterait silencieusement l'utilisateur
    a la mauvaise base : c'est le pire resultat possible, pire qu'un echec.
    """
    data = _ssrp(
        "ServerName;M;InstanceName;AUTRE;tcp;1500;;"
        "ServerName;M;InstanceName;SERVER2024;tcp;14330;;"
    )
    assert ssc._parse_sql_browser_response(data, "SERVER2024") == 14330
    assert ssc._parse_sql_browser_response(data, "AUTRE") == 1500


def test_browser_response_reads_past_two_blocks():
    """Le decoupage doit tenir au-dela du second bloc.

    Une premiere version lisait les champs d'un seul tenant : le ';;' qui
    separe les blocs y ajoutait un champ vide, decalant les paires d'un cran
    des la deuxieme instance.
    """
    data = _ssrp("InstanceName;A;tcp;1;;InstanceName;B;tcp;2;;InstanceName;C;tcp;3;;")
    assert ssc._parse_sql_browser_response(data, "C") == 3


def test_browser_response_without_the_wanted_instance_yields_nothing():
    data = _ssrp("ServerName;M;InstanceName;AUTRE;tcp;1500;;")
    assert ssc._parse_sql_browser_response(data, "SQLEXPRESS") is None


def test_browser_response_with_a_named_pipe_only_yields_nothing():
    # Une instance qui n'ecoute pas en TCP n'a pas de port a donner.
    data = _ssrp("ServerName;M;InstanceName;SQLEXPRESS;np;\\\\M\\pipe\\sql;;")
    assert ssc._parse_sql_browser_response(data, "SQLEXPRESS") is None


def test_browser_rejects_a_wrong_opcode():
    body = b"ServerName;M;InstanceName;SQLEXPRESS;tcp;14330;;"
    assert ssc._parse_sql_browser_response(b"\x01" + body, "SQLEXPRESS") is None


def test_browser_rejects_a_truncated_datagram():
    assert ssc._parse_sql_browser_response(b"\x05", "SQLEXPRESS") is None
    assert ssc._parse_sql_browser_response(b"", "SQLEXPRESS") is None


def test_browser_rejects_an_impossible_port():
    assert ssc._parse_sql_browser_response(
        _ssrp("InstanceName;I;tcp;99999;;"), "I"
    ) is None
    assert ssc._parse_sql_browser_response(
        _ssrp("InstanceName;I;tcp;pas_un_nombre;;"), "I"
    ) is None


def test_resolve_uses_the_port_sql_browser_gives(monkeypatch):
    """Le cas nominal : l'utilisateur n'ecrit qu'un nom d'instance."""
    monkeypatch.setattr(ssc, "_query_sql_browser", lambda h, i, t: 14330)
    server, port = _make(host="MACHINE\\SERVER2024")._resolve_server()
    assert server == "MACHINE"  # le nom d'instance ne part pas au pilote
    assert port == 14330


def test_resolve_falls_back_when_sql_browser_is_silent(monkeypatch):
    monkeypatch.setattr(ssc, "_query_sql_browser", lambda h, i, t: None)
    server, port = _make(host="MACHINE\\SERVER2024")._resolve_server()
    assert server == "MACHINE\\SERVER2024"
    assert port is None


def test_an_explicit_port_asks_sql_browser_nothing(monkeypatch):
    """Un port donne est un ordre : aucune raison d'aller sonder le reseau."""
    def _interdit(*a, **k):
        raise AssertionError("SQL Browser interroge alors que le port est connu")

    monkeypatch.setattr(ssc, "_query_sql_browser", _interdit)
    assert _make(host="MACHINE\\SERVER2024", port=14330)._resolve_server() == (
        "MACHINE",
        14330,
    )


def test_a_plain_host_asks_sql_browser_nothing(monkeypatch):
    def _interdit(*a, **k):
        raise AssertionError("SQL Browser interroge sans instance nommee")

    monkeypatch.setattr(ssc, "_query_sql_browser", _interdit)
    assert _make(host="127.0.0.1")._resolve_server() == ("127.0.0.1", 1433)


def test_sql_browser_is_asked_only_once(monkeypatch):
    """_build_connection_string appelle aussi _resolve_server : une requete
    reseau par message d'erreur serait absurde."""
    appels = []
    monkeypatch.setattr(
        ssc, "_query_sql_browser", lambda h, i, t: (appels.append((h, i)), 14330)[1]
    )
    c = _make(host="MACHINE\\SERVER2024")
    c._resolve_server()
    c._resolve_server()
    c._build_connection_string()
    assert appels == [("MACHINE", "SERVER2024")]


def test_browser_timeout_is_configurable(monkeypatch):
    vus = []
    monkeypatch.setattr(
        ssc, "_query_sql_browser", lambda h, i, t: (vus.append(t), None)[1]
    )
    _make(host="M\\I", browser_timeout=0.25)._resolve_server()
    assert vus == [0.25]
