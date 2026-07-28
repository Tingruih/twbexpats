"""Chart payload builders (Pitch Plinko, pitch movement).

Each module owns one chart via a ``compute_*`` function building the payload
from a pitch list.  The same function serves both the per-level payloads
(sync time, one level's pitches) and a year's cross-level total (build time,
every level's pitches pooled) — there is no separate combining algorithm to
keep in step.
"""
