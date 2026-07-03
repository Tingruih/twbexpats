"""Jinja2 environment configuration for static site generation.

URL strategy: all URLs are absolute-path URLs rooted at *base_url*.
For GitHub Pages sub-path deployment, pass base_url="/repo/".
"""

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..constants import TEMPLATE_DIR
from ..levels import is_mlb, level_display
from .filters import (
    default_if_none,
    floatformat,
    jsonld,
    num_dash,
    pct_fmt,
    tojson_safe,
)
from .urls import headshot_cdn_urls, make_absolute_url, make_url_helpers


def create_jinja_env(
    template_dir=None,
    base_url="/",
    site_origin="https://tingruih.github.io",
):
    """Create and return a configured Jinja2 Environment."""
    tpl_dir = template_dir or str(TEMPLATE_DIR)

    if not base_url.startswith("/"):
        base_url = "/" + base_url
    if not base_url.endswith("/"):
        base_url = base_url + "/"

    player_url, retired_player_url, static_url = make_url_helpers(base_url)
    site_url, absolute_url = make_absolute_url(site_origin, base_url)

    env = Environment(
        loader=FileSystemLoader(tpl_dir),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    env.filters["floatformat"] = floatformat
    env.filters["default_if_none"] = default_if_none
    env.filters["num_dash"] = num_dash

    env.filters["tojson_safe"] = tojson_safe
    env.filters["jsonld"] = jsonld
    env.filters["pct_fmt"] = pct_fmt
    env.filters["level_display"] = level_display

    env.globals["is_mlb"] = is_mlb
    env.globals["player_url"] = player_url
    env.globals["retired_player_url"] = retired_player_url
    env.globals["static_url"] = static_url
    env.globals["headshot_cdn_urls"] = headshot_cdn_urls
    env.globals["absolute_url"] = absolute_url
    env.globals["base_url"] = base_url
    env.globals["site_url"] = site_url
    env.globals["site_origin"] = site_origin.rstrip("/")

    return env
