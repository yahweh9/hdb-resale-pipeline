"""Grain: one row per level of every term, per calendar year, from a separate fit each year.

The all-years fit in hedonic_coefficients assumes every effect held still for a decade.
This one lets them move, so the edition can show whether, say, the station premium grew
through the 2021 boom. A year too thin to identify is skipped by hedonic.fit_by_year;
assert_every_substantial_year_is_fitted fails the build if a year that should have
fitted did not.
"""

import hedonic


def model(dbt, session):
    dbt.config(materialized="table")
    sales = dbt.ref("hedonic_sales").df()
    return hedonic.fit_by_year(sales)
