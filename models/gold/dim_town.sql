/*
    Grain: one row per town. Type 1 -- a town's region and maturity are properties of
    Singapore's planning geography, not of the transaction. When HDB reclassifies
    one, the correct answer is that it always belonged to the new region, so there is
    no history here worth preserving.
*/

with towns as (

    select distinct town
    from {{ ref('silver_hdb_resale') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['town']) }} as town_key,
    town,

    case
        when town in ('SEMBAWANG', 'WOODLANDS', 'YISHUN')
            then 'North'
        when town in ('ANG MO KIO', 'HOUGANG', 'PUNGGOL', 'SENGKANG', 'SERANGOON')
            then 'North-East'
        when town in ('BEDOK', 'PASIR RIS', 'TAMPINES')
            then 'East'
        when town in ('BUKIT BATOK', 'BUKIT PANJANG', 'CHOA CHU KANG', 'CLEMENTI',
                      'JURONG EAST', 'JURONG WEST', 'TENGAH')
            then 'West'
        when town in ('BISHAN', 'BUKIT MERAH', 'BUKIT TIMAH', 'CENTRAL AREA', 'GEYLANG',
                      'KALLANG/WHAMPOA', 'MARINE PARADE', 'QUEENSTOWN', 'TOA PAYOH')
            then 'Central'
        else 'Unclassified'
    end as region,

    -- HDB's own mature/non-mature split, which drives resale pricing and BTO
    -- eligibility more than anything else on this table.
    town in ('ANG MO KIO', 'BEDOK', 'BISHAN', 'BUKIT MERAH', 'BUKIT TIMAH',
             'CENTRAL AREA', 'CLEMENTI', 'GEYLANG', 'KALLANG/WHAMPOA',
             'MARINE PARADE', 'PASIR RIS', 'QUEENSTOWN', 'SERANGOON',
             'TAMPINES', 'TOA PAYOH') as is_mature_estate

from towns
