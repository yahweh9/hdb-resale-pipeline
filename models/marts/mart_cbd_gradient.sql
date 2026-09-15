/*
    Grain: one row per whole kilometre from the CBD (finding 1).

    Per kilometre rather than wide bands, because the shape is the finding: a steep decay
    to about 5km, then a plateau that oscillates. A ring with fewer than 200 sales is left
    out -- its median is a handful of flats, not a price level.
*/

select
    floor(b.dist_to_cbd_km)::integer as km_from_cbd,
    count(*)                         as sales,
    round(median(x.price_psm), 0)    as median_price_psm
from {{ ref('fact_resale_txn') }} x
join {{ ref('dim_block') }} b using (block_key)
where b.dist_to_cbd_km is not null
group by 1
having count(*) >= 200
order by 1
