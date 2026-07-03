"""Launch angle — average LA over batted balls with LA data."""

from ...util.numbers import mean_round


def compute_avg_la(la_values: list):
    return mean_round(la_values, 1)
