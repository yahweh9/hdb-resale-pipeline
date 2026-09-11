-- Singapore is roughly 50km east to west. Any block more than 5km from its NEAREST
-- station means the haversine is wrong, the coordinates are swapped, or the station
-- list lost a line -- all of which look fine until someone reads the number.

select address, nearest_mrt_name, dist_to_nearest_mrt_km
from {{ ref('dim_block') }}
where dist_to_nearest_mrt_km > 5
