-- A block with no coordinates keeps its dim_block row and its transactions, but drops
-- out of every spatial answer silently. That is the failure this guards: not a crash,
-- just a map that quietly omits part of the island.
--
-- Threshold rather than not_null, because OneMap genuinely cannot resolve a handful of
-- demolished or renamed blocks and failing the build over those would train everyone
-- to ignore the test. Tighten it if coverage improves.

with coverage as (
    select
        count(*)                                          as blocks,
        count(*) filter (where latitude is null)          as ungeocoded
    from {{ ref('dim_block') }}
)

select *
from coverage
where ungeocoded > blocks * 0.02
