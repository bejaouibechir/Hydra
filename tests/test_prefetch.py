"""
Prechargement du lot suivant : garanties de comportement.

Le gain est mesure ailleurs ; ici on verifie que le thread ne change RIEN
au resultat : meme ordre, memes exceptions, arret propre, et desactivation
quand le lecteur ne relache pas le GIL.
"""

from __future__ import annotations

import threading
import time

import pytest

from hydra_etl.internal.runner.prefetch import (
    prefetch,
    prefetch_enabled,
    should_prefetch,
)


def test_ordre_conserve():
    assert list(prefetch(range(100), enabled=True)) == list(range(100))


def test_desactive_rend_la_source_telle_quelle():
    assert list(prefetch(range(10), enabled=False)) == list(range(10))


def test_source_vide():
    assert list(prefetch(iter([]), enabled=True)) == []


def test_exception_transmise_telle_quelle():
    class Particuliere(ValueError):
        pass

    def source():
        yield 1
        yield 2
        raise Particuliere("message d'origine")

    vus = []
    with pytest.raises(Particuliere, match="message d'origine"):
        for item in prefetch(source(), enabled=True):
            vus.append(item)
    assert vus == [1, 2]


def test_exception_des_le_premier_element():
    def source():
        raise RuntimeError("echec immediat")
        yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="echec immediat"):
        list(prefetch(source(), enabled=True))


def test_arret_anticipe_ferme_la_source():
    ferme = []

    def source():
        try:
            for i in range(1000):
                yield i
        finally:
            ferme.append(True)

    gen = prefetch(source(), enabled=True, size=1)
    premiers = [next(gen), next(gen)]
    gen.close()
    assert premiers == [0, 1]
    for _ in range(50):
        if ferme:
            break
        time.sleep(0.02)
    assert ferme, "le generateur source doit etre referme"


def test_pas_de_thread_survivant():
    avant = threading.active_count()
    for _ in range(5):
        assert list(prefetch(range(20), enabled=True)) == list(range(20))
    for _ in range(50):
        if threading.active_count() <= avant:
            break
        time.sleep(0.02)
    assert threading.active_count() <= avant


def test_la_source_avance_pendant_la_consommation():
    """Preuve du recouvrement : la source produit le lot n+1 avant que le
    consommateur ait fini de traiter le lot n."""
    produits = []

    def source():
        for i in range(5):
            produits.append(i)
            yield i

    avance_max = 0
    for i in prefetch(source(), enabled=True, size=1):
        time.sleep(0.05)  # simule la transformation du lot
        avance_max = max(avance_max, len(produits) - (i + 1))
    assert avance_max >= 1, "aucun lot n'a ete lu en avance"


# ------------------------------------------------------------- decision auto

class _AvecGil:
    def reader_releases_gil(self, table=None):
        return False


class _SansGil:
    def reader_releases_gil(self, table=None):
        return True


class _Muet:
    pass


def test_auto_suit_le_lecteur(monkeypatch):
    monkeypatch.delenv("HYDRA_PREFETCH", raising=False)
    assert prefetch_enabled() is None
    assert should_prefetch(_SansGil(), "t") is True
    assert should_prefetch(_AvecGil(), "t") is False
    assert should_prefetch(_Muet(), "t") is False


def test_variable_denvironnement_force_les_deux_sens(monkeypatch):
    monkeypatch.setenv("HYDRA_PREFETCH", "0")
    assert should_prefetch(_SansGil(), "t") is False
    monkeypatch.setenv("HYDRA_PREFETCH", "1")
    assert should_prefetch(_AvecGil(), "t") is True


def test_connecteur_qui_leve_ne_bloque_pas(monkeypatch):
    monkeypatch.delenv("HYDRA_PREFETCH", raising=False)

    class _Casse:
        def reader_releases_gil(self, table=None):
            raise RuntimeError("boum")

    assert should_prefetch(_Casse(), "t") is False


def test_csv_python_ne_prefetch_pas(monkeypatch, tmp_path):
    from hydra_etl.internal.connector.csv_connector import CSVConnector

    monkeypatch.delenv("HYDRA_PREFETCH", raising=False)
    monkeypatch.setenv("HYDRA_BACKEND", "python")
    conn = CSVConnector(name="s", config={"type": "csv"}, job_dir=str(tmp_path))
    assert should_prefetch(conn, "x.csv") is False
