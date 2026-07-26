"""緩動曲線與插值工具。

所有鏡頭運動、淡入淡出、元素進場都經過這裡。刻意不提供線性緩動作為預設 ——
線性運動在視覺上像機器，起步與煞車都平滑的 cubic in-out 才符合真人操作的手感。
"""
from __future__ import annotations


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def linear(t: float) -> float:
    return clamp(t)


def ease_in_out_cubic(t: float) -> float:
    """主力曲線：起步慢、中段快、抵達前減速。用於絕大多數鏡頭運動。"""
    t = clamp(t)
    if t < 0.5:
        return 4 * t * t * t
    return 1 - pow(-2 * t + 2, 3) / 2


def ease_out_cubic(t: float) -> float:
    """快速進場後柔和停下。用於元素滑入。"""
    return 1 - pow(1 - clamp(t), 3)


def ease_in_cubic(t: float) -> float:
    """緩慢起步後加速離開。用於元素退場。"""
    t = clamp(t)
    return t * t * t


def ease_out_quint(t: float) -> float:
    """比 cubic 更強的煞車感。用於需要「啪」地定住的收尾。"""
    return 1 - pow(1 - clamp(t), 5)


def ease_out_back(t: float, overshoot: float = 1.70158) -> float:
    """帶輕微過衝再回彈。僅用於游標點擊的縮放回饋。"""
    t = clamp(t)
    c3 = overshoot + 1
    return 1 + c3 * pow(t - 1, 3) + overshoot * pow(t - 1, 2)


def smoothstep(t: float) -> float:
    """比 cubic in-out 更溫和的 S 曲線。用於不希望被察覺的 Ken Burns 呼吸。"""
    t = clamp(t)
    return t * t * (3 - 2 * t)


def sub_progress(t: float, start: float, end: float) -> float:
    """把整體進度 t 重新映射到 [start, end] 這個子區間的 0→1 進度。

    用來在一個片段內排程多個先後發生的動畫，例如字卡的 logo → 標題 → 副標。
    """
    if end <= start:
        return 1.0 if t >= end else 0.0
    return clamp((t - start) / (end - start))


def fade_in_out(t: float, fade_in: float, fade_out: float) -> float:
    """回傳 0→1→0 的不透明度包絡。

    `fade_in` / `fade_out` 皆為佔整段長度的比例。中段維持全不透明。
    """
    t = clamp(t)
    if fade_in > 0 and t < fade_in:
        return ease_out_cubic(t / fade_in)
    if fade_out > 0 and t > 1 - fade_out:
        return ease_in_cubic((1 - t) / fade_out)
    return 1.0


def bezier_point(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    """三次貝茲曲線取點。游標沿曲線而非直線移動，才有真人手感。"""
    t = clamp(t)
    u = 1 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return (
        a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
        a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
    )
