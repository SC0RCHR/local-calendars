"""Reston Town Center: a Webflow CMS collection whose raw field values are rendered into hidden
`data-field` divs. The fixture is trimmed real markup, srcsets removed; see its header."""

from datetime import datetime
from pathlib import Path

import pytest

from eventnews.model import Feed
from eventnews.sources import webflow_cms

FIX = Path(__file__).parent / "fixtures"
PAGE = (FIX / "reston_webflow.html").read_text()
FEED = Feed(
    slug="reston-town-center",
    name="Reston Town Center",
    url="https://www.restontowncenter.com/calendar-events",
    location="Reston Town Center, 11900 Market St, Reston, VA 20190",
    timezone="America/New_York",
    kind="town",
    source={"type": "webflow_cms", "url": "https://www.restontowncenter.com/calendar-events"},
)
EVENTS = webflow_cms.parse_events(PAGE, FEED)


def one(prefix):
    [ev] = [e for e in EVENTS if e.summary.startswith(prefix)]
    return ev


def test_only_the_cms_items_become_events():
    # Six of the fixture's eight collection items; the two cancellations are dropped. The
    # Featured Events list (fs-list-field attributes) carries no data-field divs, so the parade
    # is not picked up a second time from it.
    assert len(EVENTS) == 6
    assert [e.summary for e in EVENTS].count("Reston Holiday Parade & Tree Lighting") == 1


def test_one_off_event_reads_its_fields():
    ev = one("Reston Holiday Parade")
    assert ev.summary == "Reston Holiday Parade & Tree Lighting"      # entities unescaped
    assert ev.start == datetime(2026, 11, 27, 11, 0, tzinfo=ev.start.tzinfo)
    assert ev.end == datetime(2026, 11, 27, 18, 30, tzinfo=ev.end.tzinfo)
    assert ev.start.utcoffset().total_seconds() == -5 * 3600          # local wall clock, EST
    assert ev.uid == "reston-holiday-parade-tree-lighting-20261127@reston-town-center"
    assert ev.url == "https://www.restontowncenter.com/calendar-events/reston-holiday-parade-tree-lighting"
    assert ev.location == FEED.location                              # the CMS has no per-event place
    assert ev.categories == ["Seasonal & Holiday"]
    assert ev.image.endswith("_LP_0124_M-1_1942.jpg")                # the hero image, not a gallery one
    assert ev.rrule is None


def test_each_item_keeps_its_own_category():
    """`category` is rendered ahead of the `name` that opens the record, so reading it into the
    record already open shifted every category by one item: the holiday parade came through as
    "Fitness & Wellness", and the digest's towns filter (which excludes `fitness`) dropped it."""
    assert {e.summary: e.categories for e in EVENTS} == {
        "Reston Holiday Parade & Tree Lighting": ["Seasonal & Holiday"],
        "Holiday Mini Train Rides": ["Seasonal & Holiday"],
        "Saturday Dog Strut": ["Community"],
        "Washington West Film Festival": ["Arts & Culture"],
        "Reston Concerts on the Town - RDGLDGRN": ["Music & Entertainment"],
        "Breakfast with Santa": ["Seasonal & Holiday"],
    }


def test_each_item_keeps_its_own_hero_image():
    """Same shift as the category: `hero-image` precedes the record it belongs to."""
    images = [e.image for e in EVENTS]
    assert len(set(images)) == len(images)              # no item wearing its neighbour's art
    assert all("gallery-images" not in i for i in images)
    assert one("Washington West").image.endswith("_Washington-West-Film-Festival.webp")
    assert one("Breakfast with Santa").image.endswith("fixture_breakfast-with-santa.webp")


def test_each_item_keeps_its_own_detail_link():
    """The Featured Events list at the top of the page links three of the same events. Those
    links are outside any field block, so they must not be handed to the first record."""
    assert PAGE.count('href="/calendar-events/run-with-santa-5k"') == 1      # featured only
    assert {e.summary: e.url.rsplit("/", 1)[-1] for e in EVENTS} == {
        "Reston Holiday Parade & Tree Lighting": "reston-holiday-parade-tree-lighting",
        "Holiday Mini Train Rides": "holiday-mini-train-rides",
        "Saturday Dog Strut": "saturday-dog-strut",
        "Washington West Film Festival": "washington-west-film-festival",
        "Reston Concerts on the Town - RDGLDGRN": "reston-concerts-on-the-town-june27",
        "Breakfast with Santa": "breakfast-with-santa",
    }


def test_the_stale_ld_json_is_ignored():
    """The page's hand-written CollectionPage block still said 2025-11-28 for the parade in
    November 2026. Nothing may be read from it."""
    assert "2025-11-28" in PAGE
    assert all(e.start.year == 2026 for e in EVENTS)


def test_weekly_series_becomes_an_rrule():
    ev = one("Holiday Mini Train Rides")
    assert ev.summary == "Holiday Mini Train Rides"                  # the CMS value has a trailing space
    assert ev.start == datetime(2026, 11, 29, 12, 0, tzinfo=ev.start.tzinfo)
    assert ev.rrule["FREQ"] == "WEEKLY"
    assert ev.rrule["BYDAY"] == "SU"
    assert ev.rrule["UNTIL"] == datetime(2026, 12, 20, 16, 0, tzinfo=ev.start.tzinfo)


def test_monthly_series_uses_the_week_of_month_ordinal():
    ev = one("Saturday Dog Strut")
    assert ev.rrule["FREQ"] == "MONTHLY"
    assert ev.rrule["BYDAY"] == "3SA"                                # "3rd" + "Sat"
    assert ev.rrule["UNTIL"].date().isoformat() == "2026-12-19"


def test_missing_end_time_falls_back_to_the_default_duration():
    ev = one("Saturday Dog Strut")                                   # end-date-time is empty
    assert (ev.end - ev.start).total_seconds() == FEED.default_duration_minutes * 60


def test_backwards_end_time_falls_back_too():
    """One concert was typed as June 27 7:30 PM -> June 10 10:00 PM."""
    ev = one("Reston Concerts on the Town")
    assert ev.start == datetime(2026, 6, 27, 19, 30, tzinfo=ev.start.tzinfo)
    assert ev.end == datetime(2026, 6, 27, 21, 30, tzinfo=ev.end.tzinfo)


def test_a_real_multi_day_span_is_kept():
    ev = one("Washington West Film Festival")
    assert ev.start == datetime(2026, 10, 8, 12, 0, tzinfo=ev.start.tzinfo)
    assert ev.end == datetime(2026, 10, 12, 18, 0, tzinfo=ev.end.tzinfo)
    assert ev.rrule is None          # it carries a recurrence-end-date but no frequency


def test_cost_and_summary_go_into_the_description():
    ev = one("Breakfast with Santa")
    assert ev.description.startswith("Pancakes, photos and a visit from the big guy himself.")
    assert "Cost: $15 per child" in ev.description
    assert ev.description.endswith(ev.url)


@pytest.mark.parametrize("title", ["Silent Disco at Window Plaza", "Silent Night Yoga"])
def test_cancellations_are_dropped_from_either_signal(title):
    """One has "- Cancelled" in the title with a blank status, the other a Cancelled status."""
    assert title in PAGE
    assert not [e for e in EVENTS if e.summary.startswith(title)]


def test_a_full_list_warns_that_webflow_truncated_it(caplog):
    item = PAGE[PAGE.index('<div role="listitem" class="collection-item-42'):]
    item = item[:item.index('</div></div>', item.index('data-field="event-status"'))]
    with caplog.at_level("WARNING"):
        events = webflow_cms.parse_events(item * webflow_cms.ITEM_CAP, FEED)
    assert len(events) == 1                                          # same uid every time
    assert "per-list cap" in caplog.text
