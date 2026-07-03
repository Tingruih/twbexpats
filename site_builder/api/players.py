"""Player profile endpoint."""

import logging

from ..levels import sport_id_to_code
from .client import BASE_URL, get_json

logger = logging.getLogger(__name__)


def get_player_profile(mlb_id: int) -> dict:
    """
    api endpoint: /people/{mlb_id}?hydrate=transactions,rosterEntries,currentTeam

    回傳 dict :  mlb_id
                full_name (英文名字)
                position (位置)
                height (身高)
                weight (體重)
                birth_date (出生日期)
                birth_city (出生城市)
                birth_country (出生國家)
                is_active (active定義為只要還在名單上，不論有無受傷或被下放都算active)
                bat_side (打擊慣用手)
                pitch_hand (投球慣用手)
                latest_transaction (最新交易)
                transactions_json (list of dicts with date, type, description)
                roster_status (rosterEntries[0] 的 status description，反映球員最新狀態，
                                e.g. "Active", "Released", "Injured 60-Day" 等)
                roster_status_code (rosterEntries[0] 的 status code，e.g. "A", "RL", "D60")
                roster_is_active (rosterEntries[0].isActive：該筆名單關係目前是否仍在生效)
                team_id (球隊 ID)
                current_team_name (目前球隊名稱)
                current_team_level (球隊等級，如 MLB, AAA, AA 等)
    """
    url = f"{BASE_URL}/people/{mlb_id}?hydrate=transactions,rosterEntries,currentTeam"
    people = get_json(url).get("people", [])
    if not people:
        return {}

    p = people[0]

    # Transactions (most recent first)
    transactions = p.get("transactions", [])
    latest_tx = ""
    tx_list = []
    if transactions:
        sorted_tx = sorted(transactions, key=lambda t: t.get("date", ""), reverse=True)
        latest_tx = sorted_tx[0].get("description", "") if sorted_tx else ""
        for tx in sorted_tx:
            tx_list.append(
                {
                    "date": tx.get("effectiveDate") or tx.get("date", ""),
                    "type": tx.get("typeDesc", ""),
                    "description": tx.get("description", ""),
                }
            )

    # Most recent roster status (rosterEntries[0] is the latest entry,
    # regardless of whether it is still active -- e.g. "Released" entries
    # have isActive=False but are still the player's current status).
    roster_status = ""
    roster_status_code = ""
    roster_is_active = False
    roster_entries = p.get("rosterEntries", [])
    if roster_entries:
        entry = roster_entries[0]
        status = entry.get("status", {})
        roster_status = status.get("description", "")
        roster_status_code = status.get("code", "")
        roster_is_active = bool(entry.get("isActive", False))

    # Team info and level
    current_team = p.get("currentTeam", {})
    team_id = current_team.get("id")
    current_team_name = current_team.get("name", "")
    current_team_level = ""

    if team_id:
        try:
            t_data = get_json(f"{BASE_URL}/teams/{team_id}").get("teams", [])
            if t_data:
                sport_id = t_data[0].get("sport", {}).get("id")
                current_team_level = sport_id_to_code(sport_id)
        except Exception as e:
            logger.warning("Failed to fetch team level for team_id=%s: %s", team_id, e)

    return {
        "mlb_id": p.get("id"),
        "full_name": p.get("fullName", ""),
        "position": p.get("primaryPosition", {}).get("abbreviation", ""),
        "height": p.get("height", ""),
        "weight": p.get("weight"),
        "birth_date": p.get("birthDate"),
        "birth_city": p.get("birthCity", ""),
        "birth_country": p.get("birthCountry", ""),
        "is_active": p.get("active", True),
        "bat_side": p.get("batSide", {}).get("description", ""),
        "pitch_hand": p.get("pitchHand", {}).get("description", ""),
        "latest_transaction": latest_tx,
        "transactions_json": tx_list,
        "roster_status": roster_status,
        "roster_status_code": roster_status_code,
        "roster_is_active": roster_is_active,
        "team_id": team_id,
        "current_team_name": current_team_name,
        "current_team_level": current_team_level,
    }
