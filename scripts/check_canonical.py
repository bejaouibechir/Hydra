# -*- coding: utf-8 -*-
"""
Verifie que le jeu canonique donne matiere aux 18 operations du DSL.

Chaque operation est executee par le **vrai** PandasEngine, et son resultat doit etre
non trivial : une operation qui ne change rien sur ce jeu signale un jeu mal concu.

Usage : python scripts/check_canonical.py
Sortie : code 0 si les 18 passent.
"""
from __future__ import annotations

import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from hydra_etl.internal.engines.pandas_engine import PandasEngine  # noqa: E402

DATA = os.path.join(ROOT, "data", "canonical")
E = PandasEngine()

def load(name):
    return pd.read_csv(os.path.join(DATA, f"{name}.csv"), dtype=str, keep_default_na=True)

orders = load("orders")
customers = load("customers")
products = load("products")
orders_extra = load("orders_extra")
revenue_wide = load("revenue_wide")

results = []

def check(op, cond, detail):
    results.append((op, bool(cond), detail))

# 1 select
r = E._op_select(orders, {"columns": ["order_id", "amount", "status"]})
check("select", r.shape[1] == 3 and r.shape[1] < orders.shape[1], f"{orders.shape[1]} -> {r.shape[1]} colonnes")

# 2 rename
r = E._op_rename(orders, {"mapping": {"amount": "revenue"}})
check("rename", "revenue" in r.columns and "amount" not in r.columns, "amount -> revenue")

# 3 cast
r = E._op_cast(orders, {"mapping": {"quantity": "int", "amount": "float"}})
check("cast", str(r["quantity"].dtype) != "object" and str(r["amount"].dtype) != "object",
      f'quantity {orders["quantity"].dtype} -> {r["quantity"].dtype}')

# 4 filter
base = E._op_cast(orders, {"mapping": {"amount": "float"}})
r = E._op_filter(base, {"expr": "amount > 30"})
check("filter", 0 < len(r) < len(orders), f"{len(orders)} -> {len(r)} lignes")

# 5 calculate
r = E._op_calculate(E._op_cast(orders, {"mapping": {"quantity": "int", "amount": "float"}}),
                    {"column": "unit", "expr": "amount / quantity"})
check("calculate", "unit" in r.columns and r["unit"].notna().any(), "colonne unit creee")

# 6 sort
r = E._op_sort(base, {"by": ["amount"], "ascending": False})
check("sort", list(r["order_id"]) != list(orders["order_id"]), "ordre modifie")

# 7 deduplicate
r = E._op_deduplicate(orders, {})
check("deduplicate", len(r) == len(orders) - 2, f"{len(orders)} -> {len(r)} lignes, 2 doublons retires")

# 8 fill_null
nulls_before = int(orders["amount"].isna().sum())
r = E._op_fill_null(orders, {"value": "0.00", "columns": {"amount": "0.00"}})
check("fill_null", nulls_before > 0 and int(r["amount"].isna().sum()) == 0,
      f"{nulls_before} valeurs manquantes comblees")

# 9 trim
r = E._op_trim(customers, {"columns": ["name"]})
check("trim", (r["name"] != customers["name"]).any(), "espaces de bord retires")

# 10 clean
r = E._op_clean(customers, {"columns": ["name"], "case": "lower"})
changed = int((r["name"] != customers["name"]).sum())
check("clean", changed >= 6, f"{changed} valeurs normalisees sur {len(customers)}")

# 11 aggregate
r = E._op_aggregate(base, {"by": ["status"], "agg": {"total": {"func": "sum", "col": "amount"},
                                                    "n": {"func": "count", "col": "order_id"}}})
check("aggregate", len(r) >= 3 and r["n"].max() > 1, f"{len(r)} groupes, max {int(r['n'].max())} lignes")

# 12 join — inner perd la commande orpheline, left la garde
p = {"right": "customers", "key": "customer_id", "how": "inner", "_right_rows": customers.to_dict("records")}
inner = E._op_join(orders, dict(p))
left = E._op_join(orders, dict(p, how="left"))
check("join", len(inner) < len(left) == len(orders),
      f"inner {len(inner)} / left {len(left)} — la commande orpheline distingue les deux")

# 13 merge
p = {"right": "customers", "key": "customer_id", "_right_rows": customers.to_dict("records")}
r = E._op_merge(orders, dict(p))
check("merge", r.shape[1] > orders.shape[1], f"{orders.shape[1]} -> {r.shape[1]} colonnes")

# 14 union
r = E._op_union(orders, {"right": "orders_extra", "_right_rows": orders_extra.to_dict("records")})
check("union", len(r) == len(orders) + len(orders_extra), f"{len(orders)} + {len(orders_extra)} = {len(r)} lignes")

# 15 pivot
r = E._op_pivot(base, {"index": ["customer_id"], "column": "status", "values": "amount", "aggfunc": "sum"})
check("pivot", r.shape[1] >= 4, f"{r.shape[0]} lignes x {r.shape[1]} colonnes, une par statut")

# 16 unpivot
r = E._op_unpivot(revenue_wide, {"id_vars": ["region"], "var_name": "quarter", "value_name": "revenue"})
check("unpivot", len(r) == len(revenue_wide) * 4, f"{len(revenue_wide)} -> {len(r)} lignes")

# 17 transpose
r = E._op_transpose(revenue_wide, {"index_col": "region"})
check("transpose", r.shape[0] == revenue_wide.shape[1] - 1,
      f"{revenue_wide.shape} -> {r.shape}")

# 18 script
r = E._op_script(base, {"inputs": ["amount"], "outputs": {"flag": "bool"},
                        "code": "flag = amount > 40", "mode": "vectorized"})
check("script", "flag" in r.columns, "colonne flag creee")

# ---------------------------------------------------------------- rapport
ok = sum(1 for _, c, _ in results if c)
for op, cond, detail in results:
    print(f"  {'ok  ' if cond else 'FAIL'}  {op:12} {detail}")
print(f"\n{ok} / {len(results)} operations trouvent matiere dans le jeu canonique")
sys.exit(0 if ok == len(results) else 1)
