/*
    Grain: one row per calendar year, plus "All years". How well the model prices blocks
    it never saw, beside a baseline that guesses the town x flat type median.

    Median absolute error, not mean: a handful of maisonettes mispriced by 40% would
    dominate a mean and say nothing about a typical flat. Within-10% is the share of
    sales a buyer would call "about right".
*/

select
    scope,
    test_sales,
    round(model_median_error_pct, 1)    as model_median_error_pct,
    round(baseline_median_error_pct, 1) as baseline_median_error_pct,
    round(model_within_10pct, 1)        as model_within_10pct,
    round(baseline_within_10pct, 1)     as baseline_within_10pct
from {{ ref('hedonic_validation') }}
order by scope = 'All years', scope
