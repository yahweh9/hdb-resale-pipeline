-- A verdict is a claim about a block, so it has to meet the published rules: "above" or
-- "below" needs 10+ sales and a 95% interval entirely on that side of zero; "in line"
-- needs 10+ sales and an interval that straddles zero; anything thinner says
-- "not enough sales". Returns every block whose verdict breaks them.

select block_key, sales, ci_low_pct, ci_high_pct, verdict
from {{ ref('block_fair_value') }}
where not (
       (verdict = 'above'            and sales >= 10 and ci_low_pct > 0)
    or (verdict = 'below'            and sales >= 10 and ci_high_pct < 0)
    or (verdict = 'in line'          and sales >= 10 and ci_low_pct <= 0 and ci_high_pct >= 0)
    or (verdict = 'not enough sales' and sales < 10)
)
