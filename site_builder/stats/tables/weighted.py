"""Shared count-weighted combiner for per-pitch-type tables."""

from ..core.pitches import is_unknown_pitch_type


def combine_pitch_type_data(
    entries: list[dict],
    sc_key: str,
    rate_fields: list[str],
    include_pct: bool = False,
) -> list[dict]:
    """Combine per-level pitch-type data via count-weighted averages.

    Args:
        entries: list of {sport_level, team_name, sc} dicts.
        sc_key: key inside ``sc`` to read (``"vs_pitch_types"`` or ``"pitch_arsenal"``).
        rate_fields: field names to weight-average by pitch count.
        include_pct: if True, compute ``pct`` (type count / grand total) in output.

    Returns:
        Combined list sorted by pitch count descending.
        ``put_away_pct`` is always weighted by ``two_strike_count`` for accuracy.
    """
    total_count = 0
    by_type: dict[str, dict] = {}

    for e in entries:
        if e.get("sport_level") == "_combined":
            continue
        items = (e.get("sc") or {}).get(sc_key) or []
        for pt in items:
            t = pt.get("type", "UN")
            name = pt.get("name", t)
            if is_unknown_pitch_type(t, name):
                continue
            n = pt.get("count", 0)
            total_count += n
            if t not in by_type:
                by_type[t] = {
                    "name": name,
                    "count": 0,
                    "two_strike_count": 0,
                    "wsums": {f: 0.0 for f in rate_fields},
                    "wcounts": {f: 0.0 for f in rate_fields},
                    "pa_wsum": 0.0,
                    "pa_wcount": 0.0,
                }
            bucket = by_type[t]
            bucket["count"] += n
            two_k_n = pt.get("two_strike_count", 0)
            bucket["two_strike_count"] += two_k_n
            pa_pct = pt.get("put_away_pct")
            if pa_pct is not None and two_k_n:
                bucket["pa_wsum"] += pa_pct * two_k_n
                bucket["pa_wcount"] += two_k_n
            for f in rate_fields:
                v = pt.get(f)
                if v is not None:
                    bucket["wsums"][f] += v * n
                    bucket["wcounts"][f] += n

    out = []
    for t, bucket in by_type.items():
        n = bucket["count"]
        row: dict = {"type": t, "name": bucket["name"], "count": n}
        if include_pct:
            row["pct"] = round(n / total_count, 4) if total_count else None
        for f in rate_fields:
            wc = bucket["wcounts"][f]
            row[f] = round(bucket["wsums"][f] / wc, 4) if wc else None
        pa_wc = bucket["pa_wcount"]
        row["put_away_pct"] = round(bucket["pa_wsum"] / pa_wc, 4) if pa_wc else None
        out.append(row)
    out.sort(key=lambda r: r.get("count", 0), reverse=True)
    return out
