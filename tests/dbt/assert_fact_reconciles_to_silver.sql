-- The fact is incremental and the silver model is not, so the two are built by
-- different code paths. They must still agree on how many transactions exist. A
-- mismatch means the incremental filter dropped a month or double-counted one --
-- the failure mode that incremental models are actually prone to, and the one that
-- a row-level uniqueness test cannot see.

with counts as (
    select
        (select count(*) from {{ ref('fact_resale_txn') }})   as fact_rows,
        (select count(*) from {{ ref('silver_hdb_resale') }}) as silver_rows
)

select *
from counts
where fact_rows != silver_rows
