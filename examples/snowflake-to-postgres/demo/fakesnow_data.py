"""Create (or change) the demo ORDERS table in a local Snowflake emulator (fakesnow).

    python demo/fakesnow_data.py create       # 50,000 orders
    python demo/fakesnow_data.py change       # every amount + 1.00
    python demo/fakesnow_data.py break        # add one order without ORDER_ID
    python demo/fakesnow_data.py repair       # remove it
"""
import sys
from pathlib import Path

import fakesnow

DB = Path(__file__).resolve().parent / "fakesnow-db"
DB.mkdir(exist_ok=True)

SQL = {
    "create": ["""create or replace table ORDERS (
        ORDER_ID number(38,0), CUSTOMER_ID number(38,0), AMOUNT number(12,2), CURRENCY varchar,
        ORDERED_AT timestamp_tz, SHIPPED_ON date, LOADED_AT timestamp_ntz, IS_GIFT boolean,
        DETAILS variant)""",
               """insert into ORDERS select 9007199254740993 + seq8(), 1000 + mod(seq8(), 500),
        round(uniform(100, 100000, random(1)) / 100, 2), 'EUR',
        '2026-10-01 09:00:00+02'::timestamp_tz, '2026-10-03'::date,
        '2026-10-05 01:00:00'::timestamp_ntz, mod(seq8(), 7) = 0,
        parse_json('{"items": [{"sku": "A1", "qty": 2}], "channel": "web"}')
        from table(generator(rowcount => 50000))"""],
    "change": ["update ORDERS set AMOUNT = AMOUNT + 1"],
    "break": ["insert into ORDERS (ORDER_ID, CUSTOMER_ID, AMOUNT, CURRENCY) values (NULL, 1, 10.00, 'EUR')"],
    "repair": ["delete from ORDERS where ORDER_ID is null"],
}

with fakesnow.patch(db_path=str(DB)):
    import snowflake.connector

    conn = snowflake.connector.connect(account="demo", user="demo", password="demo",
                                       database="SALES", schema="PUBLIC")
    cur = conn.cursor()
    for sql in SQL[sys.argv[1] if len(sys.argv) > 1 else "create"]:
        cur.execute(sql)
    cur.execute("select count(*), count(ORDER_ID), sum(AMOUNT)::number(18,2) from ORDERS")
    rows, keyed, total = cur.fetchone()
    print(f"Snowflake ORDERS: {rows} rows ({rows - keyed} without ORDER_ID), total amount {total}")
