"""規則式 delta chips 與中文重點摘要（門檻見 plan §0.6）。"""

# ── 門檻 ──
VELO_THRESHOLD = 0.5          # mph
VELO_MIN_COUNT = 5            # 該球種週球數
USAGE_THRESHOLD = 0.05        # 5pp
USAGE_MIN_PITCHES = 30        # 週總球數
RATE_THRESHOLD = 0.03         # whiff/chase/zone/csw 3pp
RATE_MIN_DEN = 20
EV_THRESHOLD = 2.0            # mph
EV_MIN_BBE = 5
HARD_HIT_THRESHOLD = 0.08
FSTRIKE_THRESHOLD = 0.05
MAX_NOTES = 4

# (delta 鍵, 中文標籤, 單位, 門檻, 投手方向好?, 打者方向好?)
# 方向好? = delta 為「正」時是否為好事；None = 中性。
_RATE_SPECS = (
    ("whiff_pct", "Whiff%", "pp", RATE_THRESHOLD, True, False),
    ("o_swing_pct", "Chase%", "pp", RATE_THRESHOLD, True, False),
    ("zone_pct", "Zone%", "pp", RATE_THRESHOLD, None, None),
    ("csw_pct", "CSW%", "pp", RATE_THRESHOLD, True, None),
    ("swstr_pct", "SwStr%", "pp", RATE_THRESHOLD, True, False),
    ("z_contact_pct", "Z-Contact%", "pp", RATE_THRESHOLD, False, True),
    ("avg_ev", None, "mph", EV_THRESHOLD, False, True),
    ("hard_hit_pct", None, "pp", HARD_HIT_THRESHOLD, False, True),
)
_EV_LABELS = {"pitcher": "被打 EV", "batter": "平均 EV"}
_HH_LABELS = {"pitcher": "被 Hard-Hit%", "batter": "Hard-Hit%"}


def _fmt_delta(delta: float, unit: str) -> str:
    if unit == "pp":
        return f"{delta * 100:+.0f}pp"
    return f"{delta:+.1f} {unit}"


def _fmt_value(value, unit: str) -> str:
    if value is None:
        return "-"
    if unit == "pp":
        return f"{value * 100:.0f}%"
    return f"{value:.1f}"


def _chip(label, week_value, delta, unit, positive_is_good):
    good = None if positive_is_good is None else (
        (delta > 0) == positive_is_good
    )
    return {
        "label": label,
        "value_str": _fmt_value(week_value, unit),
        "delta_str": _fmt_delta(delta, unit),
        "cls": "up" if delta > 0 else "down",
        "good": bool(good) if good is not None else True,
        "_score": abs(delta),
    }


def build_chips(report: dict, role: str) -> list[dict]:
    if not report.get("season_available"):
        return []
    deltas = report.get("deltas") or {}
    week = report.get("week") or {}
    pitch_count = report.get("pitch_count") or 0
    chips: list[dict] = []

    # 球種 velo / usage（投手才有 arsenal deltas）
    for row in deltas.get("arsenal") or []:
        vd = row.get("velo_delta")
        if vd is not None and abs(vd) >= VELO_THRESHOLD \
                and row.get("count", 0) >= VELO_MIN_COUNT:
            chips.append(_chip(f"{row['type']} 均速", row.get("week_velo"),
                               vd, "mph", True))
        ud = row.get("usage_delta")
        if ud is not None and abs(ud) >= USAGE_THRESHOLD \
                and pitch_count >= USAGE_MIN_PITCHES:
            chips.append(_chip(f"{row['type']} 使用率", row.get("week_pct"),
                               ud, "pp", None))

    # 率值
    bbe = week.get("bbe") or 0
    for key, label, unit, threshold, p_good, b_good in _RATE_SPECS:
        entry = (deltas.get("discipline") or {}).get(key)
        if not entry or entry.get("delta") is None:
            continue
        delta = entry["delta"]
        if abs(delta) < threshold:
            continue
        if key in ("avg_ev", "hard_hit_pct"):
            if bbe < EV_MIN_BBE:
                continue
            label = (_EV_LABELS if key == "avg_ev" else _HH_LABELS)[role]
        elif pitch_count < RATE_MIN_DEN:
            continue
        positive_is_good = p_good if role == "pitcher" else b_good
        chips.append(_chip(label, entry.get("week"), delta, unit,
                           positive_is_good))

    chips.sort(key=lambda c: -c["_score"])
    for c in chips:
        c.pop("_score", None)
    return chips


def build_notes(report: dict, role: str) -> list[str]:
    notes: list[str] = []
    deltas = report.get("deltas") or {}
    for row in deltas.get("arsenal") or []:
        if row.get("is_new"):
            notes.append(f"新球種：{row['name']}（本週 {row['count']} 球）")
        elif row.get("is_dropped"):
            season_pct = (row.get("season_pct") or 0) * 100
            notes.append(f"棄用球種：{row['name']}（季使用率 {season_pct:.0f}%，本週 0 球）")
        elif row.get("usage_delta") is not None \
                and abs(row["usage_delta"]) >= USAGE_THRESHOLD \
                and row.get("season_pct"):
            notes.append(
                f"{row['name']} 使用率 {row['season_pct'] * 100:.0f}% → "
                f"{row['week_pct'] * 100:.0f}%"
            )
    for chip in build_chips(report, role):
        if len(notes) >= MAX_NOTES:
            break
        line = f"{chip['label']} {chip['value_str']}（{chip['delta_str']}）"
        if line not in notes:
            notes.append(line)
    return notes[:MAX_NOTES]
