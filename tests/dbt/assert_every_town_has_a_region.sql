-- dim_town maps every town to a planning region with a hardcoded CASE. A hardcoded
-- list rots: HDB launched Tengah in 2023 and its first resales are only now
-- reaching the dataset. This fails the build the day a town appears that the CASE
-- does not know about, instead of bucketing it into 'Unclassified' where a regional
-- chart would silently omit it.

select town
from {{ ref('dim_town') }}
where region = 'Unclassified'
