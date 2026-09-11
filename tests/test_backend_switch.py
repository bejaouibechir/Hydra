"""
Aiguillage Python / Rust (hydra_etl/_backend.py) : priorités, configuration,
repli avec avertissement unique quand Rust est indisponible.
"""
from __future__ import annotations

import warnings

import pytest

from hydra_etl import _backend


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.delenv("HYDRA_BACKEND", raising=False)
    monkeypatch.setenv("HYDRA_BACKENDS_FILE", str(tmp_path / "absent.yaml"))
    _backend.reload()
    yield
    _backend.reload()


def _config(monkeypatch, tmp_path, text):
    p = tmp_path / "hydra.backends.yaml"
    p.write_text(text, encoding="utf-8")
    monkeypatch.setenv("HYDRA_BACKENDS_FILE", str(p))
    _backend.reload()


def test_default_is_python():
    assert _backend.resolve("csv.read") == "python"


def test_env_default(monkeypatch):
    monkeypatch.setenv("HYDRA_BACKEND", "rust")
    assert _backend.resolve("csv.read") == "rust"


def test_priority_param_over_overrides_over_default(monkeypatch, tmp_path):
    _config(monkeypatch, tmp_path, "default: rust\noverrides:\n  csv.read: python\n")
    monkeypatch.setenv("HYDRA_BACKEND", "python")
    assert _backend.resolve("other.op") == "rust"            # default du fichier > env
    assert _backend.resolve("csv.read") == "python"          # override > default
    assert _backend.resolve("csv.read", backend="rust") == "rust"  # paramètre > tout


def test_config_read_once(monkeypatch, tmp_path):
    _config(monkeypatch, tmp_path, "default: rust\n")
    assert _backend.resolve("x") == "rust"
    (tmp_path / "hydra.backends.yaml").write_text("default: python\n", encoding="utf-8")
    assert _backend.resolve("x") == "rust"                   # pas relu
    _backend.reload()
    assert _backend.resolve("x") == "python"


def test_invalid_values_warn_and_are_ignored(monkeypatch, tmp_path):
    _config(monkeypatch, tmp_path, "default: turbo\n")
    with pytest.warns(RuntimeWarning, match="invalid backend value"):
        assert _backend.resolve("x") == "python"
    with pytest.warns(RuntimeWarning, match="invalid backend value"):
        assert _backend.resolve("x", backend="gpu") == "python"


class _Op:
    @_backend.dual("test.op", rust="_rust")
    def run(self, x):
        return ("python", x)

    def _rust(self, x):
        return ("rust", x)


def test_dual_uses_python_by_default():
    assert _Op().run(1) == ("python", 1)


def test_dual_uses_rust_when_available(monkeypatch):
    monkeypatch.setattr(_backend, "native_status", lambda: (True, ""))
    assert _Op().run(2, backend="rust") == ("rust", 2)


def test_dual_falls_back_with_single_warning(monkeypatch):
    monkeypatch.setattr(_backend, "native_status", lambda: (False, "hydra_native not installed"))
    with pytest.warns(RuntimeWarning, match="unavailable"):
        assert _Op().run(3, backend="rust") == ("python", 3)
    with warnings.catch_warnings():
        warnings.simplefilter("error")                       # plus aucun avertissement
        assert _Op().run(4, backend="rust") == ("python", 4)
