select
    cast(order_id as integer)         as order_id,
    cast(customer_id as integer)      as customer_id,
    order_date,
    cast(amount as double precision)  as amount,
    status
from {{ source('raw', 'orders') }}
where status = 'paid'
