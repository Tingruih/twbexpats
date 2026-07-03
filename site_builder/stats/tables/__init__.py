"""Per-pitch-type table builders.

Each module owns one table: a ``compute_*`` function that builds the
per-level payload from cached pitches (sync time), and a ``combine_*``
function that merges multiple levels' payloads into the season summary row
(build time).
"""
