"""Career and per-year aggregations over season-stat rows."""

from ...util.obj import Obj
from .aggregate import aggregate_stats, compute_rate_stats, sum_counting
from .annotate import annotate_row
from .innings import ip_to_outs, outs_to_ip


def compute_career(stats, level_filter=None):
    """Aggregate counting stats across multiple seasons and compute rates."""
    if level_filter == "mlb":
        stats = [s for s in stats if s.sport_level == "MLB"]
    elif level_filter == "milb":
        stats = [s for s in stats if s.sport_level != "MLB"]

    if not stats:
        return None

    career = aggregate_stats(stats)

    teams = [f"{s.sport_level} {s.team_name}" for s in stats]
    career["teams_display"] = " / ".join(teams)

    years_set = sorted(set(s.year for s in stats))
    if len(years_set) > 1:
        career["years_range"] = f"{years_set[0]}–{years_set[-1]}"
    elif years_set:
        career["years_range"] = str(years_set[0])
    else:
        career["years_range"] = ""

    return career


def compute_season_combined(stats, year):
    """Aggregate counting stats for a single year across teams."""
    stats = [s for s in stats if s.year == year]
    if not stats:
        return None

    combined = aggregate_stats(stats)

    teams = [f"{s.sport_level} {s.team_name}" for s in stats]
    combined["teams_display"] = " / ".join(teams)
    combined["year"] = year

    return combined


def compute_year_groups(all_stats):
    """Group stats by year, producing a summary row + per-team detail rows.

    Returns a list of dicts (ordered most-recent year first)::

        [
          {
            "year": 2024,
            "summary": <Obj with summed counts + recalculated rates>,
            "rows": [<Obj per team/level row for that year>],
            "multi": True/False,   # True when player was on 2+ teams that year
          },
          ...
        ]

    ERA and WHIP on the summary row are computed from total outs (IP via
    ip_to_outs) so cross-team ERA is always accurate.
    """
    years = sorted({s.year for s in all_stats}, reverse=True)
    groups = []
    for yr in years:
        yr_stats = [s for s in all_stats if s.year == yr]
        # Sort rows: MLB first, then by level order
        yr_stats.sort(key=lambda s: s.level_order)

        summary = Obj()
        sum_counting(yr_stats, summary)
        total_outs = sum(ip_to_outs(s.ip) for s in yr_stats)
        summary["ip"] = outs_to_ip(total_outs)
        compute_rate_stats(summary)
        summary["year"] = yr

        # np alias for template compatibility
        summary["np"] = summary.get("pitches")

        # Fill in all advanced / derived stats
        annotate_row(summary)

        groups.append({
            "year": yr,
            "summary": summary,
            "rows": yr_stats,
            "multi": len(yr_stats) > 1,
        })
    return groups
