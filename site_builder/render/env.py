"""Jinja2 environment configuration for static site generation.

URL strategy: 站內連結是以 *base_url* 為前綴的 absolute-path URL
（GitHub Pages 子路徑部署傳 "/repo/"）；canonical/sitemap 等對外網址一律以
*site_url* 為前綴。兩者在 CI 都來自 actions/configure-pages，見 docs/custom_domain.md。
"""

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..constants import (
    PITCH_GROUP_TOOLTIP,
    PITCH_TAG_CSS,
    PITCH_TYPE_DISPLAY,
    SITE_URL,
    TEMPLATE_DIR,
)
from ..levels import COMBINED_LEVEL, is_mlb, level_display, level_label
from .filters import (
    default_if_none,
    floatformat,
    jsonld,
    num_dash,
    pct_fmt,
    pitch_legend,
    tojson_safe,
)
from .urls import (
    RETIRED_INDEX_PATH,
    headshot_cdn_urls,
    make_absolute_url,
    make_url_helpers,
    normalize_base_url,
)


def create_jinja_env(
    template_dir=None,
    base_url="/",
    site_url=SITE_URL,
):
    """Create and return a configured Jinja2 Environment."""
    tpl_dir = template_dir or str(TEMPLATE_DIR)

    base_url = normalize_base_url(base_url)
    page_url, player_url, retired_player_url, static_url = make_url_helpers(base_url)
    site_root, absolute_url = make_absolute_url(site_url)

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
    env.filters["level_label"] = level_label

    env.globals["is_mlb"] = is_mlb
    env.globals["COMBINED_LEVEL"] = COMBINED_LEVEL
    env.globals["pitch_legend"] = pitch_legend
    env.globals["page_url"] = page_url
    env.globals["RETIRED_INDEX_PATH"] = RETIRED_INDEX_PATH
    env.globals["player_url"] = player_url
    env.globals["retired_player_url"] = retired_player_url
    env.globals["static_url"] = static_url
    env.globals["headshot_cdn_urls"] = headshot_cdn_urls
    env.globals["absolute_url"] = absolute_url
    env.globals["base_url"] = base_url
    env.globals["site_url"] = site_root
    env.globals["pitch_type_display"] = PITCH_TYPE_DISPLAY
    env.globals["pitch_tag_css"] = PITCH_TAG_CSS
    env.globals["pitch_group_tooltip"] = PITCH_GROUP_TOOLTIP

    return env
