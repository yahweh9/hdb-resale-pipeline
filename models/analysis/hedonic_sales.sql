/*
    Grain: one resale transaction, shaped as the hedonic model's input.

    Every band the model uses is assigned here, in SQL, so the Python model only ever
    fits -- it never decides where a band edge falls. The MRT band comes from dim_block,
    where it is classified on the unrounded distance; the lease band is a property of
    the sale (lease remaining when it sold), so it is assigned per transaction.

    A sale the model cannot place is left out rather than guessed: an ungeocoded block
    has no MRT band. The geocoding coverage test keeps that set empty in practice.
*/

select
    x.resale_txn_key,
    x.block_key,
    t.town,
    b.mrt_band,
    {{ lease_band('x.remaining_lease_months') }} as lease_band,
    f.floor_tier,
    f.flat_type,
    strftime(x.transaction_month, '%Y-%m')      as transaction_month,
    d.calendar_year,
    x.price_psm
from {{ ref('fact_resale_txn') }} x
join {{ ref('dim_town') }}  t using (town_key)
join {{ ref('dim_flat') }}  f using (flat_key)
join {{ ref('dim_block') }} b using (block_key)
join {{ ref('dim_date') }}  d using (date_key)
where b.mrt_band is not null
  and x.remaining_lease_months is not null
