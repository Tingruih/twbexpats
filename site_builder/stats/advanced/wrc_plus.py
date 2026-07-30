"""TJBat+ (wRC+) computation aligned with the TJStats glossary formulas.

Everything this module needs from tjstats.ca — the club's park factor and its
league's lg_wOBA / lg_R/PA — is resolved by the caller and passed in as one
per-club record (see ``league_constant.batting``). Nothing here touches the
network or the database.
"""

from typing import Optional

from ...constants import WOBA_SCALE
from ..core.aggregate import aggregate_stats
from .woba import compute_season_woba


def compute_wrc_plus(
    woba: float, pf_final: float, lg_woba: float, lg_r_pa: float
) -> Optional[int]:
    """TJStats wRC+ formula: 100 x (wRC/PA / PFm) / lg_R/PA, rounded to an int."""
    if not lg_r_pa:
        return None
    wrc_pa = (woba - lg_woba) / WOBA_SCALE + lg_r_pa
    pfm = 1 + (pf_final - 1) * 0.5
    if not pfm:
        return None
    return round(100 * (wrc_pa / pfm) / lg_r_pa)


def annotate_wrc_plus(bundles, batting_lookup) -> None:
    """Compute and inject wRC+ into season_stats rows for qualifying batters.

    bundles is [(player, stats, logs), ...] as produced by
    db.bundles.load_player_bundle. Mutates the per-season Obj rows in `stats`
    in place (never written back to `season_stats` — recomputed every build).

    ``batting_lookup(level, year) -> {team_name: BattingConstant}`` resolves
    one slice's park factors and league constants. Pass
    ``league_constant.batting.BattingConstants(conn, ...).for_level`` so a
    whole build fetches each slice exactly once. A level/year TJStats doesn't
    publish comes back as an empty mapping, which drops those rows through
    the same path as an unknown club — so this module needs no coverage check
    of its own.

    For each batter's rows, grouped by (year, sport_level):
      - The row with the most PA in the group determines which team's park
        factor and league (and therefore league constants) are used for
        every row in the group -- mirrors how TJStats itself treats players
        traded between two teams at the same level.
      - MLB rows: the computed value is stored as `wrc_plus_calc`; the
        API-sourced `wrc_plus` value itself is never overwritten.
      - Non-MLB rows: the computed value is written directly into
        `wrc_plus`, the field the templates already render.
      - When the group holds more than one row (traded inside the same
        level), a whole-group value computed from the summed batting line is
        written to every row of the group as `wrc_plus_calc_group` (MLB) /
        `wrc_plus_group` (non-MLB).  render.pages reads it when collapsing a
        year's several same-level rows into one; averaging the per-row wRC+
        would be wrong, since wOBA is a rate and has to be recomputed from
        the combined counting stats.
    """
    for player, stats, _logs in bundles:
        if player.position == "P":
            continue

        by_year_level: dict[tuple[int, str], list] = {}
        for s in stats:
            by_year_level.setdefault((s.year, s.sport_level), []).append(s)

        for (yr, level), rows in by_year_level.items():
            primary = max(rows, key=lambda r: r.get("pa") or 0)
            env = batting_lookup(level, yr).get(primary.team_name)
            if env is None:
                continue

            def _wrc_plus_of(stat_row, env=env):
                woba = compute_season_woba(stat_row)
                if woba is None:
                    return None
                return compute_wrc_plus(
                    woba, env.pf_final, env.lg_woba, env.lg_r_pa
                )

            calc_field = "wrc_plus_calc" if level == "MLB" else "wrc_plus"
            for row in rows:
                calc = _wrc_plus_of(row)
                if calc is not None:
                    row[calc_field] = calc

            if len(rows) > 1:
                group_calc = _wrc_plus_of(aggregate_stats(rows))
                if group_calc is not None:
                    for row in rows:
                        row[calc_field + "_group"] = group_calc
