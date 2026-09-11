{{ config(materialized = 'table') }}

/*
    Silver: one row per resale transaction, typed and normalised.

    There is deliberately no deduplication here, and the reason is worth stating
    because an earlier version of this model had one.

    _id is not a transaction identifier. It is data.gov.sg's row offset in their
    datastore, and it is reassigned when they republish. Measured across the current
    240,074 rows, 579 _id values appear twice -- and every one of those pairs differs
    in block, street and floor area. They are different sales that happen to share a
    row number. Deduplicating on _id deleted 579 real transactions, and the unique
    test passed precisely because the dedup had removed its own evidence.

    (month, _id) is unique: zero collisions across all 240,074 rows. Within a month
    partition the rows come from a single fetch, where the API's own numbering holds;
    across partitions a repeated number means nothing. So that pair is the key, and
    it is enforced by a test rather than silently applied by a qualify -- if the
    source ever does repeat a row, the build should go red rather than quietly drop
    it. A business key was measured too and is worse: it collapses 403 genuinely
    distinct sales, since identical units in one block do sell in the same month at
    the same price.
*/

with bronze as (

    select * from {{ source('bronze', 'hdb_resale') }}

),

typed as (

    select
        cast(_id as bigint)                                    as source_txn_id,
        month                                                  as year_month,
        cast(month || '-01' as date)                           as transaction_month,

        upper(trim(town))                                      as town,

        -- HDB writes this hyphenated in the 2017-onwards file and unhyphenated in
        -- the pre-2017 one. Only 'MULTI-GENERATION' appears in the data today, so
        -- this conforms a value rather than merging two. Normalising now means a
        -- backfill of the older file lands on the same dim_flat row instead of
        -- forking it, and it is what accepted_values on dim_flat.flat_type asserts.
        replace(upper(trim(flat_type)), '-', ' ')              as flat_type,

        -- flat_model arrives in mixed case ('Model A', 'New Generation'). No two
        -- spellings differ only by case in the current data -- checked, not assumed
        -- -- so this changes presentation, not grain. Upper-casing it anyway keeps
        -- every string column on one rule, so nothing downstream has to remember
        -- which ones were normalised and which were not.
        upper(trim(flat_model))                                as flat_model,

        upper(trim(block))                                     as block,
        upper(trim(street_name))                               as street_name,
        upper(trim(block)) || ' ' || upper(trim(street_name))  as address,

        trim(storey_range)                                     as storey_range,
        try_cast(regexp_extract(storey_range, '(\d+)', 1) as integer)      as storey_lower,
        try_cast(regexp_extract(storey_range, '(\d+)\D*$', 1) as integer)  as storey_upper,

        try_cast(floor_area_sqm as decimal(8, 2))              as floor_area_sqm,
        try_cast(resale_price as decimal(12, 2))               as resale_price,
        try_cast(lease_commence_date as integer)               as lease_commence_year,

        -- remaining_lease changed format mid-history: older rows carry a bare number
        -- of years ('70'), newer ones carry '61 years 04 months'. Both formats live
        -- in the same column, so both are parsed down to one integer of months.
        case
            when remaining_lease is null or trim(remaining_lease) = '' then null
            when regexp_matches(trim(remaining_lease), '^[0-9]+(\.[0-9]+)?$')
                then cast(round(cast(trim(remaining_lease) as double) * 12) as integer)
            when regexp_matches(lower(remaining_lease), 'year')
                then coalesce(try_cast(regexp_extract(lower(remaining_lease), '(\d+)\s*year', 1) as integer), 0) * 12
                   + coalesce(try_cast(regexp_extract(lower(remaining_lease), '(\d+)\s*month', 1) as integer), 0)
            else null
        end                                                    as remaining_lease_months,

        _ingested_at

    from bronze

)

select
    *,
    (storey_lower + storey_upper) / 2.0                        as storey_median,
    round(resale_price / nullif(floor_area_sqm, 0), 2)         as price_psm
from typed
