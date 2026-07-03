"""Extension — average release extension (ft) over all pitches."""

from ...util.numbers import mean_round


def compute_avg_extension(pitches: list[dict]):
    return mean_round([p.get("extension") for p in pitches], 2)
