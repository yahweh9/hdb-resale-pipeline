/*
    Grain: one row per floor tier (finding 3). Two storey premiums side by side.

    naive: 4-room median price per sqm by tier, against Low floors.
    controlled: each tier's median against Low floors in the SAME town, flat type and
    year, averaged over every such comparison with 15+ sales on both sides of it.

    Neither holds lease constant; the hedonic model does, and puts the top tier far lower
    -- tall blocks are newer. This mart records what the group-by comparisons say.
*/

with sales as (

    select t.town, f.flat_type, d.calendar_year, f.floor_tier, x.price_psm
    from {{ ref('fact_resale_txn') }} x
    join {{ ref('dim_town') }} t using (town_key)
    join {{ ref('dim_flat') }} f using (flat_key)
    join {{ ref('dim_date') }} d using (date_key)

),

naive as (

    select floor_tier, median(price_psm) as psm
    from sales
    where flat_type = '4 ROOM'
    group by floor_tier

),

cells as (

    select town, flat_type, calendar_year, floor_tier, median(price_psm) as psm
    from sales
    group by town, flat_type, calendar_year, floor_tier
    having count(*) >= 15

),

controlled as (

    select c.floor_tier, avg(c.psm / low.psm) as multiplier, count(*) as cells
    from cells c
    join cells low
      on  low.town = c.town
      and low.flat_type = c.flat_type
      and low.calendar_year = c.calendar_year
      and low.floor_tier = 'Low (1-4)'
    group by c.floor_tier

)

select
    case floor_tier
        when 'Low (1-4)'        then 1
        when 'Mid (5-9)'        then 2
        when 'High (10-19)'     then 3
        when 'Ultra-High (20+)' then 4
    end                                                                   as tier_order,
    floor_tier,
    round(naive.psm, 0)                                                   as naive_4room_psm,
    round(100 * (naive.psm / max(naive.psm) filter (where floor_tier = 'Low (1-4)') over () - 1), 1)
                                                                          as naive_premium_pct,
    round(controlled.multiplier, 3)                                       as controlled_multiplier,
    controlled.cells                                                      as comparison_cells
-- Full join: a tier can have controlled comparisons without a 4-room sale, or the
-- reverse. Dropping it from one side would make this mart disagree with dashboard/explore.py.
from naive
full join controlled using (floor_tier)
order by tier_order
