# CLAUDE.md - Event Newsletter

Christopher's subscribable local event calendars (breweries, towns, community groups near
Leesburg, VA 20176). Separate from JobHunt; lives at `~/Projects/EventNewsletter`, published from
GitHub repo `SC0RCHR/local-calendars` via GitHub Pages.

## What it does

GitHub Actions rebuilds the feeds and posts a weekly Discord digest; a launchd job on
Christopher's Mac pulls venues' Instagram grids. He subscribes to the published `.ics` URLs in
Apple Calendar. Venues that already publish a feed are linked, not mirrored.

### What runs when (the one place to check)

| When | What | Where |
|---|---|---|
| Daily 05:23 UTC | `eventnews build`: rebuild fetched feeds, refresh the external-feed cache, commit `docs/` | Actions, `build.yml` |
| Daily 10:30 UTC | copy published `.ics` to the old `brewery-calendars` paths | Actions in the mirror repo |
| Mondays 06:17 / 10:17 / 14:17 / 18:17 UTC | `eventnews digest --post --skip-if-posted`: purge the channel, post the week; later triggers stand down | Actions, `digest.yml` |
| **Mon & Thu 07:40 local** | `eventnews instagram`: pull each `instagram:` handle's public grid, write `data/instagram/review.md` | **His Mac, launchd** (`scripts/com.kyberstorm.eventnews-instagram.plist`, installed + verified 2026-11-02, `RunAtLoad` false, logs to `/tmp/eventnews-instagram.log`) |
| **1st of each month, by hand** | read Honor's month-at-a-glance poster from the review queue, update `config/events/honor-brewing.yaml` and `overrides.yaml` | a session |

Cron times are deliberately off the hour and early: GitHub's queue runs hours late and has
dropped runs outright. The Instagram pull cannot move to Actions (JS-rendered grid, datacenter
IPs blocked) and never logs in.

### Calendars (17)

Breweries: Honor Brewing - Loudoun (elfsight + curated), Route 7 (wheresthemusic + curated),
White's Ferry (curated), Chilly Hollow, Solace Sterling, Vanish, Flying Ace (all external feeds).
Towns & community: Town of Leesburg (vision_rss), One Loudoun (squarespace), Village at Leesburg
(event_list + curated), Mosaic District (tribe_json), Middleburg (jsonld), City of Fairfax
(opencities), Reston Town Center (webflow_cms), Historic Manassas (external), Farmers Markets
(curated). Fairs & Festivals (curated).

Mosaic, Middleburg and Fairfax joined on 2026-11-21, when Christopher asked for christmas and
holiday markets, tree lightings, kid zones and kid events, and New Year's Eve; Village at
Leesburg stopped being curated the same day, its site having been rebuilt and become readable.
Reston Town Center joined on 2026-11-24.

## Answering "what's coming up?" questions

Christopher asks things like "what October or German events are coming up in the next 30 days?"
right here in chat. The recipe:

```bash
cd ~/Projects/EventNewsletter
uv run eventnews upcoming --days 30                          # everything
uv run eventnews upcoming --days 30 --grep "oktober|german|stein|fest|lager|bavarian"
uv run eventnews upcoming --days 30 --json                   # when you want to filter/summarise yourself
```

Then summarise for him: group by date, name the venue, drop noise (weekly farmers markets,
council meetings) unless asked. Regex is a retrieval net, not the answer; read the titles and
descriptions and use judgement (e.g. "Chillyfest" is an Oktoberfest-style event even though
"german" isn't in the title). Note Leesburg's feed only sees ~2 weeks ahead.

## Fairs & Festivals (curated) and the Discord digest

- `config/events/fairs-festivals.yaml` is hand-curated because no regional aggregator publishes
  a feed (checked DullesMoms, Visit Loudoun, NOVA Parks, Loudoun Now on 2026-09-19). When
  Christopher asks to add a fair/festival, verify the date on the organizer's site or a .gov
  listing, then add it with a `verified:` date. Never add an event from memory alone.
  Multi-week attractions (pumpkin patches, Cox Farms) use `season:` so they show on weekends
  rather than as a two-month banner.
- The weekly Discord post (`eventnews digest`, Mondays via `.github/workflows/digest.yml`) has the
  three sections Christopher specified on 2026-09-19: "Fairs, Festivals and Carnivals", "Local
  Breweries" (seasonal first: Oktoberfest/German/Halloween in Sep-Oct, Christmas/holiday in
  Nov-Dec; live music only as a fallback; never karaoke/trivia/discounts), "Town Activities"
  (cap 8, with a Farmers Markets sub-list). The "Ongoing weekends:" and "Running now:" blocks are
  a label line followed by one event per line (his 2026-10-06 request), not a joined line, and
  "Running now:" sits at the TOP of its section, above this week's dated events. Sections are
  assembled from blocks by `_blocks()`, which puts one blank line between them. **"This week" is Mon-Sun**; a Saturday run shows only
  what is left of the weekend and drops anything already over. Each section ends with ONE
  "Next week:" highlights line; nothing further out is shown (he explicitly rejected seeing a
  fair 2 weeks away in detail). Layout he chose from four mockups on 2026-09-19: a **Top picks
  this week** card first (fair one-offs + seasonal brewery events + parade/airshow-type town
  items), then the three sections, each **grouped by date** (bold date header once, events as `- time — Title (Venue, Town): excerpt` bullets).
  Top Picks titles carry a themed emoji when one applies (👻 🎃 🍺 🏺 ...), from the ordered
  `digest.top_picks.icons` list in `config/calendars.yaml`: first match wins, matched against the
  title and only then the description, so a gig whose blurb mentions pumpkins stays a gig.
  In Top Picks (reworked 2026-09-24, extended 2026-10-01) same-day picks share one date header
  and read `**Title** · time (Venue)` / `> excerpt`; two or more picks running exactly the same
  multi-day range likewise share one `**Fri Oct 2 – Sun Oct 4**` header. Since 2026-10-06 EVERY
  multi-day run gets that header, even when only one pick runs it. An all-day event on a day with
  no timed pick is the one remaining inline case: `**date** — Title (Venue)`. Top picks repeat in full inside their sections; he wants that repetition. Tune under `digest:` in
  `config/calendars.yaml`; preview with `eventnews digest --from <day>`. An event that began
  before this week and runs for weeks (Honor's month-long Halloween pop-up bar) is listed in full
  the week it starts, then collapses to one **Running now:** line per section rather than being
  dropped (it was, until 2026-10-02) or repeated in full every Monday. Venues misspell things, so
  keyword patterns stay loose: Honor spells it "Halloweem", hence `hallowe\w*`. Needs the
  `DISCORD_WEBHOOK_URL` repo secret, which only Christopher sets.
- **GitHub cron is unreliable here**: runs have fired 4-9 hours after their scheduled time, and
  the 2026-10-05 digest was queued then cancelled without ever getting a runner, so that Monday's
  post never went out. Since then the digest has FOUR Monday triggers (06:17/10:17/14:17/18:17
  UTC) and scheduled runs pass `--skip-if-posted`, which reads the channel through the bot token
  and stands down if this digest's webhook already posted there this week. It matches on the
  message's `webhook_id` (parsed from `DISCORD_WEBHOOK_URL`), NOT on message text: without
  Discord's privileged Message Content intent the API returns empty `content` and `embeds` for
  messages the bot did not write, which is why a title-matching version silently never fired. A manual
  `workflow_dispatch` always posts. If the check itself errors, it posts rather than risk losing
  the week. Crons sit off the top of the hour because that minute is the most contended. Since 2026-09-19 the post is
  preceded by a **channel purge** (all non-pinned messages) via `DISCORD_BOT_TOKEN` +
  `DISCORD_CHANNEL_ID`, same pattern as JobHunt's newsletter; without them it posts unpurged.
- `short_name` / `town` on a feed drive the "(Vanish, Leesburg)" part; `wall_clock_tzids` fixes
  venues that tag events with the wrong TZID (Flying Ace uses America/Halifax for a quarter of
  theirs; the wall-clock time is the real Eastern time).

## The account rename (2026-11-18)

Christopher renamed his GitHub account **ByteMasterPro -> SC0RCHR**. GitHub redirects repo URLs
but NOT the Pages subdomain, so `bytemasterpro.github.io` stopped resolving and every published
`.ics` 404'd at once - including the brewery-calendars mirror whose whole job was keeping older
subscriptions alive. Everything now lives on `sc0rchr.github.io`; the repo slugs are unchanged.
If he renames again, expect the same, and nothing can preserve the old domain: it is released
and can be claimed by whoever registers that username next.

## The old URLs (brewery-calendars)

The project was renamed from "Brewery Calendars" on 2026-09-19, which moved GitHub Pages from
`sc0rchr.github.io/brewery-calendars/` to `.../local-calendars/` and broke Christopher's
existing Apple Calendar subscriptions (Pages does not redirect, and re-pointing the subscription
on his end did not stick). Since 2026-10-01 a separate repo, **SC0RCHR/brewery-calendars**,
serves the same `.ics` files at the old paths; its own scheduled workflow copies them from this
project's published feeds daily at 10:30 UTC and skips anything that is not a valid calendar.
Nothing is authored there. Adding or renaming a published feed here means adding the file there
too (the mirror only refreshes names it already has). It can be deleted once no old
subscriptions remain.

## What Christopher wants surfaced

**Unusual things that match his preferences belong in Top Picks, even when they are not events.**
His words, 2026-11-02. A pre-order window, a month-long pop-up, a seasonal menu, a one-off
offer - if it is unusual AND seasonal/family-shaped, promote it: put the full detail in a
`notices:` entry and add `pick:` (short wording) plus `pick_icon:`, which puts a one-line version
at the top of the Top Picks card while the section keeps the long text. Honor's Thanksgiving
Dinner To Go is the worked example. Do not promote routine things this way - weekly specials,
happy hours and discount nights stay out, as always.


Top Picks is deliberately NARROW and ranks before it caps: rank 0 marquee (fair/festival
one-offs, seasonal brewery events), rank 1 `pattern` matches (movie nights, petting zoos).
Nothing is promoted to pad a quiet week - he removed a "filler" tier on 2026-10-06 saying the
card should stay focused on his preferences "even if only 1 or 2 things show up"; mundane events
belong in Local Breweries and the other sections, which list them anyway.

**Qualifying for Top Picks matches the TITLE only**, as does seasonal rank 0: a blurb-only
match ranks lower instead. Vanish's "Frayed Knots" bio says they are "a local favourite at
festivals", which `fest\w*` read as a festival and which pushed the Monster Mash out of a
Halloween-week card (found 2026-10-19). A blurb match is not lost, just not marquee.

**Exclusions match the TITLE only** (`query.title_haystack`), not the blurb. Matching the
description cost a whole event: White's Ferry's Leesburg Fall Festival mentions "20% off wine
flights", which the `\d+% off` rule read as a discount night and dropped from the week. An event
NAMED after an offer ("50% Off Growler Fills") is still excluded.

Loose patterns have a cost to watch: `fall\b` once matched "September and October this fall" in
a car-meet blurb and promoted it over the movie night. Keep prose-common words out of the
seasonal lists; prefer `fall ?fest\w*` over `fall`.

**The holiday season, asked for by name on 2026-11-21:** christmas markets, holiday markets,
tree lightings, kid zones, kid events and New Year's Eve ("add christmas festival to words as
well"). These are in `top_picks.pattern`, the towns `prioritize` and the Nov/Dec brewery
`seasonal` block, with icons 🎄 🎅 🎁 🕎 🎆 ⛸️ ✨ 🧒. Two deliberate choices there:

- **kid terms are the explicit phrases**, not a bare `kids`: `kid.?zone`, `kids? activit\w*`,
  `face.?paint\w*`, `bounce house`, `puppet`, `magic show` and so on. A bare `kids` promoted
  Mosaic's weekly Barnes & Noble storytime to the card every single week, which is the "filler"
  he removed in October. "Storytime with Mrs. Claus" still qualifies - on `claus`.
- **civic notices that happen to carry a holiday word are in `skip`**: "Thanksgiving Day -
  Schedule & Services" is the City of Fairfax trash calendar, not an outing. Also `leaf
  collection`, `trash`, `recycling`, `street sweeping`, `snow removal`, `blood drive`. They stay
  in their section; they just never take a marquee slot.

`tests/test_holiday_matching.py` asserts all of this against the live config, in the wording
venues actually use - add a case there rather than eyeballing the regex.

Patterns are deliberately LOOSE - he said "I'd rather see more than miss things" (2026-10-06).
He has kids and asks for family outings by name: brewery festivals (Honor's Fall Fest), movie
nights on the lawn, petting zoos, craft nights, fairs and markets. Those are `prioritize` in the
breweries section and part of `top_picks.pattern`, so they rank above routine live music and can
reach Top Picks. Live music is the filler, never the headline. Two bugs that hid exactly these
events, both found by him on 2026-10-06 and worth not repeating:

- `fest\b` does not match "Festival" (the boundary fails before "ival"), so Honor's "3rd Annual
  Anniversary Fall Festival" and the "Raku Pottery Festival" were never seasonal. Use `fest\w*`.
- The brewery section used to keep the chronologically FIRST `limit` events, so a busy week cut
  Friday and Saturday entirely. It now ranks (seasonal, named kinds, music, rest), truncates by
  rank, and prints in time order; `limit` is 20, about one autumn week.

## Instagram as a source (session-driven, never CI)

Some venues announce only on Instagram. What works and what does not, established 2026-10-06:

- A logged-out profile page DOES render the recent grid, and the thumbnails are real CDN urls at
  640px - enough to read a month-at-a-glance poster. Honor posts one on the 1st of each month.
- A plain HTTP fetch does NOT work: the grid is rendered by JS, so `requests` gets a shell. It
  needs a real browser, and Instagram blocks datacenter IPs, so **this can never run in the
  weekly GitHub job**. Do not build a scraper into CI, and do not log in as Christopher: that
  risks his account and breaks Instagram's terms.
- The workflow is: open `https://www.instagram.com/<handle>` in the browser pane, extract the
  grid images, download them, read them, then write findings into
  `config/events/overrides.yaml` (detail for events a feed already has) or a curated file like
  `config/events/route-7.yaml` (events no feed carries). The extraction snippet:

      const imgs=[...document.querySelectorAll('img')].filter(i=>((i.src||'')+(i.srcset||'')).includes('cdninstagram')&&!/profile|highlight/i.test(i.alt||''));
      const pick=i=>{const s=(i.srcset||'').split(',').map(x=>x.trim().split(' ')).filter(a=>a[0]);const b=s.sort((a,b)=>parseInt(b[1]||0)-parseInt(a[1]||0))[0];return b?b[0]:i.src;};
      imgs.map(i=>({d:(i.alt||'').match(/on (\w+ \d+, \d{4})/)?.[1], alt:i.alt, url:pick(i)}))

  `alt` often carries Instagram's own OCR of the poster, which is a useful index even before
  downloading. Then curl the urls (they are signed but work for a while) and Read the files.
- **`uv run eventnews instagram`** automates the pulling half: Playwright headless Chromium loads
  each feed's `instagram:` handle logged out, downloads anything new to `data/instagram/<handle>/`
  (gitignored) and writes `data/instagram/review.md`, a newest-first queue. `scripts/
  com.kyberstorm.eventnews-instagram.plist` runs it on his Mac Mon/Thu 07:40 (install notes are in
  the file). It never runs in CI.
- **`data/instagram/review.md` lists only UNREAD posts**, as checkboxes, with a count in its
  heading; the manifest carries a `reviewed` flag per post. After looking at the images run
  `uv run eventnews instagram --mark-reviewed`, and use `--pending` to see what is outstanding
  without touching the network. A pull that leaves anything unread also prints a `::warning::`.
  This exists because Honor's **Thanksgiving Dinner To Go** poster (pre-orders, $225 whole dinner)
  was pulled on 2026-10-31 and sat unread for two days while the queue re-listed all 63 posts
  every run: Christopher found it on Instagram himself and asked why it was not in the digest.
- **Check the venue's own website too, not only Instagram.** Honor's homepage ran a modal for the
  Thanksgiving package with a direct Toast ordering link
  (`order.toasttab.com/online/honor-brewing-2-42604-dulles-trade-west-drive`) and the detail that
  online ordering is Loudoun-pickup only - none of which was on the poster. Christopher found it,
  2026-11-02. A notice's `url:`/`link_text:` carry an action link and are preferred over the
  Instagram handle in both the section and the promoted Top Picks line.
- **Read every image in the queue, not just the starred ones.** A star only means Instagram's alt
  text happened to carry an OCR hit; absence proves nothing. Venues also split one event across
  posts: White's Ferry announced the Leesburg Fall Festival on 2026-10-01 with the date and hours,
  then followed up on 10-03 with "20% OFF: Wine Flights - Fall Beer - Pretzel" and "More Details
  In Caption". Connect them before writing anything.
- When the detail that matters (a date, a promo code) is caption-only, do NOT guess: add a
  `notices:` entry in `config/events/overrides.yaml` and the digest prints a "📣 Heads up" line
  telling him to open their Instagram. That is his own instruction, 2026-10-06.
- Refresh when Christopher asks, or at the start of a month when venues post their schedule.

## Event artwork (where the real details hide)

Venues put the good stuff in the poster, not the text: Honor's Fall Fest lists "20 vendors, axe
throwing, petting zoo" only in the image. So:

- `Event.image` carries a poster URL. Sources: Elfsight `coverImage` (Honor), iCal `ATTACH`
  (Vanish, Flying Ace, Chilly Hollow, Historic Manassas), Squarespace `assetUrl` (One Loudoun).
  Solace's Google Calendar has none. Published feeds re-emit it as `ATTACH`.
- `uv run eventnews posters [--days N] [--only SLUG] [--missing-only]` downloads them to
  `data/posters/` (gitignored). **Read the images** and write what they add into
  `config/events/overrides.yaml` (`match`, optional `calendar`/`on`/`title`, `details`,
  `source`). `digest.blurb()` prefers an override over the feed's text.
- Do this when he asks why an event looks thin, and when adding a venue. Re-check each season;
  the override `match` is a title regex, so a repeating title needs `on:` to pin one date.
- `title:` renames an event the venue published without a usable one. Honor's Elfsight widget
  carried its Holiday Pop-Up Bar (Nov 23 - Jan 4) as literally "(untitled)", and because
  `_short_title` strips a trailing parenthetical the digest drew an **empty link**. The rename
  is applied in `build()` before anything groups or ranks, so every renderer agrees, and
  `override_for` matches the pre-rename name too so the same entry still supplies `details`.
  Read the poster before naming one; do not invent a title.

## Conventions

- **Config-first.** A new calendar on a known platform is a `config/calendars.yaml` entry.
  New platforms get a small adapter in `eventnews/sources/` registered in `sources/__init__.py`.
- **Structured data over scraping.** Look for the widget/platform API first: Elfsight boot JSON,
  a public Google Calendar behind an Elfsight widget, Vision CMS RSS, The Events Calendar
  `?ical=1`, CivicPlus `iCalendar.aspx`, Squarespace `?format=json`. Every current source was
  found this way; none scrape rendered HTML.
- **Link, don't mirror, feeds that already exist** (`feed_url`). Mirroring adds lag and loses
  RECURRENCE-ID overrides.
- **Stable UIDs** (`<source id>@<slug>`) so subscribers see edits, not duplicates.
- **Never publish an empty feed on a fetch failure.** `build` leaves the existing `.ics` alone.
  Since 2026-11-02 it retries with `query.RETRY_BACKOFF` first, and a source still down after
  that fails the run - Christopher wants the GitHub notification email when something is
  genuinely broken (he said so after I briefly made timeouts green). The retries are what make a
  red run meaningful: Nov 1 died on a single 30s wheresthemusic.us read timeout that would
  probably have passed on attempt two. The log and the `::error::` say whether the published feed
  survived, so severity is clear from the email.
  `sources.fetch_events` likewise tolerates one dead source on a multi-source feed as long as
  another returns events, so Route 7's curated file survives the listings site timing out.
- **The Top Picks card always renders.** When nothing qualifies it prints `top_picks.empty_note`
  instead of being dropped; an absent card reads as a failed post (Christopher, 2026-11-02).
  Early November is the natural dead zone: Halloween is over and the Nov/Dec seasonal pattern
  (christmas, santa, thanksgiving, veterans day) has nothing to match yet. Closures are skipped
  by `top_picks.skip`: "Town Offices Closed for Veterans Day" matches the words but is the
  opposite of an outing. Mind apostrophes - Honor writes "Veteran's Day", so patterns use
  `veteran.?s? day`.
- **Local times with TZID** (not UTC) so recurring events survive DST. VTIMEZONE is bounded.
- Prefer simple/direct; no over-engineering. Tests are fixture-based (`tests/fixtures/`).

## Run

```bash
uv run eventnews upcoming [--days N] [--grep RX] [--only slug,slug] [--json]
uv run eventnews build [--only SLUG] [--dry-run]
uv run pytest
```

## Source notes and landmines

- **Honor Brewing** posts a month-at-a-glance schedule on Instagram on the 1st, and it carries
  events their widget never gets (a Smash tournament, the holiday pop-up opening, the Thanksgiving
  closure) plus extra detail for ones it does. Its feed is therefore `elfsight` + a curated
  `config/events/honor-brewing.yaml`. **Re-read that poster at the start of each month** - it is
  the single highest-yield thing in this project. Only events MISSING from the widget go in the
  curated file; detail for events it already has goes in `overrides.yaml`.
- **Honor Brewing** (Elfsight widget `5cfe5396-...`): a "Commanders Watch Party" is entered as
  04:25-07:25 AM (their typo). We pass source data through as-is; do not "fix" upstream data.
  Fairfax location widget `620fc0b1-b6f5-4814-a54a-33d51c45bfe8` is commented out in config.
- **Chilly Hollow**: elf.site widget is fed by a public Google Calendar; we link to that.
- **Leesburg** (leesburgva.gov, Granicus/Vision CMS): HTML is behind Akamai Bot Manager (403 for
  curl, `bm-verify` challenges even in a real browser on deep links). The RSS endpoint
  `/Home/Components/RssFeeds/RssFeed/View?ctID=6&cateIDs=...` is NOT blocked. ctID=5 is News,
  6 is Calendar. Category ids are in the `<select name="eventcats_...">` on /residents/calendar.
  Horizon is ~2 weeks and no query parameter widens it, hence `accumulate: true`.
- **Vanish** (vanishbeer.com, Liquid Web): intermittently serves a cert chain that fails
  verification from GitHub runners ("certificate has expired"), though the chain is valid and
  verifies fine minutes later; diagnosed 2026-09-24 from a runner (chain ok, 5/5 fetches ok).
  It has also answered a feed request with the parked-domain **lander page** (HTTP 200, HTML).
  Three failures in four runs, so since 2026-10-01: `fetch_external` rejects anything that is not
  a parseable VCALENDAR, `eventnews build` writes each external feed to `cache/<slug>.ics` daily,
  and `load_calendar` falls back to that copy after `query.RETRY_BACKOFF` (~75s) is exhausted, so
  the venue stays in the digest. **Flying Ace** has had the same HTML-instead-of-iCal problem.
- **Route 7 Brewing** (Ashburn) publishes NO calendar: website is menu-and-hours, Facebook needs
  a login, Instagram posts only days ahead. Its feed merges two sources: `wheresthemusic`
  (wheresthemusic.us venue page, their live music, parseable with plain curl) and a curated
  `config/events/route-7.yaml` for everything read off Instagram. A feed's `source` may be a
  LIST; `fetch_events` merges them and dedupes by uid.
- **Village at Leesburg** (villageatleesburg.com/events/): **no longer Wix and no longer
  curated** (changed 2026-11-21). The site was rebuilt and server-renders every listing with its
  dates in a `data-event-occurrences` attribute, so `event_list` reads it directly. Two things
  follow: each event lists only its next TWO occurrences, so the feed is `accumulate: true` and
  a daily series like the holiday Tree Shows fills in as the weeks pass; and the weekly tenant
  promotions no longer carry a hand-written `routine` tag, so the adapter applies one from its
  `routine:` pattern (bargain movie Tuesdays, Friday live music, football at Anchor Bar). The
  towns section's `deprioritize` still ranks those last and `top_picks` still skips them -
  Christopher's rule from 2026-10-06 (list them, but the Monster Mash is what deserves
  attention) is unchanged. `config/events/village-at-leesburg.yaml` survives for what the page
  does NOT carry: poster detail and events already past. Do not curate an event the page lists;
  it would appear twice. The per-event ".ics" link on a detail page is a `data:` URI with one
  VEVENT, so it is no use.
- **Mosaic District** (mosaicdistrict.com, WordPress + The Events Calendar): `?ical=1` works but
  **collapses each recurring series to its next occurrence** - 16 VEVENTs where the REST API has
  38 instances over the same window, which would have shown one Saturday of Santa and one
  weekend of the Holiday Village Market. Hence `tribe_json` (the REST API) for this one. The
  three older Tribe feeds (Vanish, Flying Ace, Historic Manassas) stay on `feed_url` because
  their listings are one-offs; move one to `tribe_json` if its events ever start repeating.
- **Middleburg** (visitmiddleburgva.com/local-events/, Modern Events Calendar): no iCal export,
  `/wp-json/mec/v1/events` answers an empty list, and the `mec-events` post type exposes none of
  MEC's dates (they live in its own tables). Every rendered event does emit a schema.org Event
  block, so `jsonld` reads those. Only ~12 events, about a week ahead, are ever on the page and
  no month parameter widens it (`?mec_month=`, `?sf_month=` and friends all change nothing),
  hence `accumulate: true`. Christmas in Middleburg will not appear until it is ~a week out.
- **City of Fairfax** (fairfaxva.gov, Granicus OpenCities): publishes no feed in any form -
  `?format=ical`, `?format=json` and `?rss=1` all just serve the HTML page again. `opencities`
  reads the `/Events-directory` listings and then each event's page, which carries every date
  WITH its times (the directory shows only the next one plus a "5 more dates" teaser). Notes:
  the site answers **403 to a request with no `Accept`/`Accept-Language` header** - plain curl,
  say - and 200 to our own User-Agent once those are sent; robots.txt disallows a handful of
  individual event pages (drafts, but also "Claus and Cookies"), which are skipped and published
  as all-day from the directory's own date; and exhibits are entered as "12:00 AM - 04:00 PM",
  which is opening hours rather than a midnight start, so a midnight window longer than six
  hours becomes an all-day entry (a New Year countdown, being short, stays timed).
- **Reston Town Center** (restontowncenter.com/calendar-events, Webflow): the page renders the
  whole CMS collection - the full year, 69 items the day it was added - into hidden
  `data-field` divs, recurrence rules and all, so `webflow_cms` is one plain GET with no
  pagination and no detail fetches. Four things bite:
  * the page also carries an `ld+json` **CollectionPage** block, and it is hand-maintained and
    **stale**: in November 2026 it still gave the holiday parade as `2025-11-28` while the CMS
    fields said November 27, 2026. Never read it. (This is why `jsonld` is wrong here.)
  * `hero-image` and `category` are rendered BEFORE the `name` that opens their record, and the
    Featured Events list at the top links three events from outside any record. Reading either
    into whichever record happened to be open shifted every category by one - the holiday parade
    arrived tagged "Fitness & Wellness", and the towns section's `exclude` (which carries
    `fitness`) silently threw the headline event of the week away. `records()` holds back a
    field the open record already has, and drops a stray link; both are regression-tested.
  * end times are hand-typed and sometimes backwards (a concert ran "June 27 7:30 PM" to
    "June 10 10:00 PM"), so an end at or before the start falls back to the default duration,
    while a real multi-day span (the film festival) is kept.
  * Webflow renders at most 100 items per collection list; the adapter warns at that count.
  Cancellations come either as an `event-status` of "Cancelled" or as " - Cancelled" appended to
  the title with the status left blank; both are dropped. The per-event `category` is published
  as a CATEGORY, which is how their yoga/pilates/workout series get filtered out of the towns
  section even when the title does not say so.
- **Historic Manassas** (WordPress + The Events Calendar): `?ical=1` works. Each performance of
  a show has its own UID, so the digest collapses by (title, calendar), not UID.
- **One Loudoun** (Squarespace): `?format=json` works, `?format=ical` does not on their template.
  They enter weekly series (Zumba, Moonlight Market) as one months-long event; the adapter turns
  a 7+ day same-weekday span into a weekly RRULE.
- **Loudoun County** (loudoun.gov, CivicPlus): iCal exists at
  `/common/modules/iCalendar/iCalendar.aspx?catID=34&feed=calendar` but "County Events" had 4
  items; not worth adding as of 2026-09-19. Sterling, Ashburn and Aldie are unincorporated, so
  there is no town calendar for them; candidates are Visit Loudoun (visitloudoun.org, Simpleview
  CMS with a JSON API) and individual breweries.
- **City of Manassas** (manassasva.gov): Revize CMS calendar at /calendar.php, no feed found yet.
