"""
Tests de la CLASSE WebAPIConnector v2 (internal/connector/web_api_connector_v2.py).

Complète tests/test_web_api_connector_v2.py qui ne couvre que les politiques
(plugins/web_api_policies). Ici : construction, test_connection, extraction,
batching, pagination, headers/params, gestion d'erreurs.
"""
from __future__ import annotations

import pytest
import requests_mock as rm_lib

from internal.connector.web_api_connector_v2 import WebAPIConnector
from plugins.auth_providers import APIKeyAuth
from plugins.pagination_strategies import OffsetPagination

BASE = "https://api.example.com"


def make_connector(**kw):
    defaults = dict(
        name="t",
        base_url=BASE,
        auth_provider=APIKeyAuth(key="k", header_name="X-API-Key"),
        pagination_strategy=None,
        json_path="$[*]",
        batch_size=1000,
    )
    defaults.update(kw)
    return WebAPIConnector(**defaults)


class TestConstruction:
    def test_minimal(self):
        c = make_connector()
        assert c.base_url == BASE

    def test_base_url_normalized(self):
        c = make_connector(base_url=BASE + "/")
        assert c.base_url == BASE

    def test_default_error_classifier_present(self):
        assert make_connector().error_classifier is not None


class TestConnection:
    def test_ok(self):
        with rm_lib.Mocker() as m:
            m.head(BASE, status_code=200)
            assert make_connector().test_connection() is True

    def test_4xx_still_reachable(self):
        # < 500 = API joignable (auth pourra être affinée ensuite)
        with rm_lib.Mocker() as m:
            m.head(BASE, status_code=401)
            assert make_connector().test_connection() is True

    def test_server_error_raises(self):
        with rm_lib.Mocker() as m:
            m.head(BASE, status_code=503)
            with pytest.raises(ConnectionError):
                make_connector().test_connection()


class TestExtraction:
    def test_simple_list(self):
        with rm_lib.Mocker() as m:
            m.get(f"{BASE}/items", json=[{"id": 1}, {"id": 2}])
            batches = list(make_connector().extract_batches("items"))
        assert batches == [[{"id": 1}, {"id": 2}]]

    def test_json_path_nested(self):
        with rm_lib.Mocker() as m:
            m.get(f"{BASE}/wrap", json={"data": {"rows": [{"a": 1}]}})
            c = make_connector(json_path="$.data.rows[*]")
            batches = list(c.extract_batches("wrap"))
        assert batches == [[{"a": 1}]]

    def test_batch_size_splits(self):
        items = [{"i": n} for n in range(5)]
        with rm_lib.Mocker() as m:
            m.get(f"{BASE}/items", json=items)
            c = make_connector(batch_size=2)
            batches = list(c.extract_batches("items"))
        assert [len(b) for b in batches] == [2, 2, 1]

    def test_auth_and_custom_headers_sent(self):
        with rm_lib.Mocker() as m:
            m.get(f"{BASE}/items", json=[])
            c = make_connector()
            list(c.extract_batches("items", headers={"X-Trace": "42"}))
            sent = m.request_history[0].headers
        assert sent["X-API-Key"] == "k"
        assert sent["X-Trace"] == "42"

    def test_query_params_sent(self):
        with rm_lib.Mocker() as m:
            m.get(f"{BASE}/items", json=[])
            c = make_connector()
            list(c.extract_batches("items", query_params={"since": "2026"}))
            assert m.request_history[0].qs.get("since") == ["2026"]

    def test_endpoint_slash_normalized(self):
        with rm_lib.Mocker() as m:
            m.get(f"{BASE}/items", json=[])
            list(make_connector().extract_batches("/items"))
            assert m.request_history[0].path == "/items"


class TestPagination:
    def test_offset_pagination_multi_pages(self):
        pages = {0: [{"i": 0}, {"i": 1}], 2: [{"i": 2}], }
        def responder(request, context):
            off = int(request.qs.get("offset", ["0"])[0])
            return pages.get(off, [])
        with rm_lib.Mocker() as m:
            m.get(f"{BASE}/items", json=responder)
            c = make_connector(pagination_strategy=OffsetPagination(limit=2))
            items = [it for b in c.extract_batches("items") for it in b]
        assert items == [{"i": 0}, {"i": 1}, {"i": 2}]


class TestErrors:
    def test_http_error_raises(self):
        with rm_lib.Mocker() as m:
            m.get(f"{BASE}/missing", status_code=404, json={"error": "nf"})
            with pytest.raises(Exception):
                list(make_connector().extract_batches("missing"))

    def test_network_error_raises(self):
        import requests
        with rm_lib.Mocker() as m:
            m.get(f"{BASE}/net", exc=requests.exceptions.ConnectTimeout)
            with pytest.raises(Exception):
                list(make_connector().extract_batches("net"))
