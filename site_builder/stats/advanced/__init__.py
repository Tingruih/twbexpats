"""Advanced stats needing league constants or external data — one stat per file.

Every constant these formulas need arrives as a function argument; the
fetching and caching lives in ``site_builder.league_constant``. The one
exception is the fixed weights in ``site_builder.constants`` §3 (wOBA linear
weights, WOBA_SCALE), which are formula constants and do not vary by league
or season.
"""
