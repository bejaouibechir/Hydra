r"""
Tests E2E du connecteur SQL Server — exigent une instance vivante.

Ces tests sont ignorés par defaut, comme tests/test_e2e_postgresql.py. Ils ne
verifient pas le SQL produit (c'est le role de tests/test_sqlserver_connector.py)
mais le comportement reel contre un serveur : creation de table, append, replace,
upsert simple et composite, extraction par table et par requete, et le texte
accentue de bout en bout.

Prerequis — lancer un serveur :

    docker run -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=Hydra!Passw0rd \
      -p 1433:1433 --name mssql1 -d mcr.microsoft.com/mssql/server:2022-latest

Puis creer la base :

    docker exec -i mssql1 /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa \
      -P 'Hydra!Passw0rd' -C -Q "CREATE DATABASE hydra_e2e"

Lancer :

    HYDRA_E2E_MSSQL=1 pytest tests/test_e2e_sqlserver.py -v

Variables reconnues (valeurs par defaut entre parentheses) :
    HYDRA_E2E_MSSQL      active la suite       (absent = ignoree)
    MSSQL_HOST           (127.0.0.1)
    MSSQL_PORT           (1433 ; laisser vide avec un MSSQL_HOST
                          MACHINE\\INSTANCE pour eprouver SQL Browser)
    MSSQL_USER           (sa)
    MSSQL_PASSWORD       (Hydra!Passw0rd)
    MSSQL_DATABASE       (hydra_e2e)

Instance nommee (SQL Express, et toute instance Windows non par defaut)
----------------------------------------------------------------------
pymssql/FreeTDS **ne traduit pas un nom d'instance en numero de port** : il
n'interroge pas le service SQL Browser et retombe sur 1433, ou une instance
nommee n'ecoute pas. L'erreur obtenue ne cite meme pas le nom de l'instance :

    Unable to connect: TDS server is unavailable or does not exist (MACHINE)

Il faut donc donner le port. Pour le trouver, dans SSMS connecte a l'instance :

    SELECT local_tcp_port FROM sys.dm_exec_connections WHERE session_id = @@SPID;

Puis, en PowerShell :

    $env:MSSQL_HOST="DESKTOP-463V422"
    $env:MSSQL_PORT="<le port releve>"

Le connecteur accepte aussi `host: MACHINE\INSTANCE` avec un `port` : le port
l'emporte et l'instance est ignoree. C'est le chemin fiable.

Portabilite : lancer cette suite sur DEUX configurations avant d'annoncer le
support — une image Linux conteneurisee et une instance Windows/SQL Express.
Les classements par defaut et la resolution des instances nommees y different.
"""

from __future__ import annotations

import datetime
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("HYDRA_E2E_MSSQL"),
    reason="E2E: requires a live SQL Server. Set HYDRA_E2E_MSSQL=1 to run.",
)

from hydra_etl.internal.connector.sqlserver_connector import SQLServerConnector


def _connector(name: str = "e2e") -> SQLServerConnector:
    # MSSQL_PORT absent : la cle 'port' n'est pas transmise du tout, et c'est
    # volontaire. Avec un MSSQL_HOST de la forme MACHINE\\INSTANCE, cela met a
    # l'epreuve la resolution par SQL Browser sur un vrai serveur, ce qu'aucun
    # test unitaire ne peut faire.
    connection = {
        "host": os.environ.get("MSSQL_HOST", "127.0.0.1"),
        "user": os.environ.get("MSSQL_USER", "sa"),
        "password": os.environ.get("MSSQL_PASSWORD", "Hydra!Passw0rd"),
        "database": os.environ.get("MSSQL_DATABASE", "hydra_e2e"),
    }
    port = os.environ.get("MSSQL_PORT")
    if port:
        connection["port"] = int(port)
    elif "\\" not in connection["host"]:
        connection["port"] = 1433

    return SQLServerConnector(name=name, config={
        "type": "sqlserver",
        "connection": connection,
    })


@pytest.fixture
def c() -> SQLServerConnector:
    return _connector()


def _drop(c: SQLServerConnector, table: str) -> None:
    conn = c._connect()
    try:
        cur = conn.cursor()
        cur.execute(f"IF OBJECT_ID('dbo.{table}', 'U') IS NOT NULL DROP TABLE [dbo].[{table}]")
        conn.commit()
    finally:
        conn.close()


def _rows(c: SQLServerConnector, table: str):
    return [r for batch in c.extract_batches(table=table) for r in batch]


# ============================================================

def test_connection_works(c):
    c.test_connection()


def test_auto_create_then_append(c):
    _drop(c, "e2e_append")
    c.load_batches([[{"id": 1, "label": "one"}, {"id": 2, "label": "two"}]],
                   table="e2e_append", mode="append")
    rows = sorted(_rows(c, "e2e_append"), key=lambda r: r["id"])
    assert [r["id"] for r in rows] == [1, 2]
    assert [r["label"] for r in rows] == ["one", "two"]


def test_append_adds_without_erasing(c):
    _drop(c, "e2e_append2")
    c.load_batches([[{"id": 1, "v": 10}]], table="e2e_append2", mode="append")
    c.load_batches([[{"id": 2, "v": 20}]], table="e2e_append2", mode="append")
    assert len(_rows(c, "e2e_append2")) == 2


def test_replace_truncates_first(c):
    _drop(c, "e2e_replace")
    c.load_batches([[{"id": 1, "v": 10}, {"id": 2, "v": 20}]],
                   table="e2e_replace", mode="append")
    c.load_batches([[{"id": 9, "v": 90}]], table="e2e_replace", mode="replace")
    rows = _rows(c, "e2e_replace")
    assert len(rows) == 1 and rows[0]["id"] == 9


def test_upsert_simple_key(c):
    _drop(c, "e2e_upsert")
    c.load_batches([[{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]],
                   table="e2e_upsert", mode="append")
    # 1 existe -> mis a jour ; 3 n'existe pas -> insere.
    c.load_batches([[{"id": 1, "v": "A"}, {"id": 3, "v": "c"}]],
                   table="e2e_upsert", mode="upsert", key=["id"])
    rows = {r["id"]: r["v"] for r in _rows(c, "e2e_upsert")}
    assert rows == {1: "A", 2: "b", 3: "c"}


def test_upsert_composite_key(c):
    _drop(c, "e2e_upsert_c")
    c.load_batches([[{"region": "eu", "pid": 1, "qty": 10}]],
                   table="e2e_upsert_c", mode="append")
    c.load_batches([[{"region": "eu", "pid": 1, "qty": 99},
                     {"region": "us", "pid": 1, "qty": 5}]],
                   table="e2e_upsert_c", mode="upsert", key=["region", "pid"])
    rows = {(r["region"], r["pid"]): r["qty"] for r in _rows(c, "e2e_upsert_c")}
    assert rows == {("eu", 1): 99, ("us", 1): 5}


def test_extract_by_query(c):
    _drop(c, "e2e_query")
    c.load_batches([[{"id": i, "v": i * 2} for i in range(1, 6)]],
                   table="e2e_query", mode="append")
    rows = [r for b in c.extract_batches(
        query="SELECT [id], [v] FROM [dbo].[e2e_query] WHERE [id] > 3") for r in b]
    assert sorted(r["id"] for r in rows) == [4, 5]


def test_accented_text_survives_the_round_trip(c):
    """NVARCHAR + charset UTF-8 : le resultat doit etre identique quel que soit
    le classement par defaut du serveur."""
    _drop(c, "e2e_accents")
    original = "café crème — garçon, naïve ÆØÅ 日本語"
    c.load_batches([[{"id": 1, "label": original}]],
                   table="e2e_accents", mode="append")
    assert _rows(c, "e2e_accents")[0]["label"] == original


def test_datetime_round_trip(c):
    """DATETIME2 conserve les microsecondes, contrairement a DATETIME (3 ms)."""
    _drop(c, "e2e_dates")
    moment = datetime.datetime(2026, 9, 22, 14, 30, 15, 123456)
    c.load_batches([[{"id": 1, "at": moment}]], table="e2e_dates", mode="append")
    assert _rows(c, "e2e_dates")[0]["at"] == moment


def test_batches_are_streamed(c):
    _drop(c, "e2e_batches")
    c.load_batches([[{"id": i} for i in range(1, 251)]],
                   table="e2e_batches", mode="append")
    sizes = [len(b) for b in c.extract_batches(table="e2e_batches", batch_size=100)]
    assert sum(sizes) == 250
    assert max(sizes) <= 100


def test_schema_qualified_table(c):
    _drop(c, "e2e_schema")
    c.load_batches([[{"id": 1}]], table="dbo.e2e_schema", mode="append")
    assert len(_rows(c, "dbo.e2e_schema")) == 1
