{{ config(location=var('out_dir', '../output') ~ '/revenue_by_month.csv') }}
select strftime(cast(order_date as date), '%Y-%m') as month, round(sum(amount), 2) as revenue
from {{ ref('stg_orders') }}
group by 1
order by 1
