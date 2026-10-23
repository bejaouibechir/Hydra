"""
Validation de la cle d'upsert PostgreSQL — test unitaire, sans base de donnees.

Pourquoi ce test existe
-----------------------
`_validate_upsert_key()` interroge information_schema pour verifier que la `key`
du YAML correspond a une contrainte PRIMARY KEY / UNIQUE reelle. Deux details du
pilote faisaient echouer cette verification pour TOUTE table, y compris celles
dont la PK correspondait exactement :

1. le curseur est un RealDictCursor, donc une ligne est un dict : la deballer
   comme un tuple (`a, b = row`) recupere ses CLES, pas ses valeurs ;
2. `information_schema.key_column_usage.column_name` est de type sql_identifier ;
   psycopg2 ne decode pas un tableau de ce type et renvoie le texte brut
   ("{record_id}") au lieu d'une liste.

Resultat observe avant correctif : `KeyError: 0` sur tout job en mode upsert.

Le test E2E qui couvrait ce chemin (tests/test_e2e_postgresql.py) est desactive
au niveau module car il exige des conteneurs Docker. Celui-ci le remplace pour
la CI : il n'a besoin ni de serveur ni de pilote, seulement d'un faux curseur
qui imite fidelement le comportement de psycopg2 decrit ci-dessus.
"""

import pytest

from hydra_etl.internal.connector.postgresql_connector import PostgreSQLConnector


class _FakeRealDictCursor:
    """Imite un psycopg2.extras.RealDictCursor pour la requete de contraintes.

    `rows` est la liste des contraintes a renvoyer, sous la forme
    (constraint_name, [colonnes]). Elles sont servies comme des dicts, et les
    colonnes comme la chaine brute "{a,b}" que renvoie psycopg2 pour un
    array_agg de sql_identifier SANS cast ::text — sauf si le code a jour
    demande le cast, ce que l'on detecte dans la requete.
    """

    def __init__(self, rows):
        self._rows = rows
        self._result = []

    def execute(self, query, params=None):
        casts_to_text = "column_name::text" in query
        self._result = [
            {
                "constraint_name": name,
                "constraint_cols": list(cols) if casts_to_text else "{" + ",".join(cols) + "}",
            }
            for name, cols in self._rows
        ]

    def fetchall(self):
        return self._result


def _validate(rows, key):
    connector = PostgreSQLConnector.__new__(PostgreSQLConnector)
    connector.name = "warehouse"
    connector._validate_upsert_key(
        cursor=_FakeRealDictCursor(rows),
        schema="public",
        table="product",
        key=key,
    )


def test_primary_key_simple_est_acceptee():
    """Une PK sur la colonne de `key` doit etre reconnue (regression KeyError: 0)."""
    _validate([("product_pkey", ["record_id"])], ["record_id"])


def test_cle_composite_dans_un_autre_ordre_est_acceptee():
    """Le match se fait sur l'ensemble des colonnes, l'ordre est ignore."""
    _validate([("orders_pkey", ["order_id", "line_no"])], ["line_no", "order_id"])


def test_contrainte_unique_est_acceptee():
    _validate([("uq_product_sku", ["sku"])], ["sku"])


def test_aucune_contrainte_leve_une_erreur_explicite():
    with pytest.raises(ValueError) as excinfo:
        _validate([], ["record_id"])
    assert "no primary key/unique constraint" in str(excinfo.value).lower()


def test_cle_sans_contrainte_correspondante_nomme_les_contraintes_disponibles():
    """Le message d'erreur doit citer les contraintes reelles, pas lever KeyError."""
    with pytest.raises(ValueError) as excinfo:
        _validate([("product_pkey", ["record_id"])], ["sku"])
    message = str(excinfo.value)
    assert "product_pkey" in message
    assert "record_id" in message
