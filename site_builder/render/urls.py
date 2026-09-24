"""URL factories for templates and structured data.

站內每種頁面的路徑只在這裡定義一次（相對網站根目錄、無開頭斜線、有結尾斜線），
連結（``make_url_helpers``）、canonical/sitemap（``make_absolute_url``）與
寫檔位置（``out_dir / path / "index.html"``）都由同一個路徑推導，改網址結構
只改這裡。
"""

from urllib.parse import urljoin

# 已離隊球員列表頁；退役球員頁也建在它底下（見 player_page_path）
RETIRED_INDEX_PATH = "retired/"

# MLB Photos (Cloudinary-backed) headshot CDN. Photos are split into two
# asset families that don't overlap: "67" is the MLB-roster headshot (set the
# day a player gets an official MLB photo day), "milb" is the MiLB-roster
# headshot (set via MiLB's own media pipeline). A player only ever has one of
# the two until they cross levels for the first time, so callers must try
# both — see `headshot_cdn_urls`.
HEADSHOT_CDN_TEMPLATE_MLB = (
    "https://img.mlbstatic.com/mlb-photos/image/upload/"
    "w_180,q_auto:best/v1/people/{mlb_id}/headshot/67/current"
)
HEADSHOT_CDN_TEMPLATE_MILB = (
    "https://img.mlbstatic.com/mlb-photos/image/upload/"
    "w_180,q_auto:best/v1/people/{mlb_id}/headshot/milb/current"
)


def headshot_cdn_urls(mlb_id, latest_level_is_mlb):
    """Return (primary, secondary) headshot CDN URLs, ordered by which tier
    holds the most recently updated photo for this player.

    ``latest_level_is_mlb`` should reflect the highest level the player
    actually appeared in during their most recent season with game action —
    not just "ever reached MLB" — since that's the tier MLB most recently had
    a reason to refresh. A player demoted back to MiLB, for example, should
    try the MiLB tier first even though they have an old MLB-tier photo too.
    """
    mlb_url = HEADSHOT_CDN_TEMPLATE_MLB.format(mlb_id=mlb_id)
    milb_url = HEADSHOT_CDN_TEMPLATE_MILB.format(mlb_id=mlb_id)
    return (mlb_url, milb_url) if latest_level_is_mlb else (milb_url, mlb_url)


def player_page_path(mlb_id, is_retired: bool = False) -> str:
    """球員頁相對網站根目錄的路徑；退役球員頁放在 RETIRED_INDEX_PATH 底下。"""
    prefix = RETIRED_INDEX_PATH if is_retired else ""
    return f"{prefix}player/{mlb_id}/"


def normalize_base_url(base_url: str) -> str:
    """站內連結前綴統一成 ``/…/``；空字串（configure-pages 的 base_path）視為 ``/``。"""
    base_url = "/" + base_url.strip("/")
    return base_url if base_url == "/" else base_url + "/"


def make_url_helpers(base_url: str):
    """回傳綁定 ``base_url`` 的站內連結 closure：
    ``(page_url, player_url, retired_player_url, static_url)``。"""
    base = base_url.rstrip("/")

    def page_url(path=""):
        return f"{base}/{path}"

    def player_url(mlb_id):
        return page_url(player_page_path(mlb_id))

    def retired_player_url(mlb_id):
        return page_url(player_page_path(mlb_id, is_retired=True))

    def static_url(path):
        return page_url(f"static/{path}")

    return page_url, player_url, retired_player_url, static_url


def make_absolute_url(site_url: str):
    """以網站正式網址（如 ``SITE_URL``）建立絕對 URL closure，回 ``(site_root, absolute_url)``。"""
    site_root = site_url.rstrip("/") + "/"

    def absolute_url(path=""):
        return urljoin(site_root, str(path).lstrip("/"))

    return site_root, absolute_url
