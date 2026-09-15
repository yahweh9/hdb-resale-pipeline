/*
    Grain: one row per month. Two price indices, Jan 2017 = 100.

    naive_index follows the median price per sqm, so it moves whenever the MIX of flats
    sold moves -- a month heavy in central, short-lease sales looks dear for reasons that
    have nothing to do with prices. hedonic_index is the all-years model's month terms:
    the price of the same flat, in the same town, with the same lease band, storey and
    flat type, month to month. The gap between the two lines is the mix effect.

    is_year_end marks the last month present in each year, so a yearly table can take
    one row a year without re-deriving which month that is.
*/

with naive as (

    select
        transaction_month  as month,
        min(calendar_year) as calendar_year,
        count(*)           as sales,
        median(price_psm)  as median_psm
    from {{ ref('hedonic_sales') }}
    group by transaction_month

),

model as (

    select level as month, estimate, std_error
    from {{ ref('hedonic_coefficients') }}
    where term = 'month'

),

base as (

    -- The model's reference month is the earliest month, so both indices share a base.
    select median_psm from naive order by month limit 1

)

select
    naive.month,
    naive.calendar_year,
    naive.sales,
    round(naive.median_psm, 0)                                        as median_price_psm,
    round(100 * naive.median_psm / base.median_psm, 1)                as naive_index,
    round(100 * exp(model.estimate), 1)                               as hedonic_index,
    round(100 * exp(model.estimate - 1.959964 * model.std_error), 1)  as hedonic_ci_low,
    round(100 * exp(model.estimate + 1.959964 * model.std_error), 1)  as hedonic_ci_high,
    naive.month = max(naive.month) over (partition by naive.calendar_year) as is_year_end
from naive
join model using (month)
cross join base
order by naive.month
