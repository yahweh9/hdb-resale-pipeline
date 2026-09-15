/*
    Grain: one row per ring of distance from the CBD (finding 2). The near-station premium
    within each ring, so station proximity is not credited with being central.
*/

with sales as (

    select
        case
            when b.dist_to_cbd_km < 5  then 1
            when b.dist_to_cbd_km < 10 then 2
            when b.dist_to_cbd_km < 15 then 3
            else 4
        end as ring_order,
        b.is_near_mrt,
        x.price_psm
    from {{ ref('fact_resale_txn') }} x
    join {{ ref('dim_block') }} b using (block_key)
    where b.dist_to_cbd_km is not null
      and b.is_near_mrt is not null

),

rings as (

    select
        ring_order,
        count(*) filter (where is_near_mrt)         as near_mrt_sales,
        count(*) filter (where not is_near_mrt)     as not_near_sales,
        median(price_psm) filter (where is_near_mrt)     as near_psm,
        median(price_psm) filter (where not is_near_mrt) as not_near_psm
    from sales
    group by ring_order

)

select
    ring_order,
    case ring_order
        when 1 then 'under 5km'
        when 2 then '5-10km'
        when 3 then '10-15km'
        else '15km+'
    end                                           as cbd_ring,
    near_mrt_sales,
    not_near_sales,
    round(near_psm, 0)                            as near_mrt_psm,
    round(not_near_psm, 0)                        as not_near_psm,
    round(100 * (near_psm / not_near_psm - 1), 1) as premium_pct
from rings
order by ring_order
