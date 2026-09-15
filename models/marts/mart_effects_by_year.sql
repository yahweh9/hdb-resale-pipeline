/*
    Grain: one row per calendar year, term and level, for the three reported effects:
    town, MRT band and lease band. Storey, flat type and month are held constant in each
    year's fit but are controls, not findings, so they are not published.

    Each year is its own fit (hedonic_coefficients_by_year), so a band's effect in 2017
    and in 2025 are each measured against that year's own reference band.
*/

with orders as (

    select distinct 'mrt_band' as term, mrt_band as level, mrt_band_order as band_order
    from {{ ref('hedonic_sales') }}

    union all

    select distinct 'lease_band', lease_band, lease_band_order
    from {{ ref('hedonic_sales') }}

)

select
    c.calendar_year,
    c.term,
    c.level,
    orders.band_order,
    c.sales,
    c.is_reference,
    round(c.effect_pct, 1)  as effect_pct,
    round(c.ci_low_pct, 1)  as ci_low_pct,
    round(c.ci_high_pct, 1) as ci_high_pct
from {{ ref('hedonic_coefficients_by_year') }} c
left join orders on orders.term = c.term and orders.level = c.level
where c.term in ('town', 'mrt_band', 'lease_band')
order by c.calendar_year, c.term, orders.band_order, c.level
