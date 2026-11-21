"""Server-rendered event lists that carry their data in `data-event-*` attributes.

Village at Leesburg (and the other properties on the same mall CMS) render each listing as

    <div data-testid="event-list-item" data-event-id="8427" data-event-title="Daily Tree Shows"
         data-event-categories="event" data-href="/events/daily-tree-shows-4/"
         data-event-occurrences="[{"start":{"hour":"4","minutes":"0","ampm":"PM",
                                  "event_date":"2026-11-21"}, "end":{...}, "allday":"0"}, ...]">

so the dates are already structured and no JavaScript has to run. (CLAUDE.md used to say this
site was Wix and unreadable without a browser; it was rebuilt, and the markup above is what it
serves now. The per-event .ics link on a detail page is a `data:` URI holding one VEVENT, so it
is no better than this.)

Two caveats, both handled by `accumulate: true`:
  * each event lists only its next two occurrences ("upcoming_occurrences-0/1"), so a daily
    series shows up two days at a time and the published feed has to collect them;
  * the same item is rendered many times per page (list view, calendar grid, carousels) - 305
    copies of 8 events the day this was written - so items are deduped by (id, date).

Config:
    source:
      type: event_list
      url: https://www.villageatleesburg.com/events/
      routine: "bargain|football|friday night live"   # optional: titles to tag `routine`,
                                                      # which ranks last and never a Top Pick
"""

from __future__ import annotations

import html as htmllib
import json
import logging
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests

from eventnews.model import Event, Feed
from eventnews.text import html_to_text

log = logging.getLogger(__name__)
USER_AGENT = "Mozilla/5.0 (compatible; eventnews/0.1; +https://github.com/SC0RCHR/local-calendars)"
_ITEM = re.compile(r'data-testid="event-list-item"')
_ATTR = re.compile(r'data-(event-id|event-title|event-categories|event-occurrences|href)="([^"]*)"')
_DESCRIPTION = re.compile(r'class="event-description[^"]*"[^>]*>(.*?)</div>', re.S)
_IMG = re.compile(r'<img\s[^>]*src="([^"]+)"')


def fetch(url: str, session: requests.Session | None = None) -> str:
    sess = session or requests.Session()
    resp = sess.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}, timeout=40)
    resp.raise_for_status()
    return resp.text


def parse_events(page: str, feed: Feed) -> list[Event]:
    tz = ZoneInfo(feed.timezone)
    src = feed.source if isinstance(feed.source, dict) else next(
        (s for s in feed.sources if s.get("type") == "event_list"), {})
    base = str(src.get("url") or feed.url)
    routine = re.compile(str(src["routine"]), re.I) if src.get("routine") else None

    out: list[Event] = []
    seen: set[str] = set()
    for item in _items(page or ""):
        try:
            for ev in _parse_item(item, feed, tz, base, routine):
                if ev.uid in seen:
                    continue
                seen.add(ev.uid)
                out.append(ev)
        except Exception as exc:
            log.warning("skipping event-list item %s: %s", str(item.get("event-title"))[:60], exc)
    return out


def _items(page: str) -> list[dict]:
    """One dict per rendered listing: its data-* attributes plus the inner HTML after them."""
    starts = [m.start() for m in _ITEM.finditer(page)]
    items = []
    for i, pos in enumerate(starts):
        stop = starts[i + 1] if i + 1 < len(starts) else len(page)
        block = page[pos:stop]
        tag_end = block.find(">")
        attrs = {k: v for k, v in _ATTR.findall(block[:tag_end if tag_end > 0 else len(block)])}
        if attrs.get("event-id") and attrs.get("event-occurrences"):
            attrs["_inner"] = block[tag_end:] if tag_end > 0 else ""
            items.append(attrs)
    return items


def _parse_item(item: dict, feed: Feed, tz: ZoneInfo, base: str, routine: re.Pattern | None) -> list[Event]:
    title = htmllib.unescape(item.get("event-title") or "(untitled)").strip()
    url = urljoin(base, htmllib.unescape(item.get("href") or ""))
    categories = [c.strip() for c in htmllib.unescape(item.get("event-categories") or "").split(",") if c.strip()]
    if routine and routine.search(title):
        categories.append("routine")

    inner = item.get("_inner") or ""
    blurb = _DESCRIPTION.search(inner)
    body = html_to_text(blurb.group(1)) if blurb else ""
    description = "\n\n".join(p for p in (body, f"Details: {url}") if p)
    img = _IMG.search(inner)
    image = urljoin(base, htmllib.unescape(img.group(1))) if img else ""

    out: list[Event] = []
    for occ in json.loads(htmllib.unescape(item["event-occurrences"])):
        start, end, all_day = _window(occ, feed, tz)
        out.append(Event(
            uid=f"{item['event-id']}-{(start.date() if isinstance(start, datetime) else start):%Y%m%d}@{feed.slug}",
            summary=title,
            start=start,
            end=end,
            all_day=all_day,
            description=description,
            location=feed.location,
            url=url,
            categories=categories,
            image=image,
        ))
    return out


def _window(occ: dict, feed: Feed, tz: ZoneInfo) -> tuple[datetime | date, datetime | date, bool]:
    day = date.fromisoformat(str(occ["start"]["event_date"]).strip()[:10])
    # `hide_time` means the page prints no clock time for the listing (the $5 movie Tuesdays run
    # whenever the theatre is open). Treat it like all-day rather than publish the sentinel
    # 8:01am-6:59pm span the CMS stores behind it.
    all_day = _flag(occ.get("allday")) or _flag(occ.get("hide_time"))
    if all_day:
        last = date.fromisoformat(str((occ.get("end") or occ["start"]).get("event_date", day))[:10])
        return day, max(last, day) + timedelta(days=1), True      # DTEND is exclusive

    start = datetime.combine(day, _clock(occ["start"]), tzinfo=tz)
    end_day = date.fromisoformat(str((occ.get("end") or occ["start"]).get("event_date", day))[:10])
    end = datetime.combine(end_day, _clock(occ.get("end") or occ["start"]), tzinfo=tz)
    if end <= start:
        end = start + timedelta(minutes=feed.default_duration_minutes)
    return start, end, False


def _flag(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _clock(part: dict) -> time:
    """{"hour": "4", "minutes": "0", "ampm": "PM"} -> 16:00. The CMS writes 12-hour parts, and
    pads neither field consistently ("4:0PM" in one occurrence, "04:00PM" in the next)."""
    hour = int(str(part.get("hour") or 0))
    minute = int(str(part.get("minutes") or 0))
    ampm = str(part.get("ampm") or "").strip().upper()
    if ampm == "PM" and hour < 12:
        hour += 12
    elif ampm == "AM" and hour == 12:
        hour = 0
    return time(hour=min(hour, 23), minute=min(minute, 59))
