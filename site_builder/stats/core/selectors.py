"""Domain selectors over season-stat rows (appearance / highest level)."""

from typing import Optional

from ...levels import level_rank, to_tier_key
from ...positions import BATTER, PITCHER
from ...util.numbers import safe_float
from .innings import ip_to_outs


def has_appearance(stat) -> bool:
    if not stat:
        return False
    if (stat.gp or 0) > 0:
        return True
    if (stat.pa or 0) > 0:
        return True
    if (stat.ab or 0) > 0:
        return True
    if (stat.bf or 0) > 0:
        return True
    return ip_to_outs(stat.ip) > 0


def appeared_roles(row) -> set[str]:
    """這一列 season_stats 有出賽紀錄的角色（``positions.BATTER`` / ``PITCHER``）。

    衍生數據（wRC+、FIP、sabermetrics 各 group）「這個角色要不要算」的唯一判斷。
    不看 ``gp``：它依角色拆成 ``gp`` / ``p_gp``（見 ``positions.ROLE_SPLIT_FIELDS``），
    而打擊 PA、投球 BF/IP 本來就只屬於一個角色。
    """
    roles: set[str] = set()
    if (row.get("pa") or 0) > 0:
        roles.add(BATTER)
    # ip 存 float（sync/field_maps.py），safe_float 同時容許 API 原樣的字串
    if (row.get("bf") or 0) > 0 or ip_to_outs(safe_float(row.get("ip"))) > 0:
        roles.add(PITCHER)
    return roles


def highest_level_row(stats):
    """Return the highest-level row among *stats*, or None.

    Callers choose the scope: the retired page passes the whole career
    ("highest level ever reached"), ``sync/players.py`` passes only the latest
    season (the player's last level).

    Ranking goes through :func:`level_rank` (see ``site_builder.levels``), which
    collapses every historical spelling onto its tier, so the comparison is
    correct across the 2021 MiLB reorganization.  Rows with real appearances are
    preferred; if none have appearances we fall back to all rows.

    The row carries both ``sport_level`` (tier key) and ``year``, so callers can
    render the period-accurate display via :func:`levels.level_display`.

    同層級的平手規則（結果與列的順序無關）：先取最近一年、同年再取出賽量
    （PA + BF）較多的隊，最後以隊名決定。``-year`` 不可省略：退役頁傳整個生涯，
    多年待在同一個最高層級時標章要取「最近一次」到達的年份——``badge_year``
    決定 ``level_display()`` 顯示 2021 改制前或後的名稱（A(Adv) / A+）。
    """
    if not stats:
        return None
    appeared = [s for s in stats if has_appearance(s)]
    pool = appeared or list(stats)
    return min(pool, key=lambda s: (
        level_rank(s.sport_level),
        -(s.get("year") or 0),
        -((s.get("pa") or 0) + (s.get("bf") or 0)),
        s.get("team_name") or "",
    ))


def highest_level(stats) -> Optional[str]:
    """Return the canonical tier key of the highest level reached (or None).

    Hierarchy (highest → lowest): MLB > AAA > AA > A+ > A > A- > ROA > ROK.  A
    pre-2021 High-A peak is reported as its tier key "A+", not "A(Adv)".  For period-accurate display
    use :func:`highest_level_row` + :func:`levels.level_display` instead.
    """
    best = highest_level_row(stats)
    if best is None:
        return None
    return to_tier_key(best.sport_level) or None
