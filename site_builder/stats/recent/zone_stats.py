"""好球帶 per-zone 統計（zone 1–9 九宮格、11–14 外側象限）。

AVG 以 PA 終結球的 zone 歸區（Savant 熱區同法）；swing/whiff 對每球計。
"""

from ...constants import NON_PA_EVENTS
from ...util.numbers import ratio
from ..core.pitches import is_swing, is_whiff

HIT_EVENTS = frozenset({"single", "double", "triple", "home_run"})

# 計入打數（AB）的 PA 結果（安打 + 出局型 + 失誤/野選）；BB/HBP/犧牲不入。
AB_EVENTS = HIT_EVENTS | frozenset({
    "strikeout", "strikeout_double_play",
    "field_out", "force_out", "grounded_into_double_play",
    "double_play", "triple_play",
    "field_error", "fielders_choice", "fielders_choice_out",
    "batter_interference",
})

VALID_ZONES = tuple(range(1, 10)) + (11, 12, 13, 14)


def compute_zone_stats(pitches: list[dict]) -> dict[int, dict]:
    acc: dict[int, dict] = {}
    for p in pitches:
        zone = p.get("zone")
        if zone not in VALID_ZONES:
            continue
        cell = acc.setdefault(zone, {
            "n": 0, "swings": 0, "whiffs": 0, "ab": 0, "hits": 0,
        })
        cell["n"] += 1
        if is_swing(p):
            cell["swings"] += 1
        if is_whiff(p):
            cell["whiffs"] += 1
        event = p.get("pa_event") or ""
        if p.get("is_pa_final") and event and event not in NON_PA_EVENTS:
            if event in AB_EVENTS:
                cell["ab"] += 1
                if event in HIT_EVENTS:
                    cell["hits"] += 1
    for cell in acc.values():
        cell["swing_pct"] = ratio(cell["swings"], cell["n"], digits=6)
        cell["whiff_pct"] = ratio(cell["whiffs"], cell["swings"], digits=6)
        cell["avg"] = ratio(cell["hits"], cell["ab"], digits=3)
    return acc
