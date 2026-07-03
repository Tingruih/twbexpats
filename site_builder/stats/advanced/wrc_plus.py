"""TJBat+ (wRC+) computation aligned with the TJStats glossary formulas.

Park factors and league constants are fetched from tjstats.ca via
``site_builder.db.tjstats_cache``, which caches them in SQLite (see that
module's docstring) so a normal build never has to re-scrape a season once
its numbers are cached.
"""

import sqlite3
from typing import Optional

from ...constants import LC_LEVEL_CODE, MIN_WRC_YEAR, WOBA_SCALE, WRC_LEVELS
from ...db.tjstats_cache import get_league_constants, get_park_factors
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


def annotate_wrc_plus(bundles, conn: sqlite3.Connection, force_refresh: bool = False) -> None:
    """Compute and inject wRC+ into season_stats rows for qualifying batters.

    bundles is [(player, stats, logs), ...] as produced by
    db.bundles.load_player_bundle. Mutates the per-season Obj rows in `stats`
    in place (never written back to `season_stats` — recomputed every build);
    the TJStats park-factor/league-constant inputs themselves are cached in
    SQLite via ``db.tjstats_cache`` (see that module's docstring). Pass
    ``force_refresh=True`` to bypass the cache and re-scrape tjstats.ca.

    For each batter's rows, grouped by (year, sport_level):
      - The row with the most PA in the group determines which team's park
        factor and league (and therefore league constants) are used for
        every row in the group -- mirrors how TJStats itself treats players
        traded between two teams at the same level.
      - MLB rows: the computed value is stored as `wrc_plus_calc`; the
        API-sourced `wrc_plus` value itself is never overwritten.
      - Non-MLB rows: the computed value is written directly into
        `wrc_plus`, the field the templates already render.
    """
    pf_cache: dict[tuple[str, int], dict] = {}
    lc_cache: dict[int, dict] = {}

    def _park_factors(level, year):
        key = (level, year)
        if key not in pf_cache:
            pf_cache[key] = get_park_factors(conn, level, year, force_refresh=force_refresh)
        return pf_cache[key]

    def _league_constants(year):
        if year not in lc_cache:
            lc_cache[year] = get_league_constants(conn, year, force_refresh=force_refresh)
        return lc_cache[year]

    for player, stats, _logs in bundles:
        if player.position == "P":
            continue

        by_year_level: dict[tuple[int, str], list] = {}
        for s in stats:
            if s.year < MIN_WRC_YEAR or s.sport_level not in WRC_LEVELS:
                continue
            by_year_level.setdefault((s.year, s.sport_level), []).append(s)

        for (yr, level), rows in by_year_level.items():
            primary = max(rows, key=lambda r: r.get("pa") or 0)
            pf_entry = _park_factors(level, yr).get(primary.team_name)
            if pf_entry is None:
                continue
            lc_key = (LC_LEVEL_CODE[level], pf_entry["league"])
            lc_entry = _league_constants(yr).get(lc_key)
            if lc_entry is None:
                continue

            for row in rows:
                woba = compute_season_woba(row)
                if woba is None:
                    continue
                calc = compute_wrc_plus(
                    woba, pf_entry["pf_final"], lc_entry["lg_woba"], lc_entry["lg_r_pa"]
                )
                if calc is None:
                    continue
                if level == "MLB":
                    row["wrc_plus_calc"] = calc
                else:
                    row["wrc_plus"] = calc
