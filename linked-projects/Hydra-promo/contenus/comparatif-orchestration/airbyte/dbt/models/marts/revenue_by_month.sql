select to_char(cast(order_date as date), 'YYYY-MM') as month, round(sum(amount)::numeric, 2) as revenue
from {{ ref('stg_orders') }}
group by 1
