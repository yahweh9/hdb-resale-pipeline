/*
    Grain: one row per (flat type, flat model, storey range) -- a junk dimension of
    the descriptors that travel with a transaction.

    Type 1, and not by omission: these attributes describe the flat AS SOLD on that
    date and do not change afterwards, so there is no later version of the row for a
    Type 2 history to preserve. Floor area stays in the fact because it varies
    between individual units that share all three of these attributes.
*/

with flats as (

    select distinct
        flat_type,
        flat_model,
        storey_range,
        storey_lower,
        storey_upper
    from {{ ref('silver_hdb_resale') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['flat_type', 'flat_model', 'storey_range']) }} as flat_key,
    flat_type,
    flat_model,
    storey_range,
    storey_lower,
    storey_upper,

    case
        when storey_lower <= 4  then 'Low (1-4)'
        when storey_lower <= 9  then 'Mid (5-9)'
        when storey_lower <= 19 then 'High (10-19)'
        else 'Ultra-High (20+)'
    end as floor_tier

from flats
