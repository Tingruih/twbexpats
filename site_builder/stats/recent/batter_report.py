"""打者週報告：週值 + 週 vs 季 delta。"""

from ...util.numbers import mean_round, ratio, safe_int
from ..batted_ball import batted_ball_metrics
from ..batted_ball.exit_velocity import compute_ev90, compute_max_ev
from ..batted_ball.launch_angle import compute_avg_la
from ..batted_ball.sweet_spot import compute_sweet_spot_pct
from ..core.pitches import aggregate_pitches, ensure_pre_strikes, is_swing, is_whiff
from ..discipline import discipline_metrics
from .pitcher_report import _delta, _metric_deltas
from .zone_stats import AB_EVENTS, HIT_EVENTS

FASTBALLS = frozenset({"FF", "FA", "SI", "FT", "FC"})
BREAKING = frozenset({"SL", "ST", "SV", "CU", "KC", "CS", "KN", "EP"})
OFFSPEED = frozenset({"CH", "FS", "FO", "SC"})
GROUP_LABELS = (("fastball", "速球"), ("breaking", "變化球"), ("offspeed", "慢速球"))

_DISCIPLINE_DELTA_KEYS = (
    "o_swing_pct", "whiff_pct", "z_contact_pct", "swstr_pct", "zone_pct",
)
_QUALITY_DELTA_KEYS = ("avg_ev", "hard_hit_pct")


def pitch_group(ptype) -> str | None:
    if ptype in FASTBALLS:
        return "fastball"
    if ptype in BREAKING:
        return "breaking"
    if ptype in OFFSPEED:
        return "offspeed"
    return None


def _batting_line(games) -> dict:
    line = {key: 0 for key in ("ab", "hits", "hr", "rbi", "bb", "k")}
    src = (("ab", "atBats"), ("hits", "hits"), ("hr", "homeRuns"),
           ("rbi", "rbi"), ("bb", "baseOnBalls"), ("k", "strikeOuts"))
    for g in games:
        for dst_key, stat_key in src:
            line[dst_key] += safe_int(g["stats"].get(stat_key), 0)
    line["avg"] = ratio(line["hits"], line["ab"])
    return line


def batter_game_summary(stats: dict) -> str:
    if stats.get("summary"):
        return stats["summary"]
    ab = safe_int(stats.get("atBats"), 0)
    hits = safe_int(stats.get("hits"), 0)
    return f"{hits}-{ab}"


def group_splits(pitches) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for p in pitches:
        grp = pitch_group(p.get("pitch_type"))
        if grp:
            buckets.setdefault(grp, []).append(p)
    out = []
    for grp, _label in GROUP_LABELS:
        ps = buckets.get(grp)
        if not ps:
            continue
        swings = [p for p in ps if is_swing(p)]
        finals = [p for p in ps if p.get("is_pa_final")]
        ab = sum(1 for p in finals if (p.get("pa_event") or "") in AB_EVENTS)
        hits = sum(1 for p in finals if (p.get("pa_event") or "") in HIT_EVENTS)
        out.append({
            "group": grp,
            "n": len(ps),
            "whiff_pct": ratio(sum(1 for p in swings if is_whiff(p)),
                               len(swings), digits=6),
            "ab": ab, "hits": hits, "avg": ratio(hits, ab),
            "avg_ev": mean_round(
                [p.get("ev") for p in ps if p.get("is_in_play")], 1),
        })
    return out


def two_strike_summary(pitches) -> dict:
    finals = [
        p for p in pitches
        if p.get("is_pa_final") and p.get("pre_strikes") == 2
        and (p.get("pa_event") or "") not in ("",)
    ]
    ab = [p for p in finals if p["pa_event"] in AB_EVENTS]
    hits = [p for p in ab if p["pa_event"] in HIT_EVENTS]
    return {
        "pa": len(finals),
        "k": sum(1 for p in finals
                 if p["pa_event"] in ("strikeout", "strikeout_double_play")),
        "hits": len(hits),
        "avg": ratio(len(hits), len(ab)),
    }


def hardness_distribution(pitches) -> dict | None:
    counts = {"soft": 0, "medium": 0, "hard": 0}
    total = 0
    for p in pitches:
        h = p.get("hardness")
        if p.get("is_in_play") and h in counts:
            counts[h] += 1
            total += 1
    if not total:
        return None
    out = {k: ratio(v, total, digits=3) for k, v in counts.items()}
    out["n"] = total
    return out


def pa_timeline(games) -> list[dict]:
    out = []
    for g in games:
        seq: list[tuple[str, str]] = []
        for p in g["pitches"]:
            seq.append((p.get("pitch_type") or "?", p.get("result_code") or ""))
            if p.get("is_pa_final"):
                entry = {
                    "date": g["date"],
                    "opponent": g["opponent"],
                    "inning": p.get("inning"),
                    "pitch_hand": p.get("pitch_hand") or "",
                    "sequence": seq,
                    "result": p.get("pa_event_desc") or p.get("pa_event") or "",
                    "hit": None,
                }
                if p.get("is_in_play"):
                    entry["hit"] = {"ev": p.get("ev"), "la": p.get("la"),
                                    "distance": p.get("hit_distance")}
                out.append(entry)
                seq = []
    return out


def build_batter_report(games: list[dict], season: dict) -> dict:
    season_sc = season.get("statcast") or {}
    week_pitches = [p for g in games for p in g["pitches"]]
    ensure_pre_strikes(week_pitches)

    for g in games:
        g["summary"] = batter_game_summary(g["stats"])

    line = _batting_line(games)
    week: dict = {"batting_line": line}
    metrics: dict = {}
    if week_pitches:
        agg = aggregate_pitches(week_pitches)
        metrics.update(discipline_metrics(agg))
        metrics.update(batted_ball_metrics(agg))
        week.update(metrics)
        finals = agg["pa_final"]
        pa = len(finals) or None
        week["k_pct"] = ratio(line["k"], pa) if pa else None
        week["bb_pct"] = ratio(line["bb"], pa) if pa else None
        la_values = [p["la"] for p in agg["in_play"] if p.get("la") is not None]
        week["ev"] = {
            "avg_ev": metrics.get("avg_ev"),
            "max_ev": compute_max_ev(agg["bbe_ev"]),
            "ev90": compute_ev90(agg["bbe_ev"]),
            "avg_la": compute_avg_la(la_values),
            "sweet_spot_pct": compute_sweet_spot_pct(la_values),
            "hard_hit_pct": metrics.get("hard_hit_pct"),
            "barrel_pct": metrics.get("barrel_pct"),
            "bbe": metrics.get("bbe"),
            # MLB withMetrics 新欄位；MiLB 無資料時為 None
            "bat_speed": mean_round(
                [p.get("bat_speed") for p in week_pitches], 1),
        }
        week["hardness"] = hardness_distribution(week_pitches)

    season_available = bool(season_sc)
    return {
        "tier": min((g["tier"] for g in games), default=3),
        "pitch_count": len(week_pitches),
        "games": games,
        "week": week,
        "season_available": season_available,
        "deltas": {
            "discipline": _metric_deltas(
                metrics, season_sc,
                _DISCIPLINE_DELTA_KEYS + _QUALITY_DELTA_KEYS,
            ) if season_available else {},
        },
        "group_splits": group_splits(week_pitches),
        "two_strike": two_strike_summary(week_pitches),
        "pa_timeline": pa_timeline(games),
    }
