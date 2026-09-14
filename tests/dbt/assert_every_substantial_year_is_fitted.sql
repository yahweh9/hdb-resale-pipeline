-- fit_by_year skips a year the data cannot identify, which is right for the CI fixture's
-- ~80-sale years and wrong for any real one. 5,000 sales is far above the ~50 terms a
-- single year needs and far below the ~18,000 in the thinnest real year (partial 2026),
-- so a real year that goes missing fails the build instead of vanishing from the charts.

with years as (
    select calendar_year, count(*) as sales
    from {{ ref('hedonic_sales') }}
    group by calendar_year
),

fitted as (
    select distinct calendar_year from {{ ref('hedonic_coefficients_by_year') }}
)

select years.calendar_year, years.sales
from years
left join fitted using (calendar_year)
where years.sales >= 5000
  and fitted.calendar_year is null
