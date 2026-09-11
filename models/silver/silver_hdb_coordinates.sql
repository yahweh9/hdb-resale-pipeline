{{ config(materialized = 'table') }}

/*
    Grain: one row per HDB block address, geocoded via OneMap.

    Deduplicated on address because the bronze file is appended to across incremental
    geocoding runs -- an address geocoded twice would otherwise fan out dim_block.
    Newest wins, on the same principle as the resale silver model.
*/

select
    address,
    cast(latitude as double)  as latitude,
    cast(longitude as double) as longitude,
    postal_code
from {{ source('spatial', 'hdb_coordinates') }}
qualify row_number() over (partition by address order by latitude) = 1
