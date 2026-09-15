/*
    Grain: one row per region (finding 6). Share of each region's sales that are 5-room,
    Executive or Multi-Generation in 2017, at the 2021 boom, and in the latest year.

    2021 is fixed on purpose: it is the peak-volume year the hypothesis was framed around.
    The latest year moves with each edition.
*/

with shares as (

    select
        t.region,
        d.calendar_year,
        100 * avg((f.flat_type in ('5 ROOM', 'EXECUTIVE', 'MULTI GENERATION'))::integer) as share
    from {{ ref('fact_resale_txn') }} x
    join {{ ref('dim_date') }} d using (date_key)
    join {{ ref('dim_town') }} t using (town_key)
    join {{ ref('dim_flat') }} f using (flat_key)
    group by t.region, d.calendar_year

),

latest as (

    select max(calendar_year) as year from shares

)

select
    shares.region,
    latest.year                                                                    as latest_year,
    round(max(share) filter (where calendar_year = 2017), 1)                       as share_2017,
    round(max(share) filter (where calendar_year = 2021), 1)                       as share_2021,
    round(max(share) filter (where calendar_year = latest.year), 1)                as share_latest,
    round(max(share) filter (where calendar_year = latest.year), 1)
        - round(max(share) filter (where calendar_year = 2017), 1)                 as change_pts
from shares
cross join latest
group by shares.region, latest.year
order by shares.region
