"""Per-pitch-type table builders.

Each module owns one table via a ``compute_*`` function that builds the
payload from a pitch list.  The same function serves both the per-level rows
(sync time, one level's pitches) and a year's cross-level total (build time,
every level's pitches pooled) — there is no separate combining algorithm to
keep in step.
"""
