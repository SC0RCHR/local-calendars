"""Granicus OpenCities event directories (fairfaxva.gov and the other .gov sites on it).

The platform publishes no iCal and no feed: `?format=ical`, `?format=json` and `?rss=1` all just
serve the HTML page again. What it does give is a tidy directory of `<article>` listings, each
with the event's title, blurb, address, artwork and a link - and then every date WITH its times
on the event's own page ("Saturday, November 21, 2026 | 10:00 AM - 05:00 PM"). The directory
itself shows only the next date and a "5 more dates" teaser, so this adapter reads the directory
and then each event page behind it. There are ten listings, so that is eleven requests a day.

Two things to know:

  * the site answers 403 to a request that sends no `Accept` / `Accept-Language` header (plain
    curl, say). It is not a login or a paywall and our own User-Agent is accepted - the headers
    below are the ordinary ones any client sends;
  * robots.txt disallows a handful of individual event pages (drafts and duplicates, but also
    "Claus and Cookies"). Those are skipped, and the listing's own next-date is published as an
    all-day event instead, so the event still shows up with a link - without its times.

Config:
    source:
      type: opencities
      url: https://www.fairfaxva.gov/Events-directory
      max_events: 40          # optional cap on detail pages fetched in one run
"""

from __future__ import annotations

import html as htmllib
import logging
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests

from eventnews.model import Event, Feed
from eventnews.text import html_to_text, slugify

log = logging.getLogger(__name__)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; eventnews/0.1; +https://github.com/SC0RCHR/local-calendars)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_EVENTS = 40

_ARTICLE = re.compile(r"<article>(.*?)</article>", re.S)
_TITLE = re.compile(r'class="list-item-title">(.*?)</h2>', re.S)
_HREF = re.compile(r'href="([^"]+)"')
_BLURB = re.compile(r'class="list-item-block-desc">(.*?)</span>', re.S)
_ADDRESS = re.compile(r'class="list-item-address">(.*?)</p>', re.S)
_THUMB = re.compile(r'<img[^>]+class="thumbnail-image[^"]*"[^>]+src="([^"]+)"')
_TAGS = re.compile(r'class="tagged-as-list">(.*?)</p>', re.S)
_NEXT_DATE = re.compile(r'class="part-date">(\d+)</span>\s*<span class="part-month">(\w+)</span>\s*<span class="part-year">(\d+)', re.S)
# "Saturday, November 21, 2026 | 10:00 AM - 05:00 PM". The "Next date:" line writes "to" rather
# than a dash, and the page's own list of the remaining dates - a <select> of <option>s on some
# events, a list of spans on others - drops the weekday, so both are optional here.
_WHEN = re.compile(r"(?:[A-Z][a-z]+day,\s*)?([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})\s*\|\s*"
                   r"(\d{1,2}:\d{2}\s*[AP]M)\s*(?:-|–|to)\s*(\d{1,2}:\d{2}\s*[AP]M)")


def fetch(url: str, max_events: int = MAX_EVENTS, session: requests.Session | None = None) -> list[dict]:
    """The directory's listings, each with the full date list read off its own page."""
    sess = session or requests.Session()
    page = _get(sess, url)
    blocked = _disallowed(sess, url)
    listings = parse_directory(page, url)[:max_events]
    for item in listings:
        if not item["url"] or _is_blocked(item["url"], blocked):
            if item["url"]:
                log.info("robots.txt disallows %s; publishing its listed date only", item["url"])
            continue
        try:
            item["detail"] = _get(sess, item["url"])
        except Exception as exc:
            log.warning("%s: detail page failed (%s)", item["title"], str(exc)[:120])
    return listings


def parse_directory(page: str, base: str) -> list[dict]:
    out = []
    for block in _ARTICLE.findall(page or ""):
        title = _text(_TITLE.search(block))
        if not title:
            continue
        href = _HREF.search(block)
        thumb = _THUMB.search(block)
        tags = _text(_TAGS.search(block)).replace("Tagged as:", "")
        out.append({
            "title": title,
            "url": urljoin(base, htmllib.unescape(href.group(1))) if href else "",
            "blurb": _text(_BLURB.search(block)),
            "address": _text(_ADDRESS.search(block)),
            "image": urljoin(base, htmllib.unescape(thumb.group(1))) if thumb else "",
            "tags": [t.strip() for t in re.split(r"[,;]", tags) if t.strip()],
            "listed_date": _listed_date(block),
            "detail": "",
        })
    return out


def parse_events(listings: list[dict], feed: Feed) -> list[Event]:
    tz = ZoneInfo(feed.timezone)
    out: list[Event] = []
    seen: set[str] = set()
    for item in listings:
        try:
            events = _parse_listing(item, feed, tz)
        except Exception as exc:
            log.warning("skipping %s: %s", str(item.get("title"))[:60], exc)
            continue
        for ev in events:
            if ev.uid in seen:
                continue
            seen.add(ev.uid)
            out.append(ev)
    return out


def _parse_listing(item: dict, feed: Feed, tz: ZoneInfo) -> list[Event]:
    title = item["title"]
    url = item["url"] or feed.url
    location = item.get("address") or feed.location
    description = "\n\n".join(p for p in (item.get("blurb") or "", f"Details: {url}") if p)
    common = dict(summary=title, description=description, location=location, url=url,
                  categories=list(item.get("tags") or []), image=item.get("image") or "")
    uid_base = slugify(title)[:60]

    def uid(day: date) -> str:
        return f"{uid_base}-{day:%Y%m%d}@{feed.slug}"

    timed, untimed = _dates(item.get("detail") or "", tz)
    if not timed and not untimed and item.get("listed_date"):
        untimed = [item["listed_date"]]                 # detail page unread: publish the listing's date

    out = [Event(uid=uid(s.date()), start=s, end=e, all_day=False, **common) for s, e in timed]
    timed_days = {s.date() for s, _ in timed}
    out += [Event(uid=uid(d), start=d, end=d + timedelta(days=1), all_day=True, **common)
            for d in untimed if d not in timed_days]
    return out


def _dates(detail: str, tz: ZoneInfo) -> tuple[list[tuple[datetime, datetime]], list[date]]:
    """The dates on an event page, split into timed windows and dates we have no time for.

    Each date is published as "Weekday, Month D, YYYY | h:mm AM - h:mm PM". A window that starts
    at midnight and runs most of the day is the city filling in opening hours instead of a start
    time (Historic Blenheim's exhibits are all entered "12:00 AM - 04:00 PM"), so that date
    becomes an all-day entry rather than an event that claims to start at midnight. A SHORT
    window from midnight is left alone - a New Year countdown really does start then.
    """
    timed: dict[datetime, datetime] = {}
    untimed: set[date] = set()
    for month, day, year, t1, t2 in _WHEN.findall((detail or "").replace("&nbsp;", " ")):
        try:
            start = datetime.strptime(f"{month} {day} {year} {_clean(t1)}", "%B %d %Y %I:%M %p").replace(tzinfo=tz)
            end = datetime.strptime(f"{month} {day} {year} {_clean(t2)}", "%B %d %Y %I:%M %p").replace(tzinfo=tz)
        except ValueError:
            continue
        if end <= start:
            end = end + timedelta(days=1)               # an evening event running past midnight
        if start.hour == 0 and start.minute == 0 and (end - start) > timedelta(hours=6):
            untimed.add(start.date())
            continue
        timed.setdefault(start, end)
    return sorted(timed.items()), sorted(untimed)


def _listed_date(block: str) -> date | None:
    m = _NEXT_DATE.search(block)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(2)} {m.group(1)} {m.group(3)}", "%b %d %Y").date()
    except ValueError:
        return None


def _get(sess: requests.Session, url: str) -> str:
    resp = sess.get(url, headers=HEADERS, timeout=40)
    resp.raise_for_status()
    return resp.text


def _disallowed(sess: requests.Session, url: str) -> list[str]:
    """The `User-agent: *` Disallow prefixes from robots.txt. Unreadable robots.txt = no rules."""
    parts = urlsplit(url)
    try:
        resp = sess.get(f"{parts.scheme}://{parts.netloc}/robots.txt", headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        log.info("no robots.txt for %s (%s)", parts.netloc, str(exc)[:80])
        return []
    return _disallowed_from_text(resp.text)


def _disallowed_from_text(robots: str) -> list[str]:
    rules, applies = [], False
    for line in robots.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            applies = value == "*"
        elif key == "disallow" and applies and value:
            rules.append(value)
    return rules


def _is_blocked(url: str, rules: list[str]) -> bool:
    path = urlsplit(url).path
    return any(path.startswith(rule.split("*", 1)[0]) for rule in rules if rule.split("*", 1)[0])


def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().upper()


def _text(m: re.Match | None) -> str:
    return html_to_text(m.group(1)).strip() if m else ""
