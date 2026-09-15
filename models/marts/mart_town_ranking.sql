/*
    Grain: one row per town. Two rankings: the naive median price per sqm, and the
    hedonic model's town effect -- the town's premium over the average town once MRT band,
    lease band, storey, flat type and month are held constant. Where they disagree, the
    naive ranking was ranking the housing stock, not the town.
*/

with naive as (

    select
        t.town,
        t.region,
        t.is_mature_estate,
        count(*)            as sales,
        median(x.price_psm) as psm
    from {{ ref('fact_resale_txn') }} x
    join {{ ref('dim_town') }} t using (town_key)
    group by t.town, t.region, t.is_mature_estate

),

model as (

    select level as town, effect_pct, ci_low_pct, ci_high_pct
    from {{ ref('hedonic_coefficients') }}
    where term = 'town'

)

select
    naive.town,
    naive.region,
    naive.is_mature_estate,
    naive.sales,
    round(naive.psm, 0)          as median_price_psm,
    round(model.effect_pct, 1)   as model_effect_pct,
    round(model.ci_low_pct, 1)   as model_ci_low_pct,
    round(model.ci_high_pct, 1)  as model_ci_high_pct
from naive
left join model using (town)
order by naive.psm desc
