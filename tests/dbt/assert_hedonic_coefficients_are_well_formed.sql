-- The coefficient table means what its readers will assume it means. Returns a row for
-- each way it could quietly not:
--   * a term other than town without exactly one reference level, or a reference with
--     a non-zero effect -- every effect in that term would be relative to nothing;
--   * town effects that do not average to zero -- "relative to the average town" false;
--   * a term whose level counts do not add up to the model's input -- sales dropped
--     or double counted between the SQL input and the Python fit.

with coefficients as (
    select * from {{ ref('hedonic_coefficients') }}
),

input as (
    select count(*) as n from {{ ref('hedonic_sales') }}
),

by_term as (
    select
        term,
        count(*) filter (where is_reference)                        as reference_levels,
        coalesce(max(abs(estimate)) filter (where is_reference), 0) as reference_estimate,
        avg(estimate)                                               as mean_estimate,
        sum(sales)                                                  as sales
    from coefficients
    group by term
)

select term, 'reference levels' as problem
from by_term
where (term = 'town' and reference_levels != 0)
   or (term != 'town' and (reference_levels != 1 or reference_estimate != 0))

union all

select term, 'towns do not average to zero'
from by_term
where term = 'town' and abs(mean_estimate) > 1e-9

union all

select term, 'sales do not reconcile to the input'
from by_term, input
where by_term.sales != input.n
