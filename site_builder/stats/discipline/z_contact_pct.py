"""Z-Contact% — contact on in-zone swings / in-zone swings."""

from ...util.numbers import ratio


def compute_z_contact_pct(agg: dict):
    return ratio(len(agg["in_zone_contact"]), len(agg["in_zone_swings"]))
