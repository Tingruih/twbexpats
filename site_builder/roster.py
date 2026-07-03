"""
Single source of truth for roster logic: the tracked-player list
(src/data/roster.json) and player roster-status classification.

Modelled on ``site_builder.levels`` — no other module may define its own
roster status-code table; import from this one instead.
"""

import json
import logging

from .util.dates import parse_date

logger = logging.getLogger(__name__)


# ── Roster file (the tracked-player list) ──


def parse_roster_from_file(filepath) -> list:
    """Parse player roster entries from a JSON file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("players", [])
    except Exception as e:
        logger.error("Error reading %s: %s", filepath, e)
        return []


def build_roster_map(roster_file) -> dict:
    """Return {mlb_id: pconf} for quick lookup."""
    return {p["mlb_id"]: p for p in parse_roster_from_file(roster_file)}


# ── Roster status classification ──

# `rosterEntries[0].status.code` values meaning the player is on an injured
# list (or a rehab assignment from one) while that roster entry is still
# active (isActive=true).
ROSTER_INJURED_CODES = {"D7", "D10", "D15", "D60", "ILF", "RA"}

# `rosterEntries[0].status.code` values meaning the player is on personal /
# disciplinary leave while that roster entry is still active (isActive=true).
# SU=Suspension, RES=Reserve List (Minors), BRV=Bereavement,
# FME=Family Medical Emergency, RST=Restricted List, IN=Ineligible List,
# PL=Paternity List, MIL=Military Leave, ADM=Administrative Leave,
# TI=Temporary Inactive List.
ROSTER_RESTRICTED_CODES = {
    "SU", "RES", "BRV", "FME", "RST", "IN", "PL", "MIL", "ADM", "TI",
}

# `rosterEntries[0].status.code` values meaning the roster entry is a
# transitional roster move (e.g. DFA limbo) while still active
# (isActive=true), distinct from injury or leave.
ROSTER_OTHER_CODES = {"DES"}

# `rosterEntries[0].status.code` values meaning the player has left the
# organization entirely, even though that roster entry's isActive is false.
ROSTER_INACTIVE_CODES = {"RL", "RET", "VL"}


def categorize_roster_status(code, is_active_entry, player_is_active):
    """Map a player's most recent roster entry to a status-pill category.

    `code` is `rosterEntries[0].status.code` (empty/None if the player has no
    roster history). `is_active_entry` is `rosterEntries[0].isActive` -- True
    means this roster relationship is still ongoing, False means it has ended
    (e.g. Released). `player_is_active` is the top-level API `active` flag,
    used only as a fallback when there is no roster history at all.

    Returns one of: "active", "injured", "restricted", "inactive", "other".
    """
    if not code:
        return "active" if player_is_active else "inactive"
    if is_active_entry:
        if code in ROSTER_INJURED_CODES:
            return "injured"
        if code in ROSTER_RESTRICTED_CODES:
            return "restricted"
        if code in ROSTER_OTHER_CODES:
            return "other"
        return "active"
    if code in ROSTER_INACTIVE_CODES:
        return "inactive"
    return "other"


# ── Active / retired decision ──

# Transactions whose description contains this keyword are national-team
# call-ups (e.g. the WBC) that MLB records in its transaction feed even for
# players who have left the affiliated MLB/MiLB system.  They must NOT count
# as affiliated activity when deciding whether a player is still active.
NATIONAL_TEAM_KEYWORD = "chinese taipei"


def is_national_team_tx(tx) -> bool:
    """True if *tx* is a national-team (Chinese Taipei) call-up, not real
    affiliated-system activity."""
    return NATIONAL_TEAM_KEYWORD in str(tx.get("description", "")).lower()


def is_active_player(player, stats, year: int) -> bool:
    """Decide whether *player* still counts as active for *year*.

    Active ⇔ the player has at least one ``season_stats`` row for *year*
    **OR** has a *qualifying* transaction dated within *year*.  National-team
    call-ups (see :func:`is_national_team_tx`) are NOT qualifying: a player
    whose only *year* transactions are Chinese Taipei selections — and who has
    no *year* season_stats — has left the affiliated system and is surfaced on
    the ``/retired`` page.  (A real season_stats row always keeps them active,
    so genuine MiLB players who were also called up stay on the index.)
    """
    if any(s.year == year for s in stats):
        return True
    for tx in (player.transactions_json or []):
        tx_date = parse_date(tx.get("date"))
        if tx_date and tx_date.year == year and not is_national_team_tx(tx):
            return True
    return False
