# Snowflake → PostgreSQL, without losing a row or breaking a type

One Hydra ETL job that copies `SALES.PUBLIC.ORDERS` from Snowflake to a PostgreSQL table, and keeps every value exact on the way:

| Snowflake | Python value read by Hydra ETL | PostgreSQL column created |
|---|---|---|
| `NUMBER(38,0)` | exact integer (never a float) | `bigint` |
| `NUMBER(12,2)` | exact decimal | `numeric` |
| `TIMESTAMP_TZ` | timestamp with its time zone | `timestamp with time zone` |
| `TIMESTAMP_NTZ` | timestamp without time zone | `timestamp without time zone` |
| `DATE` | date | `date` |
| `BOOLEAN` | boolean | `boolean` |
| `VARIANT`, `OBJECT`, `ARRAY` | JSON value | `jsonb` |

Column names are lowercased (`column_case: lower`), so `ORDER_ID` becomes `order_id` and needs no quotes in PostgreSQL.

The load is an **upsert on `order_id`** (re-running the job updates rows, never duplicates them) and **all or nothing**: if anything fails in the middle of the load, PostgreSQL stays exactly as it was.

```
jobs/orders_to_postgres/
  sources.yaml        # Snowflake, read-only
  destinations.yaml   # PostgreSQL, upsert on order_id, atomic
  pipeline.yaml
workflows/
  migrate.yaml
  thread.yaml
demo/                 # optional: a local Snowflake emulator to try it without an account
```

## 1. Start a PostgreSQL

```bash
docker run --name hydra-pg -e POSTGRES_PASSWORD=hydra -p 5432:5432 -d postgres:16
```

## 2. Install

```bash
pip install "hydra-etl[snowflake,postgres]"
```

## 3. Set the connection variables

Create a `.env` file in this folder (it is ignored by git). Credentials stay out of the YAML files, and the private key stays in its own file: only its path goes here.

```
SNOWFLAKE_ACCOUNT=MYORG-MYACCOUNT
SNOWFLAKE_USER=HYDRA_SVC
SNOWFLAKE_PRIVATE_KEY_FILE=C:/Users/me/.snowflake/rsa_key.p8
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
DEMO_PG_HOST=127.0.0.1
DEMO_PG_PORT=5432
DEMO_PG_USER=postgres
DEMO_PG_PASSWORD=hydra
DEMO_PG_DATABASE=postgres
```

The PostgreSQL variables are named `DEMO_PG_*` on purpose: a `PG_PORT` or `PG_USER` already set on your machine cannot interfere with the example.

`SNOWFLAKE_ACCOUNT` is the account identifier shown in Snowsight (**Account** → **View account details**), or the locator with its region as in the Snowsight address (`xy12345.eu-central-2.aws`).

`HYDRA_SVC` is a Snowflake service user that can only read `SALES`, authenticated with a key pair:

```sql
CREATE ROLE IF NOT EXISTS HYDRA_READER;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE HYDRA_READER;
GRANT USAGE ON DATABASE SALES TO ROLE HYDRA_READER;
GRANT USAGE ON SCHEMA SALES.PUBLIC TO ROLE HYDRA_READER;
GRANT SELECT ON ALL TABLES IN SCHEMA SALES.PUBLIC TO ROLE HYDRA_READER;
CREATE USER IF NOT EXISTS HYDRA_SVC TYPE = SERVICE
  DEFAULT_ROLE = HYDRA_READER DEFAULT_WAREHOUSE = COMPUTE_WH
  RSA_PUBLIC_KEY = '<public key, one line, starting with MIIBIjANBgkqh>';
GRANT ROLE HYDRA_READER TO USER HYDRA_SVC;
```

The key pair comes from OpenSSL (the public key must be in the `BEGIN PUBLIC KEY` format):

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out rsa_key.p8
openssl pkey -in rsa_key.p8 -pubout -out rsa_key.pub
```

## 4. Run

```bash
hdrctl run .
```

The first run creates the `orders` table with the types above and `order_id` as primary key. The next runs update it.

## Try it without a Snowflake account

`demo/` uses [fakesnow](https://github.com/tekumara/fakesnow), an open-source Snowflake emulator that runs locally on DuckDB. Only the `DEMO_PG_*` variables are needed in `.env`, then:

```bash
pip install fakesnow
python demo/fakesnow_data.py create      # 50,000 orders in the emulator
python demo/hdrctl_fakesnow.py run .     # same as hdrctl run ., against the emulator
```

Then see the all-or-nothing load at work:

```bash
python demo/fakesnow_data.py change      # every amount + 1.00 in Snowflake
python demo/fakesnow_data.py break       # plus one order without ORDER_ID
python demo/hdrctl_fakesnow.py run .     # fails at the last batch: order_id cannot be NULL
```

After 50,000 updated rows were sent, the last row is refused, and PostgreSQL still holds the previous amounts: the whole load is undone, not just the failed batch. Repair and run again:

```bash
python demo/fakesnow_data.py repair
python demo/hdrctl_fakesnow.py run .     # all 50,000 orders updated
```

Check from PostgreSQL at each step:

```sql
SELECT count(*), sum(amount), min(order_id) FROM orders;
```

The emulator stores integers up to 64 bits only, while Snowflake's `NUMBER(38,0)` goes up to 38 digits.
