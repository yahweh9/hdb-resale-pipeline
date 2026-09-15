/*
    Grain: one row per block with at least one sale in the fair-value window.

    premium_pct: how far the block's sales typically land above (+) or below (-) what the
    hedonic model predicts for their town, MRT band, lease band, storey, flat type and
    month. The verdict is the only column meant to be read as a claim; "not enough sales"
    and "in line" are answers too, not gaps.
*/

select
    f.block_key,
    b.address,
    b.town,
    f.sales,
    round(f.premium_pct, 1) as premium_pct,
    round(f.ci_low_pct, 1)  as ci_low_pct,
    round(f.ci_high_pct, 1) as ci_high_pct,
    f.verdict,
    f.window_start,
    f.window_end
from {{ ref('block_fair_value') }} f
join {{ ref('dim_block') }} b using (block_key)
order by f.premium_pct desc
