"""WordPress "The Events Calendar" REST API adapter.

Why not `feed_url: /events/?ical=1`, which this project already uses for three Tribe sites: the
plugin's iCal export collapses a recurring series to its NEXT occurrence only. Mosaic District's
Holiday Village Market runs four weekends and Santa sits for six Saturdays; the .ics carries one
of each (16 VEVENTs where the API has 38 instances over the same window). So any Tribe site whose
events repeat wants this adapter instead. Vanish, Flying Ace and Historic Manassas stay on
`feed_url` because their listings are one-offs and an .ics needs no code.

Each instance is its own post with its own id, so uids are stable and recurrences need no RRULE.

Config:
    source:
      type: tribe_json
      url: https://mosaicdistrict.com      # site root; the wp-json path is appended
      days_back: 30                        # optional
      days_ahead: 270                      # optional
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from eventnews.model import Event, Feed
from eventnews.text import html_to_text

log = logging.getLogger(__name__)
USER_AGENT = "Mozilla/5.0 (compatible; eventnews/0.1; +https://github.com/SC0RCHR/local-calendars)"
API_PATH = "/wp-json/tribe/events/v1/events"
PER_PAGE = 50
MAX_PAGES = 12


def fetch(url: str, days_back: int = 30, days_ahead: int = 270, session: requests.Session | None = None,
          today: date | None = None) -> list[dict]:
    """Every event instance in [today - days_back, today + days_ahead], across pages."""
    sess = session or requests.Session()
    today = today or date.today()
    api = url.rstrip("/") + API_PATH
    params = {
        "per_page": PER_PAGE,
        "status": "publish",
        "start_date": (today - timedelta(days=days_back)).isoformat(),
        "end_date": (today + timedelta(days=days_ahead)).isoformat(),
    }
    out: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        resp = sess.get(api, params={**params, "page": page},
                        headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        events = payload.get("events") or []
        out.extend(events)
        if len(events) < PER_PAGE or page >= int(payload.get("total_pages") or 1):
            break
    return out


def parse_events(events: list[dict], feed: Feed) -> list[Event]:
    out: list[Event] = []
    for item in events:
        try:
            out.append(_parse_item(item, feed))
        except Exception as exc:
            log.warning("skipping event %s (%s): %s", item.get("id"), item.get("title"), exc)
    return out


def _parse_item(item: dict, feed: Feed) -> Event:
    tz = _zone(item.get("timezone"), feed.timezone)
    all_day = str(item.get("all_day", "")).lower() in {"true", "1", "yes"}
    start = _naive(item["start_date"])
    end = _naive(item.get("end_date") or item["start_date"])

    if all_day:
        start, end = start.date(), end.date() + timedelta(days=1)   # DTEND is exclusive
    else:
        start, end = start.replace(tzinfo=tz), end.replace(tzinfo=tz)
        if end <= start:
            end = start + timedelta(minutes=feed.default_duration_minutes)

    venue = item.get("venue") or {}
    place = venue.get("venue") if isinstance(venue, dict) else ""
    address = ", ".join(str(venue.get(k) or "") for k in ("address", "city", "state") if venue.get(k)) if isinstance(venue, dict) else ""
    location = ", ".join(p for p in (place, address) if p) or feed.location

    url = str(item.get("url") or feed.url)
    body = html_to_text(str(item.get("description") or item.get("excerpt") or ""))
    cost = str(item.get("cost") or "").strip()
    description = "\n\n".join(p for p in (body, f"Cost: {cost}" if cost else "", f"Details: {url}") if p)

    image = item.get("image") or {}
    return Event(
        uid=f"{item['id']}@{feed.slug}",
        summary=html_to_text(str(item.get("title") or "(untitled)")).strip() or "(untitled)",
        start=start,
        end=end,
        all_day=all_day,
        description=description,
        location=location,
        url=url,
        categories=[str(c.get("name")) for c in (item.get("categories") or []) if c.get("name")]
                   + [str(t.get("name")) for t in (item.get("tags") or []) if t.get("name")],
        image=str(image.get("url") or "") if isinstance(image, dict) else "",
    )


def _naive(value: str) -> datetime:
    """Tribe writes local wall-clock time with no offset: "2026-11-21 11:00:00"."""
    return datetime.fromisoformat(str(value).strip().replace(" ", "T")[:19]).replace(tzinfo=None)


def _zone(name: str | None, fallback: str) -> ZoneInfo:
    try:
        return ZoneInfo(str(name)) if name else ZoneInfo(fallback)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(fallback)
