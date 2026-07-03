"""Exit velocity — average, maximum, and 90th-percentile EV over BBEs."""

from ...util.numbers import mean_round


def compute_avg_ev(bbe_ev: list[dict]):
    return mean_round([p["ev"] for p in bbe_ev], 1)


def compute_max_ev(bbe_ev: list[dict]):
    if not bbe_ev:
        return None
    return round(max(p["ev"] for p in bbe_ev), 1)


def compute_ev90(bbe_ev: list[dict]):
    """90th percentile EV: the single value below which 90% of BBEs fall.

    此部分若樣本數小於 10 顆 BBE，算出數據會與 TJStats 不符。
    """
    ev_values = sorted(p["ev"] for p in bbe_ev)  # ascending for percentile
    if not ev_values:
        return None
    idx = min(int(len(ev_values) * 0.9), len(ev_values) - 1)
    return round(ev_values[idx], 1)
