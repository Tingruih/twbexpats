"""SQLite persistence layer.

Submodules:
    schema        — table creation and forward migrations
    season_stats  — season_stats row load/save helpers
    players       — player-table queries (orphan detection)
    game_logs     — game_logs pitch-cache queries
    play_videos   — play-video cache queries
    bundles       — full player bundle loading for the site build

Plain row access only: every module here reads and writes tables, and none
of them fetches from an external source. The league-constant caches
(league_fip_constants, tjstats_park_factors, tjstats_league_constants) are
read and written by ``site_builder.league_constant`` instead, because doing
so means fetching from an API and computing a stat — their CREATE statements
still live in ``schema.py`` with every other table.
"""
