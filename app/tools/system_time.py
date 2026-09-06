"""System clock tool with an explicit timezone."""

from datetime import datetime
from zoneinfo import ZoneInfo


def current_time(timezone: str) -> dict[str, str]:
    """Return an ISO timestamp with UTC offset and IANA timezone."""
    return {"datetime": datetime.now(ZoneInfo(timezone)).isoformat(), "timezone": timezone}
