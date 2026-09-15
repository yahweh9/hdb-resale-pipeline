/*
    Grain: one row per MRT band and per lease band. The before/after table.

    naive_pct is what a GROUP BY says: each band's median price per sqm against the
    reference band's. model_pct is the all-years hedonic effect for the same band, holding
    town, the other band, storey, flat type and month constant, with its 95% interval.
    The two disagree exactly where FINDINGS.md said a group-by could not be trusted.

    Both columns share the model's reference band, so every row answers the same question.
*/

with sales as (

    select * from {{ ref('hedonic_sales') }}

),

naive as (

    select 'mrt_band' as term, mrt_band as level, mrt_band_order as band_order,
           count(*) as sales, median(price_psm) as median_psm
    from sales
    group by mrt_band, mrt_band_order

    union all

    select 'lease_band', lease_band, lease_band_order, count(*), median(price_psm)
    from sales
    group by lease_band, lease_band_order

),

coefficients as (

    select * from {{ ref('hedonic_coefficients') }}
    where term in ('mrt_band', 'lease_band')

),

reference as (

    select naive.term, naive.median_psm as reference_psm
    from naive
    join coefficients c on c.term = naive.term and c.level = naive.level and c.is_reference

)

select
    naive.term,
    naive.level,
    naive.band_order,
    naive.sales,
    c.is_reference,
    round(100 * (naive.median_psm / reference.reference_psm - 1), 1) as naive_pct,
    round(c.effect_pct, 1)                                          as model_pct,
    round(c.ci_low_pct, 1)                                          as model_ci_low_pct,
    round(c.ci_high_pct, 1)                                         as model_ci_high_pct
from naive
join reference using (term)
join coefficients c on c.term = naive.term and c.level = naive.level
order by naive.term, naive.band_order
