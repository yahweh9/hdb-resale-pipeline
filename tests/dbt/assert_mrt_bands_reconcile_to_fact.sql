-- Every sale with a known station distance lands in exactly one band. A gap between
-- band edges would drop sales silently; an overlap would count them twice. Either
-- way the band counts stop summing to the fact, and this returns a row.

with banded as (
    select coalesce(sum(sales), 0) as n from {{ ref('mart_mrt_premium_by_band') }}
),

located as (
    select count(*) as n
    from {{ ref('fact_resale_txn') }} x
    join {{ ref('dim_block') }} b using (block_key)
    where b.dist_to_nearest_mrt_km is not null
)

select banded.n as banded_sales, located.n as located_sales
from banded, located
where banded.n != located.n
