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
2. Opérations globales (aggregate, sort, join right / outer) : au lieu de rassembler toutes les
   lignes en mémoire, chaque lot est versé dans une base DuckDB temporaire sur
   le disque, puis l'agrégation et le tri sont faits par DuckDB, en flux.
   Une opération globale qu'il ne sait pas traduire est rendue à pandas (sur
   le résultat de DuckDB), avec un message : jamais de repli silencieux.

Choix du moteur : `engine: auto | pandas | duckdb` dans transformations.yaml,
ou la variable HYDRA_ENGINE (prioritaire) ; auto par défaut.
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


def requested_engine(declared: Optional[str] = None) -> Tuple[str, str]:
    """(moteur demandé, origine) : HYDRA_ENGINE, sinon `engine:` de
    transformations.yaml, sinon auto."""
    env = os.environ.get("HYDRA_ENGINE", "").strip().lower()
    if env:
        if env not in ENGINES:
            raise ValueError(f"HYDRA_ENGINE='{env}' inconnu (attendu : {', '.join(ENGINES)})")
        return env, f"HYDRA_ENGINE={env}"
    val = str(declared or "auto").strip().lower()
    if val not in ENGINES:
        raise ValueError(f"engine: '{val}' inconnu (attendu : {', '.join(ENGINES)})")
    return val, f"engine: {val}"


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


def decide(requested: Any, has_global: bool, csv_path: Optional[Path]) -> Tuple[str, str]:
    """(moteur retenu, raison). `requested` : résultat de requested_engine()
    (ou simplement le nom du moteur)."""
    requested, origin = requested if isinstance(requested, tuple) else (requested, f"engine: {requested}")
    if requested == "pandas":
        return "pandas", origin
    if requested == "duckdb":
        if not available():
            raise ValueError(f"{origin} demande duckdb et pyarrow : pip install 'hydra-etl[duckdb]'")
        return "duckdb", origin
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
# fsum : somme compensée (Kahan), comme pandas — mêmes chiffres jusqu'au dernier décimal
_AGG_SQL = {"sum": "coalesce(fsum({c}), 0)", "count": "count({c})",
            "mean": "fsum({c}) / count({c})", "avg": "fsum({c}) / count({c})",
            "min": "min({c})", "max": "max({c})"}


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


_KEY_DTYPES = ("object", "str", "string", "int64")   # texte (pandas 2 / 3) ou entier


def _like_pandas(df: pd.DataFrame, str_cols: set = frozenset()) -> pd.DataFrame:
    """Types et vides au format pandas : colonnes texte « str » (pandas 3) rendues
    en str ; NaN (pas None) dans les colonnes objet ; entiers et booléens
    « nullables » de DuckDB rendus en types numpy (float / objet s'ils ont des
    vides, comme df.merge)."""
    import numpy as np
    for c in df.columns:
        dt = df[c].dtype
        if dt == object and c in str_cols:
            df[c] = df[c].astype("str")
        elif dt == object:
            if df[c].isna().any():
                df[c] = df[c].where(df[c].notna(), np.nan)
        elif isinstance(dt, pd.api.extensions.ExtensionDtype) and getattr(dt, "kind", "") in "iub":
            if df[c].isna().any():
                df[c] = (df[c].astype("float64") if dt.kind in "iu"
                         else df[c].astype(object).where(df[c].notna(), np.nan))
            else:
                df[c] = df[c].to_numpy(dtype=dt.numpy_dtype)
    return df


class DuckGlobal:
    """Base DuckDB temporaire : reçoit les lots, exécute aggregate, sort et les
    jointures right / outer."""

    def __init__(self) -> None:
        import duckdb
        self.dir = Path(tempfile.mkdtemp(prefix="hydra-duck-"))
        self.con = duckdb.connect(str(self.dir / "work.duckdb"))
        self.con.execute(f"SET temp_directory='{self.dir / 'spill'}'")
        self.rows = 0
        self._created = False
        self._dtypes: Dict[str, set] = {}      # types pandas vus par colonne, tous lots confondus
        self._empty: Optional[pd.DataFrame] = None
        self._joined = False
        self._str_right: set = set()           # colonnes texte « str » (pandas 3) venues d'une jointure

    def keep_only(self, steps: List[Dict[str, Any]]) -> None:
        """Si les opérations globales sont des jointures right / outer suivies
        d'une agrégation traduisible (cas courant), seules les colonnes utiles
        sont versées dans DuckDB : moins à copier. Les colonnes qui portent le nom
        d'une colonne de droite sont gardées (les suffixes « _r » ne changent pas)."""
        self.columns: Optional[set] = None
        i, joins = 0, []
        while i < len(steps) and self._step(steps[i])[0] == "join":
            joins.append(self._step(steps[i])[1])
            i += 1
        if i >= len(steps):
            return
        op, p = self._step(steps[i])
        if op != "aggregate" or self._sql(op, p, "t", check=False) is None:
            return
        by = p.get("by")
        need = set([by] if isinstance(by, str) else list(by or []))
        for out, spec in (p.get("agg") or {}).items():
            need.add(spec.get("col", out) if isinstance(spec, dict) else out)
        for jp in joins:
            rows = jp.get("_right_rows") or []
            if not rows:
                return
            for k in ("key", "left_key"):
                v = jp.get(k)
                need |= set([v] if isinstance(v, str) else list(v or []))
            need |= set().union(*(r.keys() for r in rows))
        self.columns = need

    def append(self, df: pd.DataFrame) -> None:
        cols = getattr(self, "columns", None)
        if cols:
            df = df[[c for c in df.columns if c in cols]]
        if self._empty is None:
            self._empty = df.iloc[:0]
        for c, dt in df.dtypes.items():
            self._dtypes.setdefault(str(c), set()).add(str(dt))
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
        a) est rendu à `pandas_tail(df, steps_restants, nb_faits)`."""
        if not self._created:
            return pd.DataFrame()
        if self.rows == 0:                    # rien à calculer : chemin pandas, à l'identique
            return pandas_tail(self._empty, steps, 0)
        # Un seul fil pour le calcul final (≈ 0,03 s) : sommes faites dans l'ordre
        # des lignes, comme pandas, au lieu de partiels combinés dans un ordre variable.
        self.con.execute("SET threads=1")
        rel, done = "t", 0
        for i, step in enumerate(steps):
            op, p = self._step(step)
            name = f"s{i}"
            if op == "join":
                if not self._join(p, rel, name):
                    break
            else:
                sql = self._sql(op, p, rel)
                if sql is None:
                    break
                # table (ordre des lignes figé, rowid) sauf pour la dernière étape, lue une fois
                kind = "VIEW" if i == len(steps) - 1 else "TABLE"
                self.con.execute(f"CREATE TEMP {kind} {name} AS {sql}")
            rel, done = name, i + 1
        df = self.con.execute(f"SELECT * FROM {rel}").df()
        str_cols = {c for c, dts in self._dtypes.items() if dts == {"str"}} | self._str_right
        if self._joined or str_cols:
            df = _like_pandas(df, str_cols)
        rest = steps[done:]
        if rest:
            logger.info("Moteur gros volumes : %d opération(s) globale(s) rendue(s) à pandas "
                        "(%s)", len(rest), ", ".join(self._step(s)[0] for s in rest))
            df = pandas_tail(df, rest, done)
        return df

    # ── join right / outer ───────────────────────────────────────────────────
    def _join(self, p: Dict[str, Any], rel: str, name: str) -> bool:
        """Jointure right / outer, mêmes lignes, colonnes, ordre et types que
        PandasEngine._op_join (df.merge(..., suffixes=("", "_r"))). Faux si un
        cas n'est pas garanti identique : pandas s'en charge (et donne ses erreurs)."""
        how = str(p.get("how", "inner")).lower()
        right_rows = p.get("_right_rows")
        if how not in ("right", "outer") or rel != "t" or not right_rows:
            return False                      # ordre des lignes connu seulement sur la table t
        right = pd.DataFrame(list(right_rows))
        lcols = list(self._dtypes)
        keys = p.get("key")
        if p.get("left_key") and p.get("right_key"):
            lk, rk = p["left_key"], p["right_key"]
            lk = [lk] if isinstance(lk, str) else list(lk)
            rk = [rk] if isinstance(rk, str) else list(rk)
            if len(lk) != len(rk) or any(c in lcols for c in rk):
                return False
            keys = None
        elif keys:
            keys = [keys] if isinstance(keys, str) else list(keys)
            lk = rk = keys
        else:
            return False
        for a, b in zip(lk, rk):
            if a not in lcols or b not in right.columns:
                return False
            dt = self._dtypes[a]
            # clés texte ou entières, de même type des deux côtés, sans vide :
            # pandas apparie les NaN entre eux, SQL non
            if len(dt) != 1 or next(iter(dt)) != str(right.dtypes[b]) or next(iter(dt)) not in _KEY_DTYPES:
                return False
            if right[b].isna().any() or self.con.execute(
                    f"SELECT count(*) FROM t WHERE {_q(a)} IS NULL").fetchall()[0][0]:
                return False
        sel, out = [], set(lcols)
        for c in lcols:
            if keys and c in keys:
                sel.append(f"coalesce(t.{_q(c)}, r.{_q(c)}) AS {_q(c)}")
            else:
                sel.append(f"t.{_q(c)} AS {_q(c)}")
        for c in right.columns:
            if keys and c in keys:
                continue
            col = f"{c}_r" if c in lcols else str(c)
            if col in out or str(c) == "__hydra_rn":
                return False
            out.add(col)
            sel.append(f"r.{_q(c)} AS {_q(col)}")
            if str(right.dtypes[c]) == "str":
                self._str_right.add(col)
        on = " AND ".join(f"t.{_q(a)} = r.{_q(b)}" for a, b in zip(lk, rk))
        if how == "right":                    # ordre de la droite, puis de la gauche
            join, order = "RIGHT JOIN", "r.__hydra_rn, t.rowid"
        else:                                 # clés triées, puis gauche, puis droite
            join = "FULL OUTER JOIN"
            order = ", ".join(f"coalesce(t.{_q(a)}, r.{_q(b)})" for a, b in zip(lk, rk))
            order += ", t.rowid NULLS LAST, r.__hydra_rn NULLS LAST"
        self.con.register("hydra_right", right.assign(__hydra_rn=range(len(right))))
        try:
            self.con.execute(f"CREATE TEMP TABLE r_{name} AS SELECT * FROM hydra_right")
        finally:
            self.con.unregister("hydra_right")
        self.con.execute(f"CREATE TEMP TABLE {name} AS SELECT {', '.join(sel)} FROM t {join} r_{name} r "
                         f"ON {on} ORDER BY {order}")
        # pandas passe en float une colonne entière qui reçoit des vides
        for col, typ in self.con.execute(
                f"SELECT column_name, data_type FROM information_schema.columns "
                f"WHERE table_name = '{name}'").fetchall():
            if typ in ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT",
                       "UINTEGER", "UBIGINT") and self.con.execute(
                    f"SELECT count(*) - count({_q(col)}) FROM {name}").fetchall()[0][0]:
                self.con.execute(f"ALTER TABLE {name} ALTER {_q(col)} TYPE DOUBLE")
        self._joined = True
        return True

    def _columns(self, rel: str) -> set:
        return {d[0] for d in self.con.execute(f"SELECT * FROM {rel} LIMIT 0").description}

    def _sql(self, op: str, p: Dict[str, Any], rel: str, check: bool = True) -> Optional[str]:
        """SQL d'une opération, ou None si elle n'est pas traduisible (ou si une
        colonne manque : pandas donne alors son propre message d'erreur)."""
        sql = self._sql_raw(op, p, rel)
        if sql is None or not check:
            return sql
        by = p.get("by")
        used = set([by] if isinstance(by, str) else list(by or []))
        if op == "aggregate":
            for out, spec in (p.get("agg") or {}).items():
                used.add(spec.get("col", out) if isinstance(spec, dict) else out)
        return sql if used <= self._columns(rel) else None

    def _sql_raw(self, op: str, p: Dict[str, Any], rel: str) -> Optional[str]:
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
            # rowid : à égalité, ordre d'arrivée (tri stable, comme pandas) ; rel est une table
            return f"SELECT * FROM {rel} ORDER BY {order}, rowid"
        return None

    def close(self) -> None:
        try:
            self.con.close()
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)
