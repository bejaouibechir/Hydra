"""Compare les deux sorties à la référence calculée par DuckDB sur le CSV."""
import json, sys
import duckdb, pandas as pd
data, out = sys.argv[1], sys.argv[2]
con = duckdb.connect()
ref_c = con.sql(f"""select c.country, round(sum(cast(o.amount as double)),2) as revenue, count(*) as orders
  from read_csv('{data}/orders.csv', all_varchar=true) o join read_csv('{data}/customers.csv', all_varchar=true) c using (customer_id)
  where o.status='paid' group by 1 order by 1""").df()
ref_m = con.sql(f"""select substr(order_date,1,7) as "month", round(sum(cast(amount as double)),2) as revenue
  from read_csv('{data}/orders.csv', all_varchar=true) where status='paid' group by 1 order by 1""").df()
def same(a, b):
    try:
        x = pd.read_csv(a).sort_values(list(pd.read_csv(a).columns[:1]))
    except Exception:
        return False
    b = b.copy()
    if len(x) != len(b):
        return False
    return all((abs(x["revenue"].astype(float).values - b["revenue"].astype(float).values) < 0.05 * max(1, 1)) )
print(json.dumps({"country_ok": bool(same(f"{out}/revenue_by_country.csv", ref_c)),
                  "month_ok": bool(same(f"{out}/revenue_by_month.csv", ref_m))}))
