"""Season trend chart (player-detail「圖表」分頁) payload builders.

與 movement.py / plinko.py 同樣的檔案定位——一個圖表一個檔案。跟兩者不同的是
這裡的資料是「逐場」而非「球季+層級」彙整，且直接在 build time 從已快取的
game_logs 現算（pitches_json 已經在 sync 階段抓好，逐場再彙整一次的成本很低），
所以不走 compute_*（sync）/combine_*（build）那組慣例，是單一 build-time 入口。

投手與打者版本都支援數據/年度/層級三維篩選，並共用分組與跨層級組裝邏輯。
"""

from ..levels import level_display, level_rank
from ..stats.batted_ball.sweet_spot import is_sweet_spot
from ..stats.advanced.woba import compute_pitch_woba
from ..stats.batting.avg import compute_avg
from ..stats.batting.bb_pct import compute_bb_pct
from ..stats.batting.k_pct import compute_k_pct
from ..stats.core.pitches import aggregate_pitches
from ..stats.core.pa_outcomes import compute_pa_outcome_totals
from ..stats.pitching.era import compute_era
from ..util.numbers import ratio

def _neumaier_add(total: float, compensation: float, x: float) -> tuple:
    """One step of streaming Neumaier (compensated) summation.

    CPython's built-in ``sum()`` has used compensated summation for floats
    since 3.12, so a plain running ``total += x`` here can round differently
    than the old code's ``sum(full_list)`` at the last decimal (verified:
    ``sum([...]) != naive accumulation`` on real exit-velocity data). This
    matches ``sum()`` bit-for-bit so switching to an incremental running
    total (needed to keep exit velocity O(N) — see the class docstring)
    doesn't change any displayed number.
    """
    t = total + x
    if abs(total) >= abs(x):
        compensation += (total - t) + x
    else:
        compensation += (x - t) + total
    return t, compensation


PITCHER_TREND_STAT_OPTIONS = [
    ("era", "ERA"),
    ("avg", "AVG"),
    ("k_pct", "K%"),
    ("bb_pct", "BB%"),
    ("whiff_pct", "Whiff%"),
    ("csw_pct", "CSW%"),
    ("swstr_pct", "SwStr%"),
    ("chase_pct", "Chase%"),
    ("z_contact_pct", "Z-Contact%"),
    ("hard_hit_pct", "HardHit%"),
    ("barrel_pct", "Barrel%"),
    ("exit_velocity", "Exit Velocity"),
]

BATTER_TREND_STAT_OPTIONS = [
    ("avg", "AVG"),
    ("k_pct", "K%"),
    ("bb_pct", "BB%"),
    ("woba", "wOBA"),
    ("exit_velocity", "Exit Velocity"),
    ("hard_hit_pct", "HardHit%"),
    ("barrel_pct", "Barrel%"),
    ("sweet_spot_pct", "SweetSpot%"),
    ("whiff_pct", "Whiff%"),
    ("chase_pct", "Chase%"),
    ("z_contact_pct", "Z-Contact%"),
    ("swstr_pct", "SwStr%"),
]


def _compute_pitcher_cumulative_metrics(games: list) -> list:
    """Season-to-date (cumulative through each game) values, aligned by index
    with *games* (already sorted chronologically, one level/year, OR every
    level merged together for the "_all" entry — see ``_build_all_levels_entry``).

    MLB Stats API gameLog rows give AVG/ERA/etc. as a cumulative rate stat,
    but that cumulative figure only tracks *that one level's* stint (it
    resets when a player is promoted/demoted). Using it directly would make
    ERA/AVG jump or reset to a tiny noisy sample right at every level change
    in the merged "_all" sequence. So — same as the raw counting fields
    (strikeOuts/baseOnBalls/battersFaced) below — we accumulate earnedRuns/
    outs/hits/atBats ourselves across whatever *games* we're given, so the
    resulting ERA/AVG stay continuous whether *games* is one level or the
    cross-level merge.

    ``aggregate_pitches`` is only ever called on *one game's own* pitches
    here, never on the season-to-date pile — the classification counts it
    returns are then folded into running totals. Re-running it on the whole
    pile every game (the previous approach) reclassifies every earlier pitch
    once per remaining game of the season, i.e. quadratic in total pitch
    count; a career's worth of games made this measurably slow at build
    time. The rate stats below (whiff%, CSW%, etc.) are pure count ratios —
    see ``stats/discipline/*.py`` and ``stats/batted_ball/{hard_hit,barrel}.py``
    — so folding counts in incrementally gives byte-identical numbers.
    """
    running_so = 0
    running_bb = 0
    running_bf = 0
    running_er = 0
    running_outs = 0
    running_hits = 0
    running_ab = 0
    running_swings = 0
    running_whiffs = 0
    running_called = 0
    running_total = 0
    running_out_zone = 0
    running_out_zone_swings = 0
    running_in_zone_swings = 0
    running_in_zone_contact = 0
    running_barrels = 0
    running_hard_hits = 0
    running_ev_sum = 0.0
    running_ev_c = 0.0
    running_bbe_n = 0
    out = []
    for log in games:
        s = log.stats_json or {}
        running_so += s.get("strikeOuts") or 0
        running_bb += s.get("baseOnBalls") or 0
        running_bf += s.get("battersFaced") or 0
        running_er += s.get("earnedRuns") or 0
        running_outs += s.get("outs") or 0
        running_hits += s.get("hits") or 0
        running_ab += s.get("atBats") or 0

        if log.pitches_json:
            agg = aggregate_pitches(log.pitches_json)
            running_swings += len(agg["swings"])
            running_whiffs += len(agg["whiffs"])
            running_called += len(agg["called"])
            running_total += agg["total"]
            running_out_zone += len(agg["out_zone"])
            running_out_zone_swings += len(agg["out_zone_swings"])
            running_in_zone_swings += len(agg["in_zone_swings"])
            running_in_zone_contact += len(agg["in_zone_contact"])
            running_barrels += agg["barrels"]
            running_hard_hits += agg["hard_hits"]
            for p in agg["bbe_ev"]:
                running_ev_sum, running_ev_c = _neumaier_add(running_ev_sum, running_ev_c, p["ev"])
                running_bbe_n += 1

        out.append({
            "era": compute_era(running_er, running_outs / 3.0),
            "avg": compute_avg(running_hits, running_ab),
            "k_pct": compute_k_pct(running_so, running_bf),
            "bb_pct": compute_bb_pct(running_bb, running_bf),
            "whiff_pct": ratio(running_whiffs, running_swings),
            "csw_pct": ratio(running_called + running_whiffs, running_total),
            "swstr_pct": ratio(running_whiffs, running_total),
            "chase_pct": ratio(running_out_zone_swings, running_out_zone),
            "z_contact_pct": ratio(running_in_zone_contact, running_in_zone_swings),
            "hard_hit_pct": ratio(running_hard_hits, running_bbe_n),
            "barrel_pct": ratio(running_barrels, running_bbe_n),
            "exit_velocity": round((running_ev_sum + running_ev_c) / running_bbe_n, 1) if running_bbe_n else None,
        })
    return out


def _compute_batter_cumulative_metrics(games: list) -> list:
    """Return season-to-date batter metrics aligned with chronological games.

    Same incremental-count approach as ``_compute_pitcher_cumulative_metrics``
    (see its docstring) — ``aggregate_pitches``/``compute_pa_outcome_totals``
    only ever see one game's own pitches, never the season-to-date pile.
    """
    running_hits = running_ab = running_so = running_bb = running_pa = 0
    running_swings = 0
    running_whiffs = 0
    running_called = 0
    running_total = 0
    running_out_zone = 0
    running_out_zone_swings = 0
    running_in_zone_swings = 0
    running_in_zone_contact = 0
    running_barrels = 0
    running_hard_hits = 0
    running_ev_sum = 0.0
    running_ev_c = 0.0
    running_bbe_n = 0
    running_woba_num = 0.0
    running_woba_den = 0
    running_sweet_spot_n = 0
    running_la_n = 0
    out = []
    for log in games:
        s = log.stats_json or {}
        running_hits += s.get("hits") or 0
        running_ab += s.get("atBats") or 0
        running_so += s.get("strikeOuts") or 0
        running_bb += s.get("baseOnBalls") or 0
        running_pa += s.get("plateAppearances") or 0

        if log.pitches_json:
            agg = aggregate_pitches(log.pitches_json)
            running_swings += len(agg["swings"])
            running_whiffs += len(agg["whiffs"])
            running_called += len(agg["called"])
            running_total += agg["total"]
            running_out_zone += len(agg["out_zone"])
            running_out_zone_swings += len(agg["out_zone_swings"])
            running_in_zone_swings += len(agg["in_zone_swings"])
            running_in_zone_contact += len(agg["in_zone_contact"])
            running_barrels += agg["barrels"]
            running_hard_hits += agg["hard_hits"]
            for p in agg["bbe_ev"]:
                running_ev_sum, running_ev_c = _neumaier_add(running_ev_sum, running_ev_c, p["ev"])
                running_bbe_n += 1
            for p in agg["in_play"]:
                la = p.get("la")
                if la is not None:
                    running_la_n += 1
                    if is_sweet_spot(la):
                        running_sweet_spot_n += 1
            totals = compute_pa_outcome_totals(agg["pa_final"])
            running_woba_num += totals["woba_num"]
            running_woba_den += totals["woba_den"]

        out.append({
            "avg": compute_avg(running_hits, running_ab),
            "k_pct": compute_k_pct(running_so, running_pa),
            "bb_pct": compute_bb_pct(running_bb, running_pa),
            "woba": compute_pitch_woba(
                {"woba_num": running_woba_num, "woba_den": running_woba_den}
            ),
            "exit_velocity": round((running_ev_sum + running_ev_c) / running_bbe_n, 1) if running_bbe_n else None,
            "hard_hit_pct": ratio(running_hard_hits, running_bbe_n),
            "barrel_pct": ratio(running_barrels, running_bbe_n),
            "sweet_spot_pct": ratio(running_sweet_spot_n, running_la_n),
            "whiff_pct": ratio(running_whiffs, running_swings),
            "chase_pct": ratio(running_out_zone_swings, running_out_zone),
            "z_contact_pct": ratio(running_in_zone_contact, running_in_zone_swings),
            "swstr_pct": ratio(running_whiffs, running_total),
        })
    return out


def _group_games_by_level(year_logs: list, year: int, metrics_seq_fn) -> dict:
    """Group a year's game logs by level, sort chronologically, compute
    season-to-date metrics for each level's game sequence via *metrics_seq_fn*.

    Grouping/sorting is deliberately kept separate from "how to compute
    metrics for a level's games" so a future batter trend builder can reuse
    this without depending on pitcher-specific stat logic. *metrics_seq_fn*
    takes the whole chronologically-sorted games list (not one game at a
    time) since the metrics are cumulative and therefore stateful.
    """
    by_raw_level: dict = {}
    for log in year_logs:
        by_raw_level.setdefault(log.sport_level, []).append(log)

    year_entry = {}
    for raw_level in sorted(by_raw_level, key=level_rank):
        level_key = level_display(raw_level, year)
        games = sorted(by_raw_level[raw_level], key=lambda g: g.date)
        metrics_seq = metrics_seq_fn(games)
        year_entry[level_key] = {
            "level_label": level_key,
            "games": [
                {
                    "date": g.date.strftime("%m/%d"),
                    "date_key": g.date.isoformat(),
                    **m,
                }
                for g, m in zip(games, metrics_seq)
            ],
        }
    return year_entry


def _build_all_levels_entry(year_logs: list, year: int, metrics_seq_fn) -> dict:
    """True cross-level season-to-date entry: merge every level's games by
    date and accumulate metrics with a single running total, instead of
    stitching together per-level cumulative sequences that each reset to
    zero (which would make the line jump on every promotion/demotion).

    Each game keeps its own ``level_label`` so the frontend can badge which
    level a given point belongs to.
    """
    all_games = sorted(year_logs, key=lambda g: g.date)
    metrics_seq = metrics_seq_fn(all_games)
    return {
        "level_label": "All Levels",
        "games": [
            {
                "date": g.date.strftime("%m/%d"),
                "date_key": g.date.isoformat(),
                "level_label": level_display(g.sport_level, year),
                **m,
            }
            for g, m in zip(all_games, metrics_seq)
        ],
    }


def build_pitcher_trend_by_year(logs_by_year: dict) -> dict:
    """year -> level_display string -> {"level_label", "games": [...]}.

    Also includes an "_all" key (when more than one level was played that
    year) holding a genuinely continuous cross-level cumulative sequence —
    see ``_build_all_levels_entry``.
    """
    result = {}
    for year in sorted(logs_by_year, reverse=True):
        year_logs = [log for log in logs_by_year[year] if log.date]
        if not year_logs:
            continue
        year_entry = _group_games_by_level(
            year_logs, year, _compute_pitcher_cumulative_metrics
        )
        if len(year_entry) > 1:
            year_entry["_all"] = _build_all_levels_entry(
                year_logs, year, _compute_pitcher_cumulative_metrics
            )
        result[year] = year_entry
    return result


def build_batter_trend_by_year(logs_by_year: dict) -> dict:
    """Build the filtered batter trend payload for every available season."""
    result = {}
    for year in sorted(logs_by_year, reverse=True):
        year_logs = [log for log in logs_by_year[year] if log.date]
        if not year_logs:
            continue
        year_entry = _group_games_by_level(
            year_logs, year, _compute_batter_cumulative_metrics
        )
        if len(year_entry) > 1:
            year_entry["_all"] = _build_all_levels_entry(
                year_logs, year, _compute_batter_cumulative_metrics
            )
        result[year] = year_entry
    return result
