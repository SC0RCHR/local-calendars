"""Webflow CMS collections that render their raw field values into hidden divs.

Reston Town Center (Webflow: `data-wf-site`, assets on cdn.prod.website-files.com) draws its
calendar from a CMS collection and leaves every field of every item in the markup:

    <img data-field="hero-image" src="...">
    <div data-field="category">Seasonal &amp; Holiday</div>
    <div data-field="name">Holiday Mini Train Rides</div>
    <div data-field="short-summary">...</div>
    <div data-field="start-date-time">November 29, 2026 12:00 PM</div>
    <div data-field="end-date-time">November 29, 2026 4:00 PM</div>
    <div data-field="frequency">Weekly</div>
    <div data-field="day-of-week">Sun</div>
    <div data-field="week-of-month"></div>
    <div data-field="recurrence-end-date">Dec 20, 2026 4:00 PM</div>
    <div data-field="event-status">Scheduled</div>
    <a href="/calendar-events/holiday-mini-train-rides"></a>

so the whole year's collection is one plain GET, with its recurrence rules spelled out as
fields. Three things to know before changing this:

  * **Do not read the page's `ld+json`.** It is a hand-maintained `CollectionPage` block and it
    is stale - in November 2026 it still carried `"startDate": "2025-11-28"` for the holiday
    parade while the CMS fields said November 27, 2026. The `data-field` divs are the live data.
  * `end-date-time` is typed by hand and is sometimes wrong (one concert ran "June 27 7:30 PM"
    to "June 10 10:00 PM"). An end at or before the start is dropped in favour of the feed's
    `default_duration_minutes`; a genuine multi-day span (the film festival, Oct 8 - Oct 12) is
    kept as-is.
  * Webflow renders at most 100 collection items per list, and the whole calendar - 69 items
    the day this was written - is one list. If the count ever hits 100, items are being dropped
    and the list needs paginating.

Recurring items become a real RRULE rather than expanded dates, so subscribers get one series
and the digest can say "Sundays thru Dec 20": Weekly/Daily straight across, Monthly as
`BYDAY=3SA` from `week-of-month` + `day-of-week`.

Config:
    source:
      type: webflow_cms
      url: https://www.restontowncenter.com/calendar-events
"""

from __future__ import annotations

import html as htmllib
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests

from eventnews.model import Event, Feed
from eventnews.text import html_to_text

log = logging.getLogger(__name__)
USER_AGENT = "Mozilla/5.0 (compatible; eventnews/0.1; +https://github.com/SC0RCHR/local-calendars)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
ITEM_CAP = 100              # Webflow's per-list render limit; see the module docstring

FIELDS = frozenset({"hero-image", "category", "name", "short-summary", "start-date-time",
                    "end-date-time", "frequency", "day-of-week", "week-of-month",
                    "recurrence-end-date", "cost", "event-status"})
_FIELD = re.compile(r'data-field="([a-z-]+)"')
_SRC = re.compile(r'\bsrc="([^"]+)"')
_HREF = re.compile(r'href="([^"]*/calendar-events/[^"]+)"')
_WEEKDAYS = {"su": "SU", "sun": "SU", "mo": "MO", "mon": "MO", "tu": "TU", "tue": "TU",
             "we": "WE", "wed": "WE", "th": "TH", "thu": "TH", "fr": "FR", "fri": "FR",
             "sa": "SA", "sat": "SA"}
_ORDINALS = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "last": -1}


def fetch(url: str, session: requests.Session | None = None) -> str:
    sess = session or requests.Session()
    resp = sess.get(url, headers=HEADERS, timeout=40)
    resp.raise_for_status()
    return resp.text


def parse_events(page: str, feed: Feed) -> list[Event]:
    tz = ZoneInfo(feed.timezone)
    src = next((s for s in feed.sources if s.get("type") == "webflow_cms"), {})
    base = str(src.get("url") or feed.url)

    items = records(page or "")
    if len(items) >= ITEM_CAP:
        log.warning("%s: %d items is Webflow's per-list cap - the calendar is probably truncated",
                    feed.slug, len(items))
    out: list[Event] = []
    seen: set[str] = set()
    for item in items:
        try:
            ev = _parse_item(item, feed, tz, base)
        except Exception as exc:
            log.warning("skipping webflow item %s: %s", str(item.get("name"))[:60], exc)
            continue
        if ev is None or ev.uid in seen:
            continue
        seen.add(ev.uid)
        out.append(ev)
    return out


def records(page: str) -> list[dict[str, str]]:
    """One dict per collection item.

    `name` is the record boundary, but it is not the first field on the page: `hero-image` and
    `category` are rendered ahead of the block that holds the rest, so a field arriving while
    the previous record already has it belongs to the record about to start, and is held until
    `name` opens it. (Reading those two into the record that was already open shifted every
    category by one item - the holiday parade came through tagged "Fitness & Wellness", which
    the digest's towns filter then threw away.)
    """
    out: list[dict[str, str]] = []
    current: dict[str, str] = {}
    pending: dict[str, str] = {}
    for field, value in _tokens(page):
        if field == "name":
            current = {**pending, "name": value}
            pending = {}
            out.append(current)
        elif field == "_href":
            # The item's own detail link sits inside its block, after the fields. Links outside
            # any block are somebody else's - the Featured Events list at the top of the page
            # carries three - so they are dropped rather than held for the next record.
            if current:
                current.setdefault("_href", value)
        elif not current or field in current:
            pending[field] = value
        else:
            current[field] = value
    return out


def _tokens(page: str) -> list[tuple[str, str]]:
    """The `data-field` values we use, in document order, plus each event's own detail link as
    `_href`. Field divs are leaves, so the value is the text up to the next closing tag. Fields
    we ignore are dropped here rather than in `records`, which keeps its repeat rule simple -
    `gallery-images` is the one field a single item emits more than once.
    """
    marks: list[tuple[int, str, str]] = []
    for m in _FIELD.finditer(page):
        if m.group(1) not in FIELDS:
            continue
        tag_start = page.rfind("<", 0, m.start())
        tag_end = page.find(">", m.end())
        if tag_start < 0 or tag_end < 0:
            continue
        tag = page[tag_start:tag_end]
        if tag.lstrip("<").lower().startswith("img"):
            img = _SRC.search(tag)
            value = htmllib.unescape(img.group(1)) if img else ""
        else:
            close = page.find("</", tag_end)
            value = _text(page[tag_end + 1:close if close > 0 else tag_end + 1])
        marks.append((tag_start, m.group(1), value))
    for m in _HREF.finditer(page):
        marks.append((m.start(), "_href", htmllib.unescape(m.group(1))))
    marks.sort(key=lambda t: t[0])
    return [(field, value) for _, field, value in marks]


def _parse_item(item: dict[str, str], feed: Feed, tz: ZoneInfo, base: str) -> Event | None:
    title = item.get("name", "").strip()
    start = _when(item.get("start-date-time", ""), tz)
    if not title or start is None:
        return None
    # Cancellations show up either way round: an `event-status` of "Cancelled", or the status
    # left blank and " - Cancelled" appended to the title. Drop both, so a subscribed calendar
    # loses the entry instead of keeping a dead one.
    if "cancel" in f"{item.get('event-status', '')} {title}".lower():
        return None

    end = _when(item.get("end-date-time", ""), tz)
    if end is None or end <= start:      # hand-typed and sometimes backwards; see the docstring
        end = start + timedelta(minutes=feed.default_duration_minutes)

    url = urljoin(base, item.get("_href", "")) if item.get("_href") else feed.url
    summary = item.get("short-summary", "").strip()
    cost = item.get("cost", "").strip()
    description = "\n\n".join(p for p in (summary, f"Cost: {cost}" if cost else "", f"Details: {url}") if p)
    categories = [c for c in (item.get("category", "").strip(),) if c]

    return Event(
        uid=f"{_slug(url) or _slug(title)}-{start:%Y%m%d}@{feed.slug}",
        summary=title,
        start=start,
        end=end,
        description=description,
        location=feed.location,
        url=url,
        categories=categories,
        image=item.get("hero-image", ""),
        rrule=_rrule(item, tz),
    )


def _when(value: str, tz: ZoneInfo) -> datetime | None:
    """"November 29, 2026 12:00 PM" -> aware datetime. `recurrence-end-date` abbreviates the
    month ("Dec 20, 2026 4:00 PM") and a few items carry a date with no clock time."""
    text = " ".join(value.split())
    if not text:
        return None
    for fmt in ("%B %d, %Y %I:%M %p", "%b %d, %Y %I:%M %p", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    log.warning("unparsable webflow date %r", text[:60])
    return None


def _rrule(item: dict[str, str], tz: ZoneInfo) -> dict | None:
    freq = item.get("frequency", "").strip().upper()
    if freq not in {"DAILY", "WEEKLY", "MONTHLY"}:
        return None
    rule: dict[str, object] = {"FREQ": freq}
    day = _WEEKDAYS.get(item.get("day-of-week", "").strip().lower()[:3])
    if day and freq == "WEEKLY":
        rule["BYDAY"] = day
    elif day and freq == "MONTHLY":
        # "3rd" + "Sat" -> BYDAY=3SA. Without the ordinal, repeat on the day-of-month instead.
        ordinal = _ORDINALS.get(item.get("week-of-month", "").strip().lower())
        if ordinal:
            rule["BYDAY"] = f"{ordinal}{day}"
    until = _when(item.get("recurrence-end-date", ""), tz)
    if until:
        rule["UNTIL"] = until
    return rule


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower().rstrip("/").rsplit("/", 1)[-1]).strip("-")[:70]


def _text(fragment: str) -> str:
    return " ".join(html_to_text(fragment).split())
