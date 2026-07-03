"""Site metadata, structured data (JSON-LD), and discovery files."""

from pathlib import Path
from xml.sax.saxutils import escape

from .urls import headshot_cdn_urls

SITE_TITLE = "TwbExpats | 台灣旅美棒球員 MLB/MiLB Stats Tracker"
SITE_DESCRIPTION = (
    "TwbExpats tracks 台灣旅美棒球員 / Taiwanese baseball players in MLB and MiLB, "
    "including game logs, pitching stats, batting stats, and advanced metrics."
)
SITE_SAME_AS = [
    "https://www.threads.com/@twbexpats",
    "https://github.com/Tingruih/twbexpats",
]

RETIRED_SEO_TITLE = "已離美職體系球員 / Retired Players | TwbExpats"
RETIRED_SEO_DESCRIPTION = (
    "TwbExpats 追蹤已結束旅美生涯的台灣棒球員 / Taiwanese baseball players "
    "who have left the MLB/MiLB system, with their career-combined stats "
    "and the highest level each player reached."
)


def player_display_name(player) -> str:
    if player.name_tw:
        return f"{player.name_tw} {player.name_en}"
    return player.name_en


def player_canonical_path(player, is_retired: bool = False) -> str:
    if is_retired:
        return f"retired/player/{player.mlb_id}/"
    return f"player/{player.mlb_id}/"


def player_description(player) -> str:
    role = "投球 / pitching" if player.is_pitcher else "打擊 / batting"
    level_team = " ".join(
        part for part in [player.level, player.team] if part and part != "N/A"
    )
    team_text = f"，目前效力於 / currently with {level_team}" if level_team else ""
    return (
        f"查看 {player_display_name(player)} 的 MLB/MiLB 年度成績 / season stats, "
        f"逐場紀錄 / game logs{team_text}, including {role} stats, "
        "advanced metrics, and transactions."
    )


def index_structured_data(absolute_url, player_data):
    site_url = absolute_url("")
    return [
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": "TwbExpats",
            "url": site_url,
            "description": SITE_DESCRIPTION,
            "inLanguage": "zh-Hant",
            "sameAs": SITE_SAME_AS,
        },
        {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": "台灣旅美棒球員列表 / Taiwanese Baseball Players List",
            "url": site_url,
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": idx,
                    "url": absolute_url(player_canonical_path(item["player"])),
                    "name": player_display_name(item["player"]),
                }
                for idx, item in enumerate(player_data, start=1)
            ],
        },
    ]


def player_structured_data(absolute_url, player, is_retired: bool = False):
    canonical_url = absolute_url(player_canonical_path(player, is_retired))
    breadcrumb_items = [
        {
            "@type": "ListItem",
            "position": 1,
            "name": "TwbExpats",
            "item": absolute_url(""),
        },
    ]
    if is_retired:
        breadcrumb_items.append({
            "@type": "ListItem",
            "position": 2,
            "name": "已離美職體系球員 / Retired Players",
            "item": absolute_url("retired/"),
        })
    breadcrumb_items.append({
        "@type": "ListItem",
        "position": len(breadcrumb_items) + 1,
        "name": player_display_name(player),
        "item": canonical_url,
    })
    return [
        {
            "@context": "https://schema.org",
            "@type": "Person",
            "name": player.name_tw or player.name_en,
            "alternateName": player.name_en,
            "url": canonical_url,
            "image": headshot_cdn_urls(player.mlb_id, player.latest_level_is_mlb)[0],
            "jobTitle": "棒球員 / Baseball player",
            "affiliation": player.team if player.team and player.team != "N/A" else None,
            "sameAs": [f"https://www.mlb.com/player/{player.mlb_id}"],
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": breadcrumb_items,
        },
    ]


def write_robots(out_dir: Path, sitemap_url: str):
    content = f"User-agent: *\nAllow: /\n\nSitemap: {sitemap_url}\n"
    (out_dir / "robots.txt").write_text(content, encoding="utf-8")


def write_sitemap(out_dir: Path, urls: list[dict]):
    entries = []
    for item in urls:
        loc = escape(item["loc"])
        lastmod = item.get("lastmod")
        lastmod_xml = f"\n    <lastmod>{escape(lastmod)}</lastmod>" if lastmod else ""
        entries.append(f"  <url>\n    <loc>{loc}</loc>{lastmod_xml}\n  </url>")

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    (out_dir / "sitemap.xml").write_text(xml, encoding="utf-8")
