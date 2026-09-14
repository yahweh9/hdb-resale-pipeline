/*
    Grain: one row per MRT distance band, across every sale in the warehouse.

    Descriptive, not controlled: this is the naive premium, the "before" that the
    hedonic model's within-town estimate is set against. It makes no claim that the
    station causes the difference -- FINDINGS.md finding 2 explains why it cannot.

    The premium is quoted against the farthest band rather than the nearest, so every
    number reads as "what being closer is worth" and the reference band is the one
    with no station to speak of.
*/

with sales as (

    select
        {{ mrt_band_order('b.dist_to_nearest_mrt_km') }} as band_order,
        {{ mrt_band_label('b.dist_to_nearest_mrt_km') }} as mrt_band,
        x.price_psm
    from {{ ref('fact_resale_txn') }} x
    join {{ ref('dim_block') }} b using (block_key)
    -- An ungeocoded block has no distance and so no band. The coverage test in
    -- tests/dbt keeps that set empty; the reconcile test proves nothing else is lost.
    where b.dist_to_nearest_mrt_km is not null

),

banded as (

    select
        band_order,
        mrt_band,
        count(*)          as sales,
        median(price_psm) as median_price_psm
    from sales
    group by band_order, mrt_band

)

select
    band_order,
    mrt_band,
    sales,
    round(median_price_psm, 0) as median_price_psm,
    round(
        100 * (median_price_psm / max(case when band_order = 4 then median_price_psm end) over () - 1),
        1
    ) as premium_vs_farthest_pct
from banded
order by band_order
