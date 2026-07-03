"""game_logs pitch-cache queries."""

from ..util.json import loads_json_list


def load_all_pitches_for_player(cur, mlb_id: int) -> dict[tuple, list[dict]]:
    """Return {(year, sport_level): [pitch_dict, ...]} merged across all cached games.

    When a game_logs row has an empty sport_level, we attempt to resolve it
    from season_stats.  If the player only appeared at one level in that year,
    the resolution is unambiguous; otherwise the pitches are grouped under
    ``(year, "")`` and the caller must handle the ambiguity.
    """
    cur.execute(
        "SELECT date, sport_level, pitches_json FROM game_logs "
        "WHERE player_mlb_id = ? AND pitches_json != '[]' AND pitches_json IS NOT NULL",
        (mlb_id,),
    )
    by_year_level: dict[tuple, list[dict]] = {}
    # Buffer games with empty sport_level for resolution
    unresolved: list[tuple[int, list[dict]]] = []  # (year, pitches)

    for row in cur.fetchall():
        date_str = row[0] or ""
        sport_level = row[1] or ""
        if len(date_str) < 4:
            continue
        try:
            yr = int(date_str[:4])
        except ValueError:
            continue
        pitches = loads_json_list(row[2])
        if not pitches:
            continue
        if sport_level:
            by_year_level.setdefault((yr, sport_level), []).extend(pitches)
        else:
            unresolved.append((yr, pitches))

    if not unresolved:
        return by_year_level

    # Build {year: [sport_level, ...]} from season_stats for resolution
    cur.execute(
        "SELECT year, sport_level FROM season_stats "
        "WHERE player_mlb_id = ? AND sport_level != ''",
        (mlb_id,),
    )
    levels_by_year: dict[int, set[str]] = {}
    for row in cur.fetchall():
        levels_by_year.setdefault(row[0], set()).add(row[1])

    for yr, pitches in unresolved:
        known_levels = levels_by_year.get(yr, set())
        if len(known_levels) == 1:
            # Unambiguous: assign to the single known level
            lvl = next(iter(known_levels))
            by_year_level.setdefault((yr, lvl), []).extend(pitches)
        else:
            # Ambiguous or unknown: keep under empty key for caller to handle
            by_year_level.setdefault((yr, ""), []).extend(pitches)

    return by_year_level
