"""Data synchronization: fetch from external APIs and store in SQLite.

Submodules:
    players     — Pipeline A: profile / season stats / game logs sync
    statcast    — Pipeline B: play-by-play fetch + Statcast aggregation
    extract     — pitch extraction from live-feed JSON (defines the pitch
                  dict schema cached in game_logs.pitches_json)
    field_maps  — MLB Stats API field → local column-name mappings

Public entry points are re-exported here so callers can simply
``from site_builder.sync import sync_database``.
"""

from .players import sync_database, update_database  # noqa: F401
from .statcast import sync_statcast  # noqa: F401
