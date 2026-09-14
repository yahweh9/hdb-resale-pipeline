"""Grain: one row per block with a sale in the last 36 months. Premium over the model, and a verdict.

Each sale is compared with its own year's fit; a block is called above or below only with
10+ sales and a 95% interval clear of zero (see valuation.fair_value).
"""

import valuation


def model(dbt, session):
    dbt.config(materialized="table")
    return valuation.fair_value(dbt.ref("hedonic_sales").df())
