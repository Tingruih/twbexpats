"""Date parsing helpers and the site's display timezone."""

import datetime
from typing import Optional

# All user-facing timestamps on the site are rendered in Taiwan time.
TW_TZ = datetime.timezone(datetime.timedelta(hours=8))


def parse_date(text: Optional[str]):
    if not text:
        return None
    try:
        return datetime.date.fromisoformat(str(text)[:10])
    except ValueError:
        return None
