"""URL factories for templates and structured data."""

from urllib.parse import urljoin

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


def make_url_helpers(base_url: str):
    base = base_url.rstrip("/")

    def player_url(mlb_id):
        return f"{base}/player/{mlb_id}/"

    def retired_player_url(mlb_id):
        return f"{base}/retired/player/{mlb_id}/"

    def static_url(path):
        return f"{base}/static/{path}"

    return player_url, retired_player_url, static_url


def make_absolute_url(site_origin: str, base_url: str):
    site_root = urljoin(site_origin.rstrip("/") + "/", base_url.lstrip("/"))

    def absolute_url(path=""):
        return urljoin(site_root, str(path).lstrip("/"))

    return site_root, absolute_url
