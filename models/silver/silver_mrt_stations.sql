{{ config(materialized = 'table') }}

/*
    Grain: one row per operational MRT/LRT station.

    Reads the unfiltered Wikidata response (353 rows, 233 stations) and does all the
    narrowing here. It used to happen in ingest/mrt_stations.py, which meant the exclusion
    rules were invisible to the warehouse, untested, and could only be re-evaluated by
    re-querying Wikidata. The Python side now fetches and archives; deciding what the
    response MEANS is this layer's job.

    Three exclusions, all of which change over time and so belong in a model that
    rebuilds rather than in an archive that does not:

      * No opening date. Every such station is Jurong Region Line, Sungei Bedok or
        Teck Lee -- built or planned, never opened. Listed explicitly so the
        assumption stays falsifiable.
      * Opening date in the future. Wikidata carries the Jurong Region and Cross
        Island lines in full; including them computes distances to stations that do
        not exist yet. This one self-corrects: the day a line opens, the next build
        picks it up with no re-fetch.
      * No coordinates. Nothing spatial can be done with them.

    The Singapore bounding-box check that used to raise in Python is now the
    accepted_range test in _spatial_models.yml -- same assertion, but it reports as a
    test failure alongside everything else instead of a traceback.
*/

with raw as (

    select * from {{ source('spatial', 'mrt_stations') }}

),

parsed as (

    select
        mrt_name,
        station_code,
        line,
        cast(try_cast(opening_date as timestamp) as date) as opening_date,

        -- WKT is 'Point(longitude latitude)'. Longitude comes FIRST, which is the
        -- easiest thing in this file to get backwards.
        try_cast(regexp_extract(coordinates, 'Point\(([-0-9.]+) ([-0-9.]+)\)', 1) as double) as longitude,
        try_cast(regexp_extract(coordinates, 'Point\(([-0-9.]+) ([-0-9.]+)\)', 2) as double) as latitude

    from raw

),

collapsed as (

    -- Interchanges fan out across both lines and both codes, so a station arrives as
    -- several rows. Collapse to one, keeping every code and line pipe-separated.
    select
        mrt_name as station_name,
        array_to_string(
            list_sort(list_distinct(array_agg(station_code) filter (where station_code is not null))), '|'
        ) as station_codes,
        array_to_string(
            list_sort(list_distinct(array_agg(line) filter (where line is not null))), '|'
        ) as lines,
        min(opening_date) as opening_date,
        max(latitude)     as latitude,
        max(longitude)    as longitude
    from parsed
    group by mrt_name

)

select *
from collapsed
where opening_date is not null
  and opening_date <= current_date
  and latitude is not null
  and longitude is not null
