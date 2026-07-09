"""投手週報告：週值 + 週 vs 季 delta（重用既有 stats/ 函式，不重算公式）。"""

from ...util.numbers import ratio, safe_float, safe_int
from ..core.innings import ip_to_outs, outs_to_ip
from ..core.pitches import aggregate_pitches, ensure_pre_strikes
from ..batted_ball import batted_ball_metrics
from ..discipline import discipline_metrics
from ..tables.arsenal import compute_pitch_arsenal
from .derived import (
    attack_zone_distribution,
    derived_by_pitch_type,
    edge_pct,
    f_strike_pct,
)

# NEW/棄用 徽章門檻（plan §0.6）
NEW_WEEK_USAGE = 0.03
NEW_WEEK_COUNT = 3
NEW_SEASON_USAGE = 0.02
DROP_SEASON_USAGE = 0.05
DROP_MIN_WEEK_PITCHES = 30

_DISCIPLINE_DELTA_KEYS = (
    "whiff_pct", "o_swing_pct", "zone_pct", "csw_pct", "swstr_pct",
    "z_contact_pct",
)
_BATTED_DELTA_KEYS = ("avg_ev", "hard_hit_pct")


def _delta(week, season, digits=3):
    if week is None or season is None:
        return None
    return round(week - season, digits)


def pitcher_game_summary(stats: dict) -> str:
    ip = stats.get("inningsPitched") or "0.0"
    er = safe_int(stats.get("earnedRuns"), 0)
    k = safe_int(stats.get("strikeOuts"), 0)
    bb = safe_int(stats.get("baseOnBalls"), 0)
    return f"{ip} IP, {er} ER, {k} K, {bb} BB"


def _sum_ip(games) -> float | None:
    outs = sum(
        ip_to_outs(safe_float(g["stats"].get("inningsPitched")))
        for g in games
    )
    return outs_to_ip(outs)


def collect_scoring_events(games) -> list[dict]:
    out = []
    for g in games:
        for p in g["pitches"]:
            if not p.get("is_pa_final"):
                continue
            for r in p.get("runners") or []:
                if r.get("is_scoring_event"):
                    out.append({
                        "date": g["date"],
                        "inning": p.get("inning"),
                        "event": p.get("pa_event_desc") or r.get("event") or "",
                        "earned": r.get("earned"),
                    })
    return out


def build_arsenal_deltas(week_arsenal, season_arsenal, week_total: int):
    if not season_arsenal and not week_arsenal:
        return []
    if not season_arsenal:
        return []
    season_by_type = {r.get("type"): r for r in season_arsenal}
    rows = []
    for w in week_arsenal or []:
        s = season_by_type.get(w["type"]) or {}
        s_pct = safe_float(s.get("pct")) or 0.0
        w_pct = safe_float(w.get("pct")) or 0.0
        rows.append({
            "type": w["type"], "name": w.get("name") or w["type"],
            "count": w["count"],
            "week_pct": w_pct, "season_pct": s_pct or None,
            "usage_delta": round(w_pct - s_pct, 3),
            "week_velo": w.get("velo"), "season_velo": s.get("velo"),
            "velo_delta": _delta(w.get("velo"), s.get("velo"), 1),
            "whiff_delta": _delta(w.get("whiff_pct"), s.get("whiff_pct")),
            "chase_delta": _delta(w.get("chase_pct"), s.get("chase_pct")),
            "zone_delta": _delta(w.get("zone_pct"), s.get("zone_pct")),
            "is_new": (
                w_pct >= NEW_WEEK_USAGE
                and w["count"] >= NEW_WEEK_COUNT
                and s_pct < NEW_SEASON_USAGE
            ),
            "is_dropped": False,
        })
    if week_total >= DROP_MIN_WEEK_PITCHES:
        week_types = {r["type"] for r in rows}
        for s in season_arsenal:
            s_pct = safe_float(s.get("pct")) or 0.0
            if s.get("type") not in week_types and s_pct >= DROP_SEASON_USAGE:
                rows.append({
                    "type": s["type"], "name": s.get("name") or s["type"],
                    "count": 0, "week_pct": 0.0, "season_pct": s_pct,
                    "usage_delta": round(-s_pct, 3),
                    "week_velo": None, "season_velo": s.get("velo"),
                    "velo_delta": None, "whiff_delta": None,
                    "chase_delta": None, "zone_delta": None,
                    "is_new": False, "is_dropped": True,
                })
    rows.sort(key=lambda r: -(r["week_pct"] or 0))
    return rows


def _metric_deltas(week_metrics: dict, season_sc: dict, keys) -> dict:
    out = {}
    for key in keys:
        out[key] = {
            "week": week_metrics.get(key),
            "season": safe_float(season_sc.get(key)),
            "delta": _delta(week_metrics.get(key), safe_float(season_sc.get(key))),
        }
    return out


def build_pitcher_report(games: list[dict], season: dict) -> dict:
    season_sc = season.get("statcast") or {}
    week_pitches = [p for g in games for p in g["pitches"]]
    ensure_pre_strikes(week_pitches)

    for g in games:
        g["summary"] = pitcher_game_summary(g["stats"])

    week: dict = {
        "ip": _sum_ip(games),
        "er": sum(safe_int(g["stats"].get("earnedRuns"), 0) for g in games),
        "k": sum(safe_int(g["stats"].get("strikeOuts"), 0) for g in games),
        "bb": sum(safe_int(g["stats"].get("baseOnBalls"), 0) for g in games),
        "hits": sum(safe_int(g["stats"].get("hits"), 0) for g in games),
        "pickoffs": sum(
            1 for g in games for e in (g.get("events") or [])
            if e.get("type") == "pickoff"
        ),
        "arsenal": [],
        "derived_by_type": {},
    }
    metrics: dict = {}
    if week_pitches:
        agg = aggregate_pitches(week_pitches)
        metrics.update(discipline_metrics(agg))
        metrics.update(batted_ball_metrics(agg))
        week["arsenal"] = compute_pitch_arsenal(week_pitches)
        week["derived_by_type"] = derived_by_pitch_type(week_pitches)
        week["f_strike_pct"] = f_strike_pct(week_pitches)
        week["edge_pct"] = edge_pct(week_pitches)
        week["attack_zones"] = attack_zone_distribution(week_pitches)
        week.update(metrics)

    season_available = bool(season_sc)
    return {
        "tier": min((g["tier"] for g in games), default=3),
        "pitch_count": len(week_pitches),
        "games": games,
        "week": week,
        "season_available": season_available,
        "deltas": {
            "arsenal": build_arsenal_deltas(
                week["arsenal"], season_sc.get("pitch_arsenal"),
                len(week_pitches),
            ) if season_available else [],
            "discipline": _metric_deltas(
                metrics, season_sc,
                _DISCIPLINE_DELTA_KEYS + _BATTED_DELTA_KEYS,
            ) if season_available else {},
        },
        "scoring_events": collect_scoring_events(games),
    }
