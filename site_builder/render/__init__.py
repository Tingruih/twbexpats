"""Static-site rendering (SQLite → Jinja2 → HTML).

Submodules:
    env       — Jinja2 environment factory
    filters   — custom Jinja2 filters
    urls      — URL factories (player/static/absolute, headshot CDN)
    seo       — site metadata, structured data, sitemap/robots
    pitch_log — per-game pitch-log JSON payloads
    pages     — the build_static_site entry point
"""

from .pages import build_static_site  # noqa: F401
