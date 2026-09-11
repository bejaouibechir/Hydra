# -*- coding: utf-8 -*-
"""
tests/test_api_studio.py — Montage du Studio dans l'API.

Verifie les quatre regles qui rendent le bundle servable sans casser l'API :
    1. /api reste prioritaire sur le montage racine ;
    2. une route inconnue renvoie index.html (routage React cote navigateur) ;
    3. sans bundle, l'API fonctionne et / explique comment le construire ;
    4. aucune remontee de chemin hors du bundle.

Le bundle reel est produit par `python scripts/build_studio.py`. Ces tests
fabriquent un bundle minimal pour rester independants de Node.
"""
from __future__ import annotations

import importlib

import pytest

fastapi = pytest.importorskip("fastapi", reason="l'extra [server] n'est pas installe")
from fastapi.testclient import TestClient  # noqa: E402

from hydra_etl.api import studio as studio_mod  # noqa: E402

INDEX_HTML = (
    '<!doctype html><html><head><title>Hydra Studio</title></head>'
    '<body><div id="root"></div></body></html>'
)


def _build_app(tmp_path, *, bundled: bool, disabled: bool = False):
    """Reconstruit une application avec un bundle factice, ou sans bundle."""
    dist = tmp_path / "studio_dist"
    if bundled:
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
        (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    else:
        dist.mkdir(parents=True)

    studio_mod.STUDIO_DIST = dist
    import hydra_etl.api.main as main_mod
    importlib.reload(main_mod)
    return main_mod


@pytest.fixture
def bundled(tmp_path, monkeypatch):
    monkeypatch.delenv("HYDRA_NO_STUDIO", raising=False)
    original = studio_mod.STUDIO_DIST
    module = _build_app(tmp_path, bundled=True)
    yield TestClient(module.app), module
    studio_mod.STUDIO_DIST = original


@pytest.fixture
def unbundled(tmp_path, monkeypatch):
    monkeypatch.delenv("HYDRA_NO_STUDIO", raising=False)
    original = studio_mod.STUDIO_DIST
    module = _build_app(tmp_path, bundled=False)
    yield TestClient(module.app), module
    studio_mod.STUDIO_DIST = original


class TestBundlePresent:
    def test_studio_is_reported_as_bundled(self, bundled):
        _, module = bundled
        assert module.STUDIO_BUNDLED is True

    def test_root_serves_the_studio(self, bundled):
        client, _ = bundled
        response = client.get("/")
        assert response.status_code == 200
        assert '<div id="root">' in response.text

    def test_api_keeps_priority_over_the_root_mount(self, bundled):
        client, _ = bundled
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_unknown_api_route_answers_json_not_html(self, bundled):
        client, _ = bundled
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404
        assert "application/json" in response.headers["content-type"]

    def test_client_side_route_falls_back_to_index(self, bundled):
        client, _ = bundled
        response = client.get("/workflows/abc123")
        assert response.status_code == 200
        assert '<div id="root">' in response.text

    def test_static_asset_is_served(self, bundled):
        client, _ = bundled
        response = client.get("/assets/app.js")
        assert response.status_code == 200
        assert "console.log" in response.text

    @pytest.mark.parametrize(
        "path",
        ["/%2e%2e/%2e%2e/etc/passwd", "/..%2f..%2fetc%2fpasswd"],
    )
    def test_path_traversal_is_refused(self, bundled, path):
        client, _ = bundled
        response = client.get(path)
        assert response.status_code == 404
        assert "root:" not in response.text


class TestBundleAbsent:
    def test_studio_is_reported_as_missing(self, unbundled):
        _, module = unbundled
        assert module.STUDIO_BUNDLED is False

    def test_api_still_works(self, unbundled):
        client, _ = unbundled
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_root_explains_how_to_build(self, unbundled):
        client, _ = unbundled
        response = client.get("/")
        assert response.status_code == 200
        assert "build_studio.py" in response.text


class TestDisabled:
    def test_no_studio_env_var_skips_the_mount(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HYDRA_NO_STUDIO", "1")
        original = studio_mod.STUDIO_DIST
        try:
            module = _build_app(tmp_path, bundled=True)
            assert module.STUDIO_BUNDLED is False
            client = TestClient(module.app)
            assert client.get("/api/health").status_code == 200
        finally:
            studio_mod.STUDIO_DIST = original
