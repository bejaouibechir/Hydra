"""
window.py — fonctions de fenêtre, communes au parseur, à pandas et à DuckDB.

    - window:
        partition_by: [customer_id]          # optionnel : sans lui, toute la table
        order_by: [{col: order_date, desc: false}]   # ou [order_date]
        columns:
          order_rank:  {func: row_number}
          prev_amount: {func: lag, col: amount, offset: 1, default: 0}

Règles (identiques en pandas et en DuckDB) :
- les lignes gardent leur ordre d'entrée ; seules des colonnes sont ajoutées ;
- tri par order_by, valeurs nulles en dernier (même en desc), égalités
  départagées par l'ordre d'entrée (row_number, lag, lead déterministes) ;
- rank / dense_rank : lignes égales sur order_by = même rang (nulles égales
  entre elles) ;
- lag / lead : hors de la partition -> default (nul si absent) ;
- cumuls (cumsum, cumcount, cummin, cummax) : de la 1re ligne de la partition
  à la ligne courante, dans l'ordre order_by ; une valeur nulle est sautée (la
  ligne garde le cumul atteint ; nulle tant qu'aucune valeur n'est vue) ;
- agrégats de partition (sum, mean, min, max, count, first, last) : valeur de
  toute la partition sur chaque ligne ; valeurs nulles ignorées, comme
  `aggregate` (sum d'une partition sans valeur = 0) ; first / last : première
  / dernière valeur non nulle dans l'ordre order_by (ordre d'entrée sans lui).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

RANK_FUNCS = ("row_number", "rank", "dense_rank")
OFFSET_FUNCS = ("lag", "lead")
CUM_FUNCS = ("cumsum", "cumcount", "cummin", "cummax")
PART_FUNCS = ("sum", "mean", "min", "max", "count", "first", "last")
FUNCS = RANK_FUNCS + OFFSET_FUNCS + CUM_FUNCS + PART_FUNCS
NEEDS_ORDER = RANK_FUNCS + OFFSET_FUNCS + CUM_FUNCS
NUMERIC_ONLY = ("cumsum", "cummin", "cummax", "sum", "mean")
_KEYS = {
    **{f: set() for f in RANK_FUNCS},
    **{f: {"col", "offset", "default"} for f in OFFSET_FUNCS},
    **{f: {"col"} for f in CUM_FUNCS + PART_FUNCS},
}
_COL_OPTIONAL = ("cumcount",)


class WindowSpecError(ValueError):
    pass


def as_list(v: Any) -> List[str]:
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


def order_spec(order_by: Any) -> List[Tuple[str, bool]]:
    """[(colonne, desc)] depuis [col] ou [{col, desc}]."""
    out: List[Tuple[str, bool]] = []
    for item in as_list(order_by):
        if isinstance(item, str):
            out.append((item, False))
        elif isinstance(item, dict):
            unknown = set(item) - {"col", "desc"}
            if unknown or not isinstance(item.get("col"), str) or not item["col"].strip():
                raise WindowSpecError("window.order_by: each item is a column name or {col, desc}")
            desc = item.get("desc", False)
            if not isinstance(desc, bool):
                raise WindowSpecError("window.order_by: desc must be true or false")
            out.append((item["col"].strip(), desc))
        else:
            raise WindowSpecError("window.order_by: each item is a column name or {col, desc}")
    return out


def check(params: Dict[str, Any]) -> None:
    """Validation complète (parseur et moteur) : message clair, jamais d'option ignorée."""
    if not isinstance(params, dict):
        raise WindowSpecError("window: expected a mapping (partition_by, order_by, columns)")
    unknown = set(params) - {"partition_by", "order_by", "columns"} - {k for k in params if str(k).startswith("_")}
    if unknown:
        raise WindowSpecError(f"window: unknown option(s): {', '.join(sorted(map(str, unknown)))}")
    part = params.get("partition_by")
    if part is not None and not (isinstance(part, str) and part.strip() or
                                 isinstance(part, list) and part and all(isinstance(c, str) and c.strip() for c in part)):
        raise WindowSpecError("window.partition_by: a column name or a list of column names")
    order = order_spec(params.get("order_by"))
    cols = params.get("columns")
    if not isinstance(cols, dict) or not cols:
        raise WindowSpecError("window.columns: at least one output column, e.g. {rank: {func: row_number}}")
    for name, spec in cols.items():
        if not isinstance(name, str) or not name.strip():
            raise WindowSpecError("window.columns: output column names cannot be empty")
        if not isinstance(spec, dict) or "func" not in spec:
            raise WindowSpecError(f"window.columns.{name}: expected {{func: ...}}")
        func = str(spec["func"]).strip().lower()
        if func not in FUNCS:
            raise WindowSpecError(f"window.columns.{name}: function '{spec['func']}' is not supported "
                                  f"(expected: {', '.join(FUNCS)})")
        given = {k for k, v in spec.items() if v is not None}     # None = absent (modèle Pydantic)
        extra = given - {"func"} - _KEYS[func]
        if extra:
            raise WindowSpecError(f"window.columns.{name}: option(s) {', '.join(sorted(map(str, extra)))} "
                                  f"not allowed with {func}")
        if not order and func in NEEDS_ORDER:
            raise WindowSpecError(f"window.columns.{name}: {func} needs window.order_by")
        if "col" in _KEYS[func] and (func not in _COL_OPTIONAL or spec.get("col") is not None):
            if not isinstance(spec.get("col"), str) or not spec["col"].strip():
                raise WindowSpecError(f"window.columns.{name}: {func} needs col (the column to read)")
        if func in OFFSET_FUNCS:
            off = spec.get("offset")
            off = 1 if off is None else off
            if isinstance(off, bool) or not isinstance(off, int) or off < 1:
                raise WindowSpecError(f"window.columns.{name}: offset must be an integer >= 1")
            d = spec.get("default")
            if d is not None and not isinstance(d, (str, int, float, bool)):
                raise WindowSpecError(f"window.columns.{name}: default must be a single value")


def used_columns(params: Dict[str, Any]) -> List[str]:
    cols = as_list(params.get("partition_by")) + [c for c, _ in order_spec(params.get("order_by"))]
    for spec in (params.get("columns") or {}).values():
        if isinstance(spec, dict) and isinstance(spec.get("col"), str):
            cols.append(spec["col"])
    return list(dict.fromkeys(cols))


def outputs(params: Dict[str, Any]) -> List[str]:
    return list((params.get("columns") or {}).keys())


# ── pandas ──────────────────────────────────────────────────────────────────
def apply_pandas(df, params: Dict[str, Any]):
    import numpy as np
    import pandas as pd

    check(params)
    part = as_list(params.get("partition_by"))
    order = order_spec(params.get("order_by"))
    specs = params["columns"]
    missing = [c for c in used_columns(params) if c not in df.columns]
    if missing:
        raise ValueError(f"window: column(s) not found: {', '.join(missing)} "
                         f"(available: {', '.join(map(str, df.columns))})")
    clash = [c for c in specs if c in df.columns]
    if clash:
        raise ValueError(f"window: output column(s) already exist: {', '.join(clash)} — choose other names")
    for name, spec in specs.items():
        func = str(spec["func"]).strip().lower()
        if func in NUMERIC_ONLY and df[spec["col"]].dtype.kind not in "iuf":
            raise ValueError(f"window.columns.{name}: {func} needs a numeric column "
                             f"('{spec['col']}' is {df[spec['col']].dtype}) — cast it first")

    n = len(df)
    keys = part + [c for c, _ in order]
    tmp = pd.DataFrame({f"k{i}": df[c].to_numpy() for i, c in enumerate(keys)})
    tmp["__pos"] = np.arange(n)
    if n:
        tmp = tmp.sort_values([f"k{i}" for i in range(len(keys))],
                              ascending=[True] * len(part) + [not d for _, d in order],
                              na_position="last", kind="mergesort")
    pos = tmp["__pos"].to_numpy()

    def changed(s):
        prev = s.shift()
        same = (s == prev) | (s.isna() & prev.isna())
        return ~same.fillna(False).astype(bool)

    if part:
        new_group = np.zeros(n, dtype=bool)
        for i in range(len(part)):
            new_group |= changed(tmp[f"k{i}"]).to_numpy()
        if n:
            new_group[0] = True
    else:
        new_group = np.zeros(n, dtype=bool)
        if n:
            new_group[0] = True
    gid = pd.Series(np.cumsum(new_group), index=tmp.index)
    rn = gid.groupby(gid).cumcount() + 1
    size = gid.map(gid.value_counts())
    peer = new_group.copy()
    for i in range(len(part), len(keys)):
        peer |= changed(tmp[f"k{i}"]).to_numpy()
    peer_s = pd.Series(peer, index=tmp.index)

    out = lazy_copy(df)
    for name, spec in specs.items():
        func = str(spec["func"]).strip().lower()
        if func == "row_number":
            vals = rn.to_numpy(dtype="int64")
        elif func == "dense_rank":
            vals = peer_s.astype("int64").groupby(gid).cumsum().to_numpy(dtype="int64")
        elif func == "rank":
            vals = rn.where(peer_s).groupby(gid).ffill().to_numpy(dtype="int64")
        elif func == "cumcount" and spec.get("col") is None:
            vals = rn.to_numpy(dtype="int64")
        elif func in CUM_FUNCS or func in PART_FUNCS:
            col = spec["col"]
            srcs = pd.Series(df[col].to_numpy()[pos], index=tmp.index, dtype=df[col].dtype)
            grp = srcs.groupby(gid)
            if func == "cumcount":
                res_s = srcs.notna().astype("int64").groupby(gid).cumsum()
            elif func in CUM_FUNCS:
                res_s = getattr(grp, func)()
                if res_s.isna().any():
                    res_s = res_s.groupby(gid).ffill()
                if df[col].dtype.kind in "iu" and not res_s.isna().any():
                    res_s = res_s.astype("int64")
            elif func in ("min", "max"):
                vals_nn = srcs.dropna()              # texte : pandas ne saute pas les vides
                per = vals_nn.groupby(gid.loc[vals_nn.index]).agg(func)
                res_s = gid.map(per)
                if df[col].dtype.kind in "iuf" and res_s.dtype == object:
                    res_s = res_s.astype("float64")
            else:
                res_s = grp.transform(func)
                if func == "count":
                    res_s = res_s.astype("int64")
            if res_s.dtype == object:
                res_s = res_s.where(res_s.notna(), None)
            vals = res_s.array
        else:
            col, off = spec["col"], int(spec.get("offset") or 1)
            src = df[col].to_numpy()[pos]
            srcs = pd.Series(src, index=tmp.index, dtype=df[col].dtype)
            shifted = srcs.groupby(gid).shift(off if func == "lag" else -off)
            outside = (rn <= off) if func == "lag" else (rn > size - off)
            default = spec.get("default")
            if default is not None:
                shifted = shifted.astype(object) if isinstance(default, str) and shifted.dtype.kind in "biuf" \
                    else shifted
                shifted[outside] = default
            if df[col].dtype.kind in "iu" and not shifted.isna().any() and \
                    (default is None or (isinstance(default, int) and not isinstance(default, bool))):
                shifted = shifted.astype("int64")
            if shifted.dtype == object:          # vides : None (comme une colonne texte lue), pas NaN
                shifted = shifted.where(shifted.notna(), None)
            vals = shifted.array
        # entier « nullable » (cast: int) sans vide -> int64, comme DuckDB le rend
        if str(getattr(vals, "dtype", "")) == "Int64" and not pd.isna(vals).any():
            vals = vals.astype("int64")
        if str(getattr(vals, "dtype", "")) == "Float64":       # moyenne d'un Int64 : DOUBLE chez DuckDB
            vals = vals.to_numpy(dtype="float64", na_value=np.nan)
        if n:
            # remise dans l'ordre d'entrée, type conservé (Int64 compris)
            res = pd.Series(vals, index=pos).sort_index().array
        else:
            res = np.array([], dtype="int64")
        if not n and func in OFFSET_FUNCS + ("first", "last", "min", "max", "cummin", "cummax", "cumsum", "sum") \
                and spec.get("col") is not None:
            res = df[spec["col"]].to_numpy()[:0]
        if not n and func == "mean":
            res = np.array([], dtype="float64")
        out[name] = res
    return out


def lazy_copy(df):
    from hydra_etl.internal.engines.frame_copy import lazy_copy as lc
    return lc(df)


# ── DuckDB ──────────────────────────────────────────────────────────────────
def _literal(v: Any) -> str:
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def sql(params: Dict[str, Any], rel: str, dtypes: Dict[str, set], q) -> Optional[Tuple[str, List[str]]]:
    """(SELECT de la fenêtre, colonnes à passer en DOUBLE si elles ont des vides),
    ou None si le résultat ne serait pas garanti identique à pandas (pandas
    s'en charge alors). Entier numpy + vides -> float chez pandas ; entier
    « nullable » (Int64) -> reste entier, comme DuckDB le rend."""
    to_double: List[str] = []
    try:
        check(params)
    except WindowSpecError:
        return None                                  # pandas donnera le message
    safe = {"int64", "Int64", "float64", "object", "str", "string"}
    for c in used_columns(params):
        dt = dtypes.get(c)
        if not dt or len(dt) != 1 or next(iter(dt)) not in safe:
            return None
    part = as_list(params.get("partition_by"))
    order = order_spec(params.get("order_by"))
    pb = f"PARTITION BY {', '.join(q(c) for c in part)} " if part else ""
    ob = ", ".join(f"{q(c)} {'DESC' if d else 'ASC'} NULLS LAST" for c, d in order)
    obr = f"{ob}, rowid" if ob else "rowid"
    sel = []
    for name, spec in params["columns"].items():
        func = str(spec["func"]).strip().lower()
        if func in CUM_FUNCS or func in PART_FUNCS:
            col = spec.get("col")
            kind = next(iter(dtypes[col])) if col else None
            if func in NUMERIC_ONLY and kind not in ("int64", "Int64", "float64"):
                return None                          # pandas donne le message
            c = q(col) if col else "*"
            if func in CUM_FUNCS:
                agg = {"cumsum": "sum", "cumcount": "count", "cummin": "min", "cummax": "max"}[func]
                expr = f"{agg}({c}) OVER ({pb}ORDER BY {obr} ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)"
                if func == "cumsum" and kind in ("int64", "Int64"):
                    expr = f"CAST({expr} AS BIGINT)"
            elif func in ("first", "last"):
                expr = (f"{func}_value({c} IGNORE NULLS) OVER ({pb}ORDER BY {obr} "
                        f"ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)")
            else:
                agg = {"sum": "fsum", "mean": "avg", "min": "min", "max": "max", "count": "count"}[func]
                if func == "sum" and kind in ("int64", "Int64"):
                    agg = "sum"
                expr = f"{agg}({c}) OVER ({pb.strip()})"
                if func == "sum":
                    expr = f"CAST(coalesce({expr}, 0) AS {'DOUBLE' if kind == 'float64' else 'BIGINT'})"
            sel.append(f"{expr} AS {q(name)}")
            continue
        if func in ("rank", "dense_rank"):
            over = f"OVER ({pb}ORDER BY {ob})"
            sel.append(f"{func}() {over} AS {q(name)}")
            continue
        over = f"OVER ({pb}ORDER BY {ob}, rowid)"
        if func == "row_number":
            sel.append(f"row_number() {over} AS {q(name)}")
            continue
        col, off, d = spec["col"], int(spec.get("offset") or 1), spec.get("default")
        kind = next(iter(dtypes[col]))
        if d is not None:
            numeric = kind in ("int64", "Int64", "float64")
            if isinstance(d, bool) or numeric != isinstance(d, (int, float)) or kind == "bool":
                return None
            if kind in ("int64", "Int64") and isinstance(d, float):
                return None
        elif kind == "int64":
            to_double.append(name)
        args = f"{q(col)}, {off}" + (f", {_literal(d)}" if d is not None else "")
        sel.append(f"{func}({args}) {over} AS {q(name)}")
    return f"SELECT *, {', '.join(sel)} FROM {rel} ORDER BY rowid", to_double
