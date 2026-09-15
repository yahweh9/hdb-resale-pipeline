/*
    Grain: one row per physical block address.

    Carries the spatial attributes, because location is a property of the block and
    not of the transaction. Putting distance-to-MRT on the fact would repeat the same
    value across every sale in the same block -- 240,000 rows to store 9,744 facts.

    Coordinates are LEFT joined. An address OneMap could not resolve still gets a
    dim_block row, with null coordinates, so its transactions stay in the fact rather
    than silently vanishing. The geocoding coverage test is what keeps that honest.
*/

{% set cbd_lat = 1.2839 %}
{% set cbd_lon = 103.8515 %}

with blocks as (

    select distinct
        address,
        block,
        street_name,
        town
    from {{ ref('silver_hdb_resale') }}

),

located as (

    select
        b.address,
        b.block,
        b.street_name,
        b.town,
        c.latitude,
        c.longitude,
        c.postal_code
    from blocks b
    left join {{ ref('silver_hdb_coordinates') }} c using (address)

),

nearest_station as (

    -- 9,744 blocks x 181 stations is 1.8M pairs, which DuckDB scans in well under a
    -- second. A spatial index would be the answer at a hundred times this size.
    select
        l.address,
        m.station_name,
        m.lines,
        {{ haversine_km('l.latitude', 'l.longitude', 'm.latitude', 'm.longitude') }} as dist_km
    from located l
    join {{ ref('silver_mrt_stations') }} m
      on l.latitude is not null
    qualify row_number() over (
        partition by l.address
        order by {{ haversine_km('l.latitude', 'l.longitude', 'm.latitude', 'm.longitude') }}
    ) = 1

)

select
    {{ dbt_utils.generate_surrogate_key(['l.address']) }} as block_key,
    l.address,
    l.block,
    l.street_name,
    l.town,
    l.postal_code,

    l.latitude,
    l.longitude,

    round({{ haversine_km('l.latitude', 'l.longitude', cbd_lat, cbd_lon) }}, 2) as dist_to_cbd_km,

    n.station_name                as nearest_mrt_name,
    n.lines                       as nearest_mrt_lines,
    round(n.dist_km, 2)           as dist_to_nearest_mrt_km,

    -- Bands are classified on the unrounded distance; the rounding above is for
    -- display only. Banding the rounded column instead would put a block 403m away
    -- ("0.40 km") in 0-400m while is_near_mrt said it was not near -- 1,096 sales
    -- counted as near by one and far by the other.
    {{ mrt_band_order('n.dist_km') }} as mrt_band_order,
    {{ mrt_band_label('n.dist_km') }} as mrt_band,

    -- 400m is the conventional planning threshold for "walkable to a station" and is
    -- what HDB and URA use in their own accessibility studies. Defined as the first
    -- band, so "near MRT" and "0-400m" can never disagree.
    {{ mrt_band_order('n.dist_km') }} = 1 as is_near_mrt

from located l
left join nearest_station n using (address)
