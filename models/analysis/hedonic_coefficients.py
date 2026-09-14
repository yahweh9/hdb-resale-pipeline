"""Grain: one row per level of every term in the all-years hedonic fit.

A dbt Python model so the fit sits in the same dependency graph as everything it reads
and everything that will read it: `dbt build` refreshes gold, refits the model, then
runs the tests on its output, in that order, every time.

The fitting itself lives in hedonic.py at the repository root (on the path via
module_paths in profiles.yml). This file only moves data in and out, so the maths is
tested by pytest against planted answers rather than only here against real data.
"""

import hedonic


def model(dbt, session):
    dbt.config(materialized="table")
    sales = dbt.ref("hedonic_sales").df()
    return hedonic.fit_hedonic(sales)
