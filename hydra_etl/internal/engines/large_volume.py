"""
large_volume.py — moteur « gros volumes » (optionnel, `pip install hydra-etl[duckdb]`).

Même principe que l'accélérateur `native` : pandas reste la référence et le
moteur par défaut ; au-delà d'un seuil, deux étapes changent de moteur, avec
le même résultat.

1. Lecture CSV (CSVConnector._extract_frames_arrow) : pyarrow (C++, plusieurs cœurs), en grands lots, au lieu du
   module `csv` ligne par ligne. Valeurs rendues en texte, comme le lecteur
   Python ; les opérations ligne à ligne (filter, cast, join interne,
   calculate…) restent exécutées par pandas, lot par lot : même code, mêmes
   résultats.
2. Opérations globales (aggregate, sort) : au lieu de rassembler toutes les
   lignes en mémoire, chaque lot est versé dans une base DuckDB temporaire sur
   le disque, puis l'agrégation et le tri sont faits par DuckDB, en flux.
   Une opération globale qu'il ne sait pas traduire est rendue à pandas (sur
   le résultat de DuckDB), avec un message : jamais de repli silencieux.

Choix du moteur : variable HYDRA_ENGINE = auto (défaut) | pandas | duckdb.
`auto` : DuckDB si le job a
une opération globale et que la source dépasse HYDRA_LARGE_VOLUME_ROWS lignes
estimées (2 000 000 par défaut) ; sinon pandas.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

ENGINES = ("auto", "pandas", "duckdb")
DEFAULT_THRESHOLD = 2_000_000
_WARNED: set = set()


def available() -> bool:
    try:
        import duckdb  # noqa: F401
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


def threshold() -> int:
    try:
        return int(os.environ.get("HYDRA_LARGE_VOLUME_ROWS", DEFAULT_THRESHOLD))
    except ValueError:
        return DEFAULT_THRESHOLD


def requested_engine(transforms_raw: Any = None) -> str:  # noqa: ARG001 — clé DSL `engine:` à venir
    """Moteur demandé : HYDRA_ENGINE (auto | pandas | duckdb), auto par défaut.
    La clé `engine:` de transformations.yaml viendra avec son support DSL / Studio."""
    val = os.environ.get("HYDRA_ENGINE", "").strip().lower() or "auto"
    if val not in ENGINES:
        raise ValueError(f"HYDRA_ENGINE='{val}' inconnu (attendu : {', '.join(ENGINES)})")
    return val


def estimate_csv_rows(path: Path) -> int:
    """Lignes estimées d'un CSV : taille du fichier / longueur moyenne des
    premières lignes (lecture de 256 Ko au plus)."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            head = f.read(262_144)
        lines = head.count(b"\n")
        if lines <= 1:
            return 0
        return int(size / (len(head) / lines))
    except OSError:
        return 0


def decide(requested: str, has_global: bool, csv_path: Optional[Path]) -> Tuple[str, str]:
    """(moteur retenu, raison)."""
    if requested == "pandas":
        return "pandas", "HYDRA_ENGINE=pandas"
    if requested == "duckdb":
        if not available():
            raise ValueError("HYDRA_ENGINE=duckdb demande duckdb et pyarrow : pip install 'hydra-etl[duckdb]'")
        return "duckdb", "HYDRA_ENGINE=duckdb"
    # auto
    if not has_global:
        return "pandas", "auto : aucune opération globale"
    rows = estimate_csv_rows(csv_path) if csv_path else 0
    if rows < threshold():
        return "pandas", f"auto : ≈ {rows:,} lignes estimées (< {threshold():,})".replace(",", " ")
    if not available():
        key = "auto-missing"
        if key not in _WARNED:
            _WARNED.add(key)
            logger.warning("Gros volume (≈ %s lignes) : installez 'hydra-etl[duckdb]' pour le moteur "
                           "gros volumes ; pandas utilisé.", f"{rows:,}")
        return "pandas", "auto : duckdb non installé"
    return "duckdb", f"auto : ≈ {rows:,} lignes estimées (≥ {threshold():,})".replace(",", " ")


# La lecture CSV rapide est dans CSVConnector._extract_frames_arrow (projection,
# reprise par le lecteur Python).


# ── Opérations globales dans DuckDB ──────────────────────────────────────────
_AGG_SQL = {"sum": "coalesce(sum({c}), 0)", "count": "count({c})", "mean": "avg({c})",
            "avg": "avg({c})", "min": "min({c})", "max": "max({c})"}


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


class DuckGlobal:
    """Base DuckDB temporaire : reçoit les lots, exécute aggregate / sort."""

    def __init__(self) -> None:
        import duckdb
        self.dir = Path(tempfile.mkdtemp(prefix="hydra-duck-"))
        self.con = duckdb.connect(str(self.dir / "work.duckdb"))
        self.con.execute(f"SET temp_directory='{self.dir / 'spill'}'")
        self.rows = 0
        self._created = False

    def keep_only(self, steps: List[Dict[str, Any]]) -> None:
        """Si la 1re opération globale est une agrégation traduisible, seules ses
        colonnes (clés + sources) sont versées dans DuckDB : moins à copier."""
        self.columns: Optional[List[str]] = None
        if not steps:
            return
        op, p = self._step(steps[0])
        if op != "aggregate" or self._sql(op, p, "t") is None:
            return
        by = p.get("by")
        cols = [by] if isinstance(by, str) else list(by or [])
        for out, spec in (p.get("agg") or {}).items():
            src = spec.get("col", out) if isinstance(spec, dict) else out
            if src not in cols:
                cols.append(src)
        self.columns = cols

    def append(self, df: pd.DataFrame) -> None:
        cols = getattr(self, "columns", None)
        if cols and all(c in df.columns for c in cols):
            df = df[cols]
        self.con.register("hydra_batch", df)
        try:
            if not self._created:
                self.con.execute("CREATE TABLE t AS SELECT * FROM hydra_batch")
                self._created = True
            else:
                self.con.execute("INSERT INTO t BY NAME SELECT * FROM hydra_batch")
        finally:
            self.con.unregister("hydra_batch")
        self.rows += len(df)

    @staticmethod
    def _step(step: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        if "op" in step:
            return str(step["op"]).strip().lower(), step.get("params") or {}
        op, params = next(iter(step.items()))
        return str(op).strip().lower(), params if isinstance(params, dict) else {}

    def run(self, steps: List[Dict[str, Any]], pandas_tail) -> pd.DataFrame:
        """Exécute les steps globaux traduisibles dans DuckDB ; le reste (s'il y en
        a) est rendu à `pandas_tail(df, steps_restants)`."""
        if not self._created:
            return pd.DataFrame()
        rel, done = "t", 0
        for i, step in enumerate(steps):
            op, p = self._step(step)
            sql = self._sql(op, p, rel)
            if sql is None:
                break
            name = f"s{i}"
            self.con.execute(f"CREATE TEMP VIEW {name} AS {sql}")
            rel, done = name, i + 1
        df = self.con.execute(f"SELECT * FROM {rel}").df()
        rest = steps[done:]
        if rest:
            logger.info("Moteur gros volumes : %d opération(s) globale(s) rendue(s) à pandas "
                        "(%s)", len(rest), ", ".join(self._step(s)[0] for s in rest))
            df = pandas_tail(df, rest, done)
        return df

    def _sql(self, op: str, p: Dict[str, Any], rel: str) -> Optional[str]:
        if op == "aggregate":
            by = p.get("by")
            by = [by] if isinstance(by, str) else list(by or [])
            agg = p.get("agg") or {}
            if not by or not isinstance(agg, dict):
                return None
            cols = []
            for out, spec in agg.items():
                if isinstance(spec, dict):
                    func, src = str(spec.get("func", "sum")).lower(), spec.get("col", out)
                else:
                    func, src = str(spec).lower(), out
                tpl = _AGG_SQL.get(func)
                if tpl is None:
                    return None
                cols.append(f"{tpl.format(c=_q(src))} AS {_q(out)}")
            keys = ", ".join(_q(b) for b in by)
            not_null = " AND ".join(f"{_q(b)} IS NOT NULL" for b in by)   # pandas : dropna
            return (f"SELECT {keys}, {', '.join(cols)} FROM {rel} WHERE {not_null} "
                    f"GROUP BY {keys} ORDER BY {keys}")                    # pandas : sort=True
        if op == "sort":
            by = p.get("by")
            by = [by] if isinstance(by, str) else list(by or [])
            asc = p.get("ascending", True)
            asc = asc if isinstance(asc, list) else [asc] * len(by)
            if not by or len(asc) != len(by):
                return None
            order = ", ".join(f"{_q(b)} {'ASC' if a else 'DESC'} NULLS LAST" for b, a in zip(by, asc))
            return f"SELECT * FROM {rel} ORDER BY {order}"
        return None

    def close(self) -> None:
        try:
            self.con.close()
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)
