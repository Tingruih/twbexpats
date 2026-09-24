"""Career and per-year aggregations over season-stat rows."""

from ...levels import is_milb, is_mlb, level_display
from .aggregate import aggregate_stats
from .annotate import annotate_row


def _teams_display(stats) -> str:
    """「層級 球隊」以 / 串接；層級依該列年份顯示（2020 年以前為舊制名稱）。"""
    return " / ".join(f"{level_display(s.sport_level, s.year)} {s.team_name}" for s in stats)


def compute_career(stats, level_filter=None):
    """Aggregate counting stats across multiple seasons and compute rates."""
    if level_filter == "mlb":
        stats = [s for s in stats if is_mlb(s.sport_level)]
    elif level_filter == "milb":
        stats = [s for s in stats if is_milb(s.sport_level)]

    if not stats:
        return None

    career = aggregate_stats(stats)

    career["teams_display"] = _teams_display(stats)

    years_set = sorted(set(s.year for s in stats))
    if len(years_set) > 1:
        career["years_range"] = f"{years_set[0]}–{years_set[-1]}"
    elif years_set:
        career["years_range"] = str(years_set[0])
    else:
        career["years_range"] = ""

    return career


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

    summary 是全站唯一的「單一年度合計列」：成績表的年度列與 bio 卡的本季合計
    （render/pages.py 的 season_combined）讀的是同一個物件，所以欄位必定一致。
    """
    years = sorted({s.year for s in all_stats}, reverse=True)
    groups = []
    for yr in years:
        yr_stats = [s for s in all_stats if s.year == yr]
        # Sort rows: MLB first, then by level order
        yr_stats.sort(key=lambda s: s.level_order)

        summary = aggregate_stats(yr_stats)
        summary["year"] = yr
        summary["teams_display"] = _teams_display(yr_stats)

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
