"""schema.org Event blocks (`<script type="application/ld+json">`) read off an events page.

Middleburg's visitor site runs Modern Events Calendar, which publishes no iCal and registers no
REST route (`/wp-json/mec/v1/events` answers an empty list, and the `mec-events` post type
exposes none of MEC's dates, which live in its own tables). What the page does emit, per event,
is a schema.org Event with real start/end timestamps, the blurb, the venue and the poster - so
that is what we read.

The blocks cover only what the page renders, about a week ahead, and MEC's list view takes no
month parameter (`?mec_month=` and friends change nothing). Pair this with `accumulate: true`:
each run folds the newly-visible week into the published feed, so the season builds up instead
of the calendar never seeing past next Sunday.

Config:
    source:
      type: jsonld
      url: https://visitmiddleburgva.com/local-events/
"""

from __future__ import annotations

import html as htmllib
import json
import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from eventnews.model import Event, Feed
from eventnews.text import html_to_text, slugify

log = logging.getLogger(__name__)
USER_AGENT = "Mozilla/5.0 (compatible; eventnews/0.1; +https://github.com/SC0RCHR/local-calendars)"
_SCRIPTS = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)


def fetch(url: str, session: requests.Session | None = None) -> str:
    sess = session or requests.Session()
    resp = sess.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}, timeout=40)
    resp.raise_for_status()
    return resp.text


def find_events(page: str) -> list[dict]:
    """Every Event node in the page's JSON-LD, including inside an @graph."""
    out: list[dict] = []
    for block in _SCRIPTS.findall(page or ""):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        out.extend(node for node in _walk(data) if _is_event(node))
    return out


def _walk(data):
    if isinstance(data, list):
        for item in data:
            yield from _walk(item)
    elif isinstance(data, dict):
        yield data
        for key in ("@graph", "itemListElement", "subEvent"):
            if key in data:
                yield from _walk(data[key])


def _is_event(node) -> bool:
    types = node.get("@type") if isinstance(node, dict) else None
    types = types if isinstance(types, list) else [types]
    return any("event" in str(t).lower() for t in types) and bool(node.get("startDate"))


def parse_events(page: str, feed: Feed) -> list[Event]:
    tz = ZoneInfo(feed.timezone)
    out: list[Event] = []
    seen: set[str] = set()
    for node in find_events(page):
        try:
            ev = _parse_node(node, feed, tz)
        except Exception as exc:
            log.warning("skipping jsonld event %s: %s", str(node.get("name"))[:60], exc)
            continue
        if ev.uid in seen:
            continue
        seen.add(ev.uid)
        out.append(ev)
    return out


def _parse_node(node: dict, feed: Feed, tz: ZoneInfo) -> Event:
    title = htmllib.unescape(str(node.get("name") or "(untitled)")).strip()
    start, start_all_day = _when(node["startDate"], tz)
    end, end_all_day = _when(node.get("endDate") or node["startDate"], tz)
    all_day = start_all_day and end_all_day

    if all_day:
        end = end + timedelta(days=1)                   # schema.org endDate is inclusive
    else:
        if start_all_day != end_all_day:                # mixed: trust the start
            start, end = _as_datetime(start, tz), _as_datetime(end, tz)
        if end <= start:
            end = start + timedelta(minutes=feed.default_duration_minutes)

    loc = node.get("location") if isinstance(node.get("location"), dict) else {}
    location = ", ".join(str(loc.get(k)).strip() for k in ("name", "address") if _text(loc.get(k))) or feed.location
    url = _text(node.get("url")) or _text((node.get("offers") or {}).get("url") if isinstance(node.get("offers"), dict) else "") or feed.url
    body = html_to_text(str(node.get("description") or ""))
    description = "\n\n".join(p for p in (body, f"Details: {url}") if p)

    image = node.get("image")
    if isinstance(image, dict):
        image = image.get("url")
    elif isinstance(image, list):
        image = next((i for i in image if isinstance(i, str)), "")

    start_key = (start.date() if isinstance(start, datetime) else start).isoformat()
    return Event(
        uid=f"{slugify(title)[:60]}-{start_key}@{feed.slug}",
        summary=title,
        start=start,
        end=end,
        all_day=all_day,
        description=description,
        location=location,
        url=url,
        categories=[],
        image=str(image or ""),
    )


def _when(value, tz: ZoneInfo) -> tuple[datetime | date, bool]:
    """(when, is_all_day). "2026-11-20T09:30:00-05:00" -> aware datetime; "2026-09-24" -> date."""
    text = str(value).strip()
    if len(text) <= 10:
        return date.fromisoformat(text), True
    parsed = datetime.fromisoformat(text)
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)), False


def _as_datetime(when: datetime | date, tz: ZoneInfo) -> datetime:
    if isinstance(when, datetime):
        return when
    return datetime.combine(when, datetime.min.time(), tzinfo=tz)


def _text(value) -> str:
    return str(value).strip() if isinstance(value, str) and value.strip() else ""
