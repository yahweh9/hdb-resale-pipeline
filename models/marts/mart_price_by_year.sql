/*
    Grain: one row per calendar year (finding 5). Median price per sqm, and the gap
    between mature and non-mature estates. The gap is a ratio, so it partly controls for
    the market-wide rise: whatever lifted prices lifted both sides.
*/

with yearly as (

    select
        d.calendar_year,
        count(*)                                                   as sales,
        median(x.price_psm)                                        as psm,
        median(x.price_psm) filter (where t.is_mature_estate)      as mature_psm,
        median(x.price_psm) filter (where not t.is_mature_estate)  as non_mature_psm
    from {{ ref('fact_resale_txn') }} x
    join {{ ref('dim_date') }} d using (date_key)
    join {{ ref('dim_town') }} t using (town_key)
    group by d.calendar_year

)

select
    calendar_year,
    sales,
    round(psm, 0)                                     as median_price_psm,
    round(mature_psm, 0)                              as mature_psm,
    round(non_mature_psm, 0)                          as non_mature_psm,
    round(100 * (mature_psm / non_mature_psm - 1), 1) as maturity_gap_pct
from yearly
order by calendar_year
