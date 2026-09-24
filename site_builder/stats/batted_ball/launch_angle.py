"""Launch angle — average LA over batted balls with LA data."""

from ...util.numbers import mean_round


def collect_la_values(in_play: list[dict]) -> list[float]:
    """有 launch angle 的擊球仰角清單，是 avg LA 與 SwSp% 共用的分母樣本。

    MiLB 部分擊球沒有 hitData.launchAngle（``la`` 為 None），不能算進分母。
    """
    return [p["la"] for p in in_play if p.get("la") is not None]


def compute_avg_la(la_values: list):
    return mean_round(la_values, 1)
