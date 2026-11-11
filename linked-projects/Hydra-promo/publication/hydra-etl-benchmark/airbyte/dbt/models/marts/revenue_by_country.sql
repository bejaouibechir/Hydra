select c.country, round(sum(o.amount)::numeric, 2) as revenue, count(o.order_id) as orders
from {{ ref('stg_orders') }} o
join {{ ref('stg_customers') }} c using (customer_id)
group by c.country
