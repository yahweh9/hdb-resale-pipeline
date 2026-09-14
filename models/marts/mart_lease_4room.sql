/*
    Grain: one row per lease band, 4-room flats only (finding 4).

    The naive lease table and the confound behind it: the shortest leases look dear
    because they sit close to the CBD, in mature estates. The same bands as the hedonic
    model, so the naive table and the model's before/after table in finding 4 line up.
*/

select
    {{ lease_band_order('x.remaining_lease_months') }} as band_order,
    {{ lease_band('x.remaining_lease_months') }}       as lease_band,
    count(*)                                                  as sales,
    round(median(x.price_psm), 0)                             as median_price_psm,
    round(median(b.dist_to_cbd_km), 1)                        as median_km_to_cbd,
    round(100 * avg(t.is_mature_estate::integer), 0)          as pct_mature
from {{ ref('fact_resale_txn') }} x
join {{ ref('dim_flat') }}  f using (flat_key)
join {{ ref('dim_town') }}  t using (town_key)
join {{ ref('dim_block') }} b using (block_key)
where f.flat_type = '4 ROOM'
  and x.remaining_lease_months is not null
group by 1, 2
order by band_order
