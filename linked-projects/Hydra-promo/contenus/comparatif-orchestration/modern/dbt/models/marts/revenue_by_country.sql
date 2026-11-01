{{ config(location=var('out_dir', '../output') ~ '/revenue_by_country.csv') }}
select c.country, round(sum(o.amount), 2) as revenue, count(o.order_id) as orders
from {{ ref('stg_orders') }} o
join {{ ref('stg_customers') }} c using (customer_id)
group by c.country
order by c.country
