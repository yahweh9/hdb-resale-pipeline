-- The quality gate. On blocks it never saw, the model must price a typical sale more
-- closely than a guess of the town x flat type median. If a change to the model, the
-- bands or the data stops that being true, the model is no longer earning its place in
-- the edition and the build says so.
--
-- Only scopes with 1,000+ test sales are judged: the CI fixture's handful of test sales
-- measures noise, while the thinnest real year (partial 2026) has about 3,500.

select scope, test_sales, model_median_error_pct, baseline_median_error_pct
from {{ ref('hedonic_validation') }}
where test_sales >= 1000
  and model_median_error_pct >= baseline_median_error_pct
