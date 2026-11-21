"""What the holiday season has to match, checked against the real config/calendars.yaml.

Christopher named these kinds by hand - christmas and holiday markets, tree lightings, kid zones
and kid events, New Year's Eve, christmas festivals - and named three live postings he wanted on
the card. The matching has silently lost things before (`fest\\b` never matched "Festival"), so
the patterns are tested against the wording venues actually use, not against the regex.
"""

import re
from pathlib import Path

import pytest

from eventnews.model import load_config

CFG = load_config(Path(__file__).parent.parent / "config" / "calendars.yaml")
PICKS = re.compile(CFG.digest["top_picks"]["pattern"], re.I)
SKIP = re.compile(CFG.digest["top_picks"]["skip"], re.I)
TOWNS = CFG.digest["sections"]["towns"]
TOWN_EXCLUDE = re.compile(TOWNS["exclude"], re.I)
TOWN_PRIORITY = re.compile(TOWNS["prioritize"], re.I)
WINTER = re.compile(next(s["pattern"] for s in CFG.digest["sections"]["breweries"]["seasonal"]
                         if 12 in s["months"]), re.I)


# the three postings Christopher pointed at, as their sites title them
@pytest.mark.parametrize("title", [
    "Holiday Village Market",
    "Daily Tree Shows",
    "Saturday Santa Visits",
])
def test_the_named_postings_qualify_for_top_picks(title):
    assert PICKS.search(title)


@pytest.mark.parametrize("title", [
    "Christmas Market",
    "Holiday Market",
    "10th Annual Holiday Market (Dec. 4-6, 11-13)",
    "40th Annual Holiday Craft Show (Nov. 21-22)",
    "Christmas Festival",
    "Christmas Parade",
    "Middleburg Community Christmas Parade",
    "Holiday Parade",
    "Holiday Festival of Lights",
    "Winter Festival",
    "Tree Lighting",
    "Holiday Tree Lighting",
    "Annual Christmas Tree Lighting Ceremony",
    "Kid Zone",
    "Kids Zone at the Winter Market",
    "Kids Craft Night",
    "Kids Club: Gingerbread Houses",
    "Family Fun Day",
    "Face Painting and Balloon Artist",
    "New Year's Eve Bash",
    "NYE Party",
    "Noon Year's Eve for Kids",
    "Ball Drop and Countdown",
    "Storytime with Mrs. Claus",
    "Sensory Santa Visits",
    "Breakfast with Santa",
    "Grinch Brunch at The Conche",
    "Hanukkah Candlelighting and Glow Party",
    "Menorah Lighting",
    "Polar Express Pajama Party",
    "Ugly Sweater Party",
    "Gingerbread House Workshop",
    "The Nutcracker",
    "Caroling on the Green",
    "Ice Skating Opening Night",
    "Winterfest",
    "Holiday Lights Walk",
    "Toy Drive",
    "Cookie Decorating",
])
def test_holiday_and_kid_wording_qualifies(title):
    assert PICKS.search(title), f"{title!r} would not reach Top Picks"


@pytest.mark.parametrize("title", [
    "Grand Cata: Trivia Tuesdays",
    "Caboose Commons: Trivia Night",
    "Karaoke Night",
    "$5 Bargain Tuesdays at Phoenix Theatres",
    "Live Music: Matty D.",
    "Barnes and Noble: Saturday Storytime",       # a weekly bookstore reading is not a marquee pick
])
def test_routine_nights_are_not_top_picks(title):
    assert not PICKS.search(title), f"{title!r} should stay in its own section"


@pytest.mark.parametrize("title", [
    "Thanksgiving Day - Schedule & Services",     # the trash and office-closure calendar
    "Closed for Thanksgiving",
    "Town Offices Closed for Christmas",
    "Fall Leaf Collection",
    "Inova Blood Drive",
])
def test_notices_and_closures_are_skipped_from_the_card(title):
    assert SKIP.search(title), f"{title!r} should never take a marquee slot"


@pytest.mark.parametrize("title", [
    "Grand Cata: Trivia Tuesdays",
    "Karaoke Night",
    "Fall Leaf Collection",
    "The Chase Club Is Coming to Middleburg: Now Accepting Applications!",
    "Town Council Meeting",
])
def test_town_section_drops_municipal_noise(title):
    assert TOWN_EXCLUDE.search(title)


@pytest.mark.parametrize("title", [
    "Holiday Village Market",
    "Daily Tree Shows",
    "Saturday Santa Visits",
    "Storytime with Mrs. Claus",
    "Hanukkah Candlelighting and Glow Party",
    "Christmas Festival",
    "Christmas Parade",
    "Holiday Parade",
])
def test_town_section_ranks_the_holiday_events_up(title):
    assert TOWN_PRIORITY.search(title)
    assert not TOWN_EXCLUDE.search(title)


@pytest.mark.parametrize("title", [
    "Santa at the Taproom",
    "Grinch Movie Night",
    "Christmas Market Pop-Up",
    "New Year's Eve Countdown",
    "Ugly Sweater Party",
])
def test_breweries_treat_these_as_seasonal_in_december(title):
    assert WINTER.search(title)
