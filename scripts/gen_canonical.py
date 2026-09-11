# -*- coding: utf-8 -*-
"""
Jeu de donnees canonique du site — customers / products / orders / orders_extra / revenue_wide.

Deterministe, ecrit a la main. Concu pour que **chacune des 18 operations** du DSL ait
quelque chose de non trivial a montrer :

  fill_null     -> valeurs manquantes dans city, amount, category
  deduplicate   -> deux lignes strictement dupliquees dans orders
  trim          -> espaces de bord dans customers.name
  clean         -> espaces multiples et casses melangees dans customers.name
  cast          -> quantity, amount, unit_price, dates stockes en texte
  join / merge  -> customer_id commun, plus une commande orpheline (inner != left)
  union         -> orders_extra partage le schema de orders
  aggregate     -> 3 pays, 3 categories, plusieurs lignes par groupe
  pivot         -> orders : index customer_id, colonne status, valeurs amount
  unpivot       -> revenue_wide : 4 colonnes de valeurs
  transpose     -> revenue_wide tient en 4 lignes

Sortie : CSV + JSON dans les deux emplacements (moteur et site).
Usage   : python scripts/gen_canonical.py
"""
from __future__ import annotations

import csv
import json
import os

# ---------------------------------------------------------------- donnees

CUSTOMERS = [
    # customer_id, name (sale a dessein), city, country, signup_date, segment
    ("C001", "  ALICE martin ",     "Paris",     "FR", "2024-01-15", "pro"),
    ("C002", "bob  DUPONT",         "Lyon",      "FR", "2024-02-03", "particulier"),
    ("C003", " Carla  Ruiz",        "Madrid",    "ES", "2024-02-28", "pro"),
    ("C004", "DIETER  schmidt ",    None,        "DE", "2024-03-11", "pro"),
    ("C005", "elena  Gomez ",       "Barcelona", "ES", "2024-04-02", "particulier"),
    ("C006", " Farid Benali",       "Marseille", "FR", "2024-05-19", "particulier"),
    ("C007", "GRETA  mueller",      "Berlin",    "DE", "2024-06-07", "pro"),
    ("C008", "hugo  Lefevre  ",     "Nantes",    "FR", "2024-07-23", None),
]

PRODUCTS = [
    # product_id, product_name, category, unit_price (texte)
    ("P01", "Carnet A5",        "books", "4.50"),
    ("P02", "Stylo plume",      "tools", "24.00"),
    ("P03", "Atlas illustre",   "books", "39.90"),
    ("P04", "Cube en bois",     "toys",  "12.00"),
    ("P05", "Regle metal",      "tools", "7.25"),
    ("P06", "Guide du papier",  None,    "18.00"),
]

# order_id, customer_id, product_id, quantity, amount, status, order_date
ORDERS = [
    ("O1001", "C001", "P01", "3",  "13.50",  "paid",     "2025-01-04"),
    ("O1002", "C001", "P03", "1",  "39.90",  "paid",     "2025-01-11"),
    ("O1003", "C002", "P02", "2",  "48.00",  "pending",  "2025-01-12"),
    ("O1004", "C003", "P01", "10", "45.00",  "paid",     "2025-01-15"),
    ("O1005", "C003", "P05", "4",  "29.00",  "refunded", "2025-01-19"),
    ("O1006", "C004", "P04", "1",  "12.00",  "paid",     "2025-01-22"),
    ("O1007", "C004", "P02", "1",  None,     "pending",  "2025-01-25"),
    ("O1008", "C005", "P06", "2",  "36.00",  "paid",     "2025-02-01"),
    ("O1009", "C005", "P01", "6",  "27.00",  "paid",     "2025-02-03"),
    ("O1010", "C006", "P03", "1",  "39.90",  "refunded", "2025-02-08"),
    ("O1011", "C006", "P05", "8",  "58.00",  "paid",     "2025-02-14"),
    ("O1012", "C007", "P02", "3",  "72.00",  "paid",     "2025-02-17"),
    ("O1013", "C007", "P04", "2",  "24.00",  "pending",  "2025-02-21"),
    ("O1014", "C008", "P01", "1",  "4.50",   "paid",     "2025-02-25"),
    ("O1015", "C008", "P06", "1",  None,     "pending",  "2025-03-02"),
    ("O1016", "C001", "P05", "2",  "14.50",  "paid",     "2025-03-05"),
    ("O1017", "C002", "P04", "5",  "60.00",  "paid",     "2025-03-09"),
    ("O1018", "C003", "P02", "1",  "24.00",  "paid",     "2025-03-13"),
    ("O1019", "C005", "P03", "2",  "79.80",  "paid",     "2025-03-16"),
    ("O1020", "C007", "P01", "12", "54.00",  "paid",     "2025-03-20"),
    ("O1021", "C099", "P01", "1",  "4.50",   "paid",     "2025-03-24"),  # client orphelin
    ("O1022", "C002", "P06", "3",  "54.00",  "refunded", "2025-03-27"),
    ("O1023", "C004", "P05", "2",  "14.50",  "paid",     "2025-04-02"),
    ("O1024", "C006", "P02", "1",  "24.00",  "pending",  "2025-04-06"),
    ("O1025", "C008", "P03", "1",  "39.90",  "paid",     "2025-04-10"),
    ("O1026", "C001", "P04", "4",  "48.00",  "paid",     "2025-04-14"),
    ("O1027", "C003", "P06", "1",  "18.00",  "paid",     "2025-04-18"),
    ("O1028", "C007", "P05", "3",  "21.75",  "paid",     "2025-04-22"),
    # deux doublons stricts de O1014 — matiere pour deduplicate
    ("O1014", "C008", "P01", "1",  "4.50",   "paid",     "2025-02-25"),
    ("O1014", "C008", "P01", "1",  "4.50",   "paid",     "2025-02-25"),
]

ORDERS_EXTRA = [
    ("O2001", "C002", "P01", "2",  "9.00",   "paid",     "2025-05-04"),
    ("O2002", "C005", "P02", "1",  "24.00",  "paid",     "2025-05-08"),
    ("O2003", "C007", "P03", "1",  "39.90",  "pending",  "2025-05-12"),
    ("O2004", "C001", "P05", "5",  "36.25",  "paid",     "2025-05-15"),
]

REVENUE_WIDE = [
    ("FR", "1420.00", "1685.50", "1290.00", "1810.75"),
    ("ES", "980.40",  "1105.00", "1240.60", "1002.30"),
    ("DE", "760.00",  "845.20",  "910.00",  "1120.40"),
    ("IT", "512.00",  "498.75",  "603.10",  "655.00"),
    ("BE", "331.20",  "402.90",  "377.45",  "458.00"),
]

TABLES = {
    "customers":    (["customer_id", "name", "city", "country", "signup_date", "segment"], CUSTOMERS),
    "products":     (["product_id", "product_name", "category", "unit_price"], PRODUCTS),
    "orders":       (["order_id", "customer_id", "product_id", "quantity", "amount", "status", "order_date"], ORDERS),
    "orders_extra": (["order_id", "customer_id", "product_id", "quantity", "amount", "status", "order_date"], ORDERS_EXTRA),
    "revenue_wide": (["region", "q1", "q2", "q3", "q4"], REVENUE_WIDE),
}

# ---------------------------------------------------------------- ecriture

def rows_as_dicts(cols, rows):
    return [dict(zip(cols, r)) for r in rows]


def write_all(dest_dirs):
    written = []
    for d in dest_dirs:
        os.makedirs(d, exist_ok=True)
        for name, (cols, rows) in TABLES.items():
            p_csv = os.path.join(d, f"{name}.csv")
            with open(p_csv, "w", encoding="utf-8", newline="\n") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(cols)
                for r in rows:
                    w.writerow(["" if v is None else v for v in r])
            written.append(p_csv)

            p_json = os.path.join(d, f"{name}.json")
            with open(p_json, "w", encoding="utf-8", newline="\n") as f:
                json.dump(rows_as_dicts(cols, rows), f, ensure_ascii=False, indent=2)
                f.write("\n")
            written.append(p_json)
    return written


if __name__ == "__main__":
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    targets = [
        os.path.join(here, "data", "canonical"),
        os.path.join(os.path.dirname(here), "hydra-site", "public", "data"),
    ]
    for p in write_all([t for t in targets if os.path.isdir(os.path.dirname(t))]):
        print("ecrit", p)
    for name, (cols, rows) in TABLES.items():
        print(f"{name:14} {len(rows):3} lignes x {len(cols)} colonnes")
