# -*- coding: utf-8 -*-
"""
Fixtures de fidelite : sortie de reference du **vrai** moteur Hydra.

Pour chaque operation du DSL, execute PandasEngine sur le jeu canonique et enregistre
entree + parametres + sortie attendue dans hydra-site/src/_fixtures/<op>.json.

Le moteur JavaScript du site doit reproduire ces sorties a l'identique. Toute divergence
signifie que le site enseigne un Hydra imaginaire.

Usage : python scripts/gen_fixtures.py
"""
from __future__ import annotations

import json
import math
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from hydra_etl.internal.engines.pandas_engine import PandasEngine  # noqa: E402

DATA = os.path.join(ROOT, "data", "canonical")
OUT = os.path.join(os.path.dirname(ROOT), "hydra-site", "src", "_fixtures")
E = PandasEngine()


def load(name):
    return pd.read_csv(os.path.join(DATA, f"{name}.csv"), dtype=str, keep_default_na=True)


def jsonable(df: pd.DataFrame):
    """DataFrame -> liste de dicts JSON purs. NaN/NA -> null, numpy -> natif."""
    rows = []
    for rec in df.to_dict("records"):
        row = {}
        for k, v in rec.items():
            if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
                row[str(k)] = None
            elif hasattr(v, "item"):
                row[str(k)] = v.item()
            else:
                row[str(k)] = v
        rows.append(row)
    return rows


orders = load("orders")
customers = load("customers")
orders_extra = load("orders_extra")
revenue_wide = load("revenue_wide")

# base typee : la plupart des operations numeriques partent de la
orders_typed = E._op_cast(orders, {"mapping": {"quantity": "int", "amount": "float"}})

CASES = [
    ("select",      orders,        {"columns": ["order_id", "amount", "status"]}, None),
    ("rename",      orders,        {"mapping": {"amount": "revenue", "status": "state"}}, None),
    ("cast",        orders,        {"mapping": {"quantity": "int", "amount": "float"}}, None),
    ("filter",      orders_typed,  {"expr": "amount > 30"}, None),
    ("calculate",   orders_typed,  {"column": "unit", "expr": "amount / quantity"}, None),
    ("sort",        orders_typed,  {"by": ["amount"], "ascending": False}, None),
    ("deduplicate", orders,        {}, None),
    ("fill_null",   orders,        {"columns": {"amount": "0.00"}}, None),
    ("trim",        customers,     {"columns": ["name"]}, None),
    ("clean",       customers,     {"columns": ["name"], "case": "lower"}, None),
    ("aggregate",   orders_typed,  {"by": ["status"],
                                    "agg": {"total": {"func": "sum", "col": "amount"},
                                            "n": {"func": "count", "col": "order_id"}}}, None),
    ("join",        orders,        {"key": "customer_id", "how": "left"}, "customers"),
    ("merge",       customers,     {"key": "customer_id"}, "customers"),
    ("union",       orders,        {"distinct": False}, "orders_extra"),
    ("pivot",       orders_typed,  {"index": ["customer_id"], "column": "status",
                                    "values": "amount", "aggfunc": "sum"}, None),
    ("unpivot",     revenue_wide,  {"id_vars": ["region"], "var_name": "quarter",
                                    "value_name": "revenue"}, None),
    ("transpose",   revenue_wide,  {"index_col": "region"}, None),
]

RIGHTS = {"customers": customers, "orders_extra": orders_extra}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    index = []
    for op, df_in, params, right_name in CASES:
        p = dict(params)
        if right_name:
            p["_right_rows"] = RIGHTS[right_name].to_dict("records")
            p["right"] = right_name
        result = getattr(E, f"_op_{op}")(df_in, p)

        public = {k: v for k, v in p.items() if not k.startswith("_")}
        fixture = {
            "op": op,
            "params": public,
            "input": jsonable(df_in),
            "right": jsonable(RIGHTS[right_name]) if right_name else None,
            "expected": jsonable(result),
        }
        path = os.path.join(OUT, f"{op}.json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(fixture, f, ensure_ascii=False, indent=1)
            f.write("\n")
        index.append({"op": op, "rows_in": len(fixture["input"]), "rows_out": len(fixture["expected"])})
        print(f"  {op:12} {len(fixture['input']):3} -> {len(fixture['expected']):3} lignes")

    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"generated_from": "PandasEngine", "cases": index}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"\n{len(index)} fixtures ecrites dans {OUT}")
    print("script : non simule dans le navigateur, aucune fixture")
