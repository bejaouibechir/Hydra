select cast(customer_id as integer) as customer_id, name, country
from {{ source('raw', 'customers') }}
