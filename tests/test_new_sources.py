"""The four adapters added for the holiday-season sources: Mosaic District (The Events Calendar
REST), Middleburg (schema.org JSON-LD), Village at Leesburg (data-event-* listings) and the City
of Fairfax (Granicus OpenCities directory + event pages)."""

import json
from datetime import date, datetime
from pathlib import Path

from eventnews.model import Feed
from eventnews.sources import event_list, jsonld, opencities, tribe_json

FIX = Path(__file__).parent / "fixtures"
TZ = "America/New_York"


def feed(slug, **kw):
    kw.setdefault("source", {"type": "manual", "file": "x"})
    return Feed(slug=slug, name=slug.title(), url=f"https://{slug}.example/events", location=f"{slug} default location",
                timezone=TZ, kind="town", **kw)


def by_name(events, prefix):
    return [e for e in events if e.summary.startswith(prefix)]


# ------------------------------------------------------- The Events Calendar REST (Mosaic)

TRIBE = feed("mosaic", source={"type": "tribe_json", "url": "https://mosaicdistrict.com"})
TRIBE_PAYLOAD = json.loads((FIX / "mosaic_tribe_events.json").read_text())["events"]


def test_tribe_timed_event_keeps_its_instance_id_and_local_time():
    [ev] = by_name(tribe_json.parse_events(TRIBE_PAYLOAD, TRIBE), "Holiday Village Market")
    assert ev.uid == "10008347@mosaic"                      # per-instance id, so recurrences never collide
    assert ev.start.isoformat() == "2026-11-21T11:00:00-05:00"
    assert ev.end.isoformat() == "2026-11-21T16:00:00-05:00"
    assert not ev.all_day
    assert ev.url == "https://mosaicdistrict.com/event/holiday-village-market/2026-11-21/"
    assert ev.image.endswith(".jpg")
    assert "merry mosaic" in ev.categories
    assert "Details: https://mosaicdistrict.com/event/holiday-village-market/2026-11-21/" in ev.description


def test_tribe_all_day_event_becomes_a_date_with_exclusive_end():
    [ev] = by_name(tribe_json.parse_events(TRIBE_PAYLOAD, TRIBE), "Mosaic Fall Fest")
    assert ev.all_day
    assert ev.start == date(2027, 9, 25) and ev.end == date(2027, 9, 26)


def test_tribe_falls_back_to_the_feed_location_when_the_event_has_no_venue():
    [ev] = by_name(tribe_json.parse_events(TRIBE_PAYLOAD, TRIBE), "Holiday Tree Lighting")
    assert ev.location == "mosaic default location"


def test_tribe_fetch_pages_and_windows(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, page):
            self.page = page

        def raise_for_status(self):
            pass

        def json(self):
            if self.page == 1:
                return {"events": [{"id": i} for i in range(tribe_json.PER_PAGE)], "total_pages": 2}
            return {"events": [{"id": 999}], "total_pages": 2}

    class Sess:
        def get(self, url, params=None, headers=None, timeout=None):
            calls.append((url, params["page"], params["start_date"], params["end_date"]))
            return Resp(params["page"])

    events = tribe_json.fetch("https://mosaicdistrict.com/", days_back=10, days_ahead=20,
                              session=Sess(), today=date(2026, 11, 21))
    assert len(events) == tribe_json.PER_PAGE + 1
    assert calls[0][0] == "https://mosaicdistrict.com/wp-json/tribe/events/v1/events"
    assert [c[1] for c in calls] == [1, 2]
    assert calls[0][2] == "2026-11-11" and calls[0][3] == "2026-12-11"


# ------------------------------------------------------------------ JSON-LD (Middleburg)

LD = feed("middleburg", source={"type": "jsonld", "url": "https://visitmiddleburgva.com/local-events/"}, accumulate=True)
LD_PAGE = (FIX / "middleburg_jsonld.html").read_text()


def test_jsonld_reads_every_event_block():
    events = jsonld.parse_events(LD_PAGE, LD)
    assert {e.summary for e in events} == {
        "Model Railroad Extravaganza", "Celebrate Thanksgiving in Middleburg!",
        "Yuri Gorbachev 23rd Annual Exhibition at The Byrne Gallery", "Family Board Game Night"}


def test_jsonld_timed_event_keeps_its_offset_venue_and_poster():
    [ev] = by_name(jsonld.parse_events(LD_PAGE, LD), "Model Railroad")
    assert ev.start.isoformat() == "2026-11-20T09:30:00-05:00"
    assert ev.end.isoformat() == "2026-11-20T17:00:00-05:00"
    assert not ev.all_day
    assert ev.location == "Middleburg Library, 101 Reed St, Middleburg, VA 20117"
    assert ev.url.endswith("/events/model-railroad-extravaganza-5-987-189/")
    assert ev.image.endswith(".png")
    assert ev.uid == "model-railroad-extravaganza-2026-11-20@middleburg"
    assert "T-TRAK" in ev.description


def test_jsonld_date_only_event_is_all_day_with_exclusive_end():
    [ev] = by_name(jsonld.parse_events(LD_PAGE, LD), "Celebrate Thanksgiving")
    assert ev.all_day
    assert ev.start == date(2026, 11, 23) and ev.end == date(2026, 11, 29)    # endDate 11-28 inclusive


def test_jsonld_ignores_non_event_nodes():
    page = ('<script type="application/ld+json">'
            '{"@graph":[{"@type":"WebSite","name":"Site"},'
            '{"@type":"Event","name":"Tree Lighting","startDate":"2026-12-04T17:00:00-05:00"}]}</script>')
    [ev] = jsonld.parse_events(page, LD)
    assert ev.summary == "Tree Lighting"


def test_jsonld_survives_a_broken_block():
    page = '<script type="application/ld+json">{not json</script>' + LD_PAGE
    assert len(jsonld.parse_events(page, LD)) == 4


# ------------------------------------------------- data-event-* listings (Village at Leesburg)

VAL = feed("village", source={"type": "event_list", "url": "https://www.villageatleesburg.com/events/",
                              "routine": "bargain tuesday|football season|friday night live"}, accumulate=True)
VAL_PAGE = (FIX / "village_event_list.html").read_text()


def test_event_list_expands_each_occurrence_and_dedupes_repeated_renders():
    events = event_list.parse_events(VAL_PAGE, VAL)
    tree = by_name(events, "Daily Tree Shows")
    assert [e.start_date for e in tree] == [date(2026, 11, 21), date(2026, 11, 22)]   # listed twice on the page
    assert len({e.uid for e in events}) == len(events)


def test_event_list_reads_12_hour_clock_parts():
    [first, second] = by_name(event_list.parse_events(VAL_PAGE, VAL), "Daily Tree Shows")
    assert first.start.isoformat() == "2026-11-21T16:00:00-05:00"
    assert first.end.isoformat() == "2026-11-21T21:00:00-05:00"
    assert second.start.isoformat() == "2026-11-22T16:00:00-05:00"
    # "04:00PM" in one occurrence and "4:0PM" in another are the same time
    [santa, _] = by_name(event_list.parse_events(VAL_PAGE, VAL), "Saturday Santa Visits")
    assert santa.start.isoformat() == "2026-12-05T16:00:00-05:00"


def test_event_list_blurb_image_url_and_uid():
    [ev, _] = by_name(event_list.parse_events(VAL_PAGE, VAL), "Daily Tree Shows")
    assert ev.uid == "8427-20261121@village"
    assert ev.url == "https://www.villageatleesburg.com/events/daily-tree-shows-4/"
    assert ev.image.startswith("https://www.villageatleesburg.com/media/")
    assert "holiday tree shows in the Plaza" in ev.description
    assert ev.location == "village default location"


def test_event_list_tags_the_weekly_tenant_promotions_routine():
    events = event_list.parse_events(VAL_PAGE, VAL)
    assert "routine" in by_name(events, "Football Season")[0].categories
    assert "routine" in by_name(events, "$5 Bargain Tuesdays")[0].categories
    assert "routine" not in by_name(events, "Daily Tree Shows")[0].categories


def test_event_list_allday_and_hidden_time_become_all_day():
    events = event_list.parse_events(VAL_PAGE, VAL)
    football = by_name(events, "Football Season")[0]          # allday "1"
    bargain = by_name(events, "$5 Bargain Tuesdays")[0]        # hide_time "1"
    assert football.all_day and football.start == date(2026, 11, 23) and football.end == date(2026, 11, 24)
    assert bargain.all_day and bargain.start == date(2026, 11, 24)


# ------------------------------------------------- OpenCities directory (City of Fairfax)

FFX = feed("fairfax", source={"type": "opencities", "url": "https://www.fairfaxva.gov/Events-directory"})
DIRECTORY = (FIX / "fairfax_directory.html").read_text()
CRAFT_SHOW = (FIX / "fairfax_craft_show.html").read_text()
CIVIL_WAR = (FIX / "fairfax_civil_war.html").read_text()


def test_opencities_directory_listing_fields():
    listings = opencities.parse_directory(DIRECTORY, "https://www.fairfaxva.gov/Events-directory")
    craft = next(i for i in listings if i["title"].startswith("40th Annual"))
    assert craft["url"] == "https://www.fairfaxva.gov/Events-directory/Parks-and-Recreation/Special-Events/Holiday-Craft-Show"
    assert craft["listed_date"] == date(2026, 11, 21)
    assert "premium arts and crafts festival" in craft["blurb"]
    assert craft["image"].startswith("https://www.fairfaxva.gov/files/")
    assert craft["tags"] == ["Community & Special Events"]


def test_opencities_reads_all_dates_off_the_event_page():
    listings = opencities.parse_directory(DIRECTORY, "https://www.fairfaxva.gov/Events-directory")
    craft = next(i for i in listings if i["title"].startswith("40th Annual"))
    craft["detail"] = CRAFT_SHOW
    events = opencities.parse_events([craft], FFX)
    assert [(e.start.isoformat()[:16], e.end.isoformat()[11:16]) for e in events] == [
        ("2026-11-21T10:00", "17:00"), ("2026-11-22T10:00", "15:00")]   # the "to 05:00 PM" next-date line is not a third
    assert events[0].uid == "40th-annual-holiday-craft-show-nov-21-22-20261121@fairfax"


def test_opencities_midnight_opening_hours_become_all_day_dates():
    listings = opencities.parse_directory(DIRECTORY, "https://www.fairfaxva.gov/Events-directory")
    exhibit = next(i for i in listings if i["title"] == "The Civil War")
    exhibit["detail"] = CIVIL_WAR
    events = opencities.parse_events([exhibit], FFX)
    assert len(events) == 8 and all(e.all_day for e in events)
    assert events[0].start == date(2026, 11, 11) and events[0].end == date(2026, 11, 12)


def test_opencities_short_window_from_midnight_stays_timed():
    [ev] = opencities.parse_events(
        [{"title": "New Year Countdown", "url": "https://x/e", "blurb": "", "address": "", "image": "", "tags": [],
          "listed_date": date(2027, 1, 1),
          "detail": "<p>Friday, January 01, 2027 | 12:00 AM - 02:00 AM</p>"}], FFX)
    assert not ev.all_day and ev.start.isoformat() == "2027-01-01T00:00:00-05:00"


def test_opencities_unreadable_event_page_falls_back_to_the_listed_date():
    listings = opencities.parse_directory(DIRECTORY, "https://www.fairfaxva.gov/Events-directory")
    thanksgiving = next(i for i in listings if i["title"].startswith("Thanksgiving Day"))
    [ev] = opencities.parse_events([thanksgiving], FFX)          # detail stayed ""
    assert ev.all_day and ev.start == date(2026, 11, 26)


def test_opencities_respects_robots_disallow():
    rules = opencities._disallowed_from_text("""
        User-agent: badbot
        Disallow: /

        User-agent: *
        Disallow: /Events-directory/Parks-and-Recreation/Special-Events/Claus-and-Cookies
        Disallow: /EngagementHQ-Projects/*
    """)
    blocked = "https://www.fairfaxva.gov/Events-directory/Parks-and-Recreation/Special-Events/Claus-and-Cookies"
    allowed = "https://www.fairfaxva.gov/Events-directory/Parks-and-Recreation/Special-Events/Holiday-Market"
    assert opencities._is_blocked(blocked, rules)
    assert opencities._is_blocked("https://www.fairfaxva.gov/EngagementHQ-Projects/anything", rules)
    assert not opencities._is_blocked(allowed, rules)


def test_opencities_fetch_skips_disallowed_pages(monkeypatch):
    fetched = []

    class Resp:
        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            pass

    class Sess:
        def get(self, url, headers=None, timeout=None):
            fetched.append(url)
            if url.endswith("/robots.txt"):
                return Resp("User-agent: *\nDisallow: /Events-directory/Historic-Resources/\n")
            if url.endswith("Events-directory"):
                return Resp(DIRECTORY)
            return Resp(CRAFT_SHOW)

    listings = opencities.fetch("https://www.fairfaxva.gov/Events-directory", session=Sess())
    civil_war = next(i for i in listings if i["title"] == "The Civil War")
    assert civil_war["detail"] == ""                  # under the disallowed prefix
    assert not any("Historic-Resources" in u for u in fetched)
    assert any("Holiday-Craft-Show" in u for u in fetched)
