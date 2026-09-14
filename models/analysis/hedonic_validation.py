"""Grain: one row per calendar year, plus one for all years. Out-of-sample accuracy.

Each year's model is fitted on 80% of blocks and prices the other 20%, next to a
town x flat type median baseline. assert_model_beats_baseline turns the result into a
build check: a model that stops beating the lazy guess fails the build.
"""

import valuation


def model(dbt, session):
    dbt.config(materialized="table")
    return valuation.validate(dbt.ref("hedonic_sales").df())
