{{
    config(
        materialized = 'incremental',
        unique_key = 'date_key',
        incremental_strategy = 'delete+insert',
        on_schema_change = 'append_new_columns'
    )
}}

/*
    Grain: one resale transaction.

    The incremental unit is a MONTH, not a row. unique_key is date_key, so
    delete+insert drops every fact row for each month in the incoming batch and
    re-inserts it -- deliberately mirroring bronze, where a month is also replaced
    wholesale. Keying on the transaction surrogate instead would leave behind any row
    data.gov.sg later withdrew from an open month: the fact would go on serving a
    transaction the source no longer reports, and nothing would ever notice.

    Dimension keys are hashed from natural keys on both sides rather than joined. The
    hash is deterministic, so the fact computes town_key without touching dim_town --
    no fan-out risk from a dimension that turns out not to be unique -- and the
    relationships tests still prove each dimension holds every key the fact emits.
*/

with silver as (

    select * from {{ ref('silver_hdb_resale') }}

    {% if is_incremental() %}
    -- Re-open the newest month already loaded rather than starting after it, for the
    -- same reason the ingest re-fetches it: transactions keep registering against a
    -- month for weeks after that month has begun.
    where transaction_month >= (
        select coalesce(max(transaction_month), date '1900-01-01') from {{ this }}
    )
    {% endif %}

)

select
    {{ dbt_utils.generate_surrogate_key(['year_month', 'source_txn_id']) }}             as resale_txn_key,

    cast(strftime(transaction_month, '%Y%m') as integer)                                as date_key,
    {{ dbt_utils.generate_surrogate_key(['town']) }}                                    as town_key,
    {{ dbt_utils.generate_surrogate_key(['flat_type', 'flat_model', 'storey_range']) }} as flat_key,
    {{ dbt_utils.generate_surrogate_key(['address']) }}                                 as block_key,

    -- Degenerate dimension: data.gov.sg's own row offset. Only meaningful paired with
    -- the month, which is why the surrogate key hashes both -- see silver for why.
    source_txn_id,
    transaction_month,

    resale_price,
    floor_area_sqm,
    price_psm,
    remaining_lease_months,
    lease_commence_year,

    _ingested_at

from silver
