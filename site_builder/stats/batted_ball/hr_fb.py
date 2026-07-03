"""HR/FB% — home runs per fly ball."""

from ...util.numbers import ratio


def compute_hr_fb_pct(pa_final: list[dict], fb_count: int):
    hr = sum(1 for p in pa_final if p.get("pa_event") == "home_run")
    return ratio(hr, fb_count)
