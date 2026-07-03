"""Chart payload builders (Pitch Plinko, pitch movement).

Each module owns one chart: a ``compute_*`` function building the per-level
payload from cached pitches (sync time) and a ``combine_*`` function merging
multiple levels for the season summary row (build time).
"""
