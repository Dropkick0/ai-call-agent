"""Google Calendar helper module.

Provides authentication using a service account and utility functions
for querying free time slots and creating events.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import List, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
_SERVICE = None


def _load_credentials() -> service_account.Credentials:
    """Load service account credentials from ``GOOGLE_CRED_JSON`` env var."""
    cred_json = os.getenv("GOOGLE_CRED_JSON")
    if not cred_json:
        raise ValueError("GOOGLE_CRED_JSON environment variable not set")

    # The variable may be a path to a JSON file or the JSON itself
    if os.path.isfile(cred_json):
        with open(cred_json, "r", encoding="utf-8") as f:
            info = json.load(f)
    else:
        info = json.loads(cred_json)

    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def get_service():
    """Return an authenticated Calendar API service instance."""
    global _SERVICE
    if _SERVICE is None:
        creds = _load_credentials()
        _SERVICE = build("calendar", "v3", credentials=creds)
    return _SERVICE


def _parse_google_dt(value: str) -> datetime:
    """Parse RFC3339 timestamps returned by Google."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def list_free_slots(
    calendar_id: str,
    start: datetime,
    end: datetime,
    *,
    slot_minutes: int = 30,
) -> List[Tuple[datetime, datetime]]:
    """Return a list of free time slots between ``start`` and ``end``.

    Parameters
    ----------
    calendar_id: str
        ID of the calendar to query.
    start, end: datetime
        Range to search for free time. Expected to be timezone-aware.
    slot_minutes: int
        Length of each suggested slot in minutes.
    """

    service = get_service()
    body = {
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "items": [{"id": calendar_id}],
    }
    response = service.freebusy().query(body=body).execute()
    busy_periods = response["calendars"][calendar_id].get("busy", [])
    busy_periods = [
        ( _parse_google_dt(p["start"]), _parse_google_dt(p["end"]) )
        for p in busy_periods
    ]
    slots = []
    slot_delta = timedelta(minutes=slot_minutes)
    current = start
    idx = 0
    while current + slot_delta <= end:
        slot_end = current + slot_delta
        # Advance through busy periods that end before this slot
        while idx < len(busy_periods) and busy_periods[idx][1] <= current:
            idx += 1
        if idx < len(busy_periods) and busy_periods[idx][0] < slot_end and busy_periods[idx][1] > current:
            current = busy_periods[idx][1]
            continue
        slots.append((current, slot_end))
        current += slot_delta
    return slots


def create_event(
    calendar_id: str,
    start: datetime,
    end: datetime,
    summary: str,
) -> dict:
    """Create a calendar event and return the API response."""
    service = get_service()
    body = {
        "summary": summary,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    return service.events().insert(calendarId=calendar_id, body=body).execute()


