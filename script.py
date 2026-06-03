import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from ics import Calendar, Event
from urllib.parse import quote
from ics.grammar.parse import ContentLine
import re
import os
import glob
import hashlib
import unicodedata
from collections import defaultdict, Counter

BERLIN = ZoneInfo("Europe/Berlin")

# The source page only lists start times, so events get a fixed default length.
# _parse_end() will override this if the page ever exposes an end time.
DEFAULT_DURATION = timedelta(hours=2)
UID_DOMAIN = "triq-calendar.github.io"

URL = "https://www.transinterqueer.org/en/offers-and-projects/events-2/"
BASE_URL = "https://supernovaria.github.io/triq-calendar"
TRIQ_EVENTS_URL = "https://www.transinterqueer.org/en/offers-and-projects/events-2/"
TRIQ_INSTAGRAM_URL = "https://www.instagram.com/transinterqueer/"


def slugify(title):
    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", "ignore").decode("ascii")
    title = re.sub(r"[^\w]+", "_", title)
    return title.strip("_")


def normalize_title(title):
    """Casing/whitespace-insensitive key for grouping a series and for UIDs."""
    return re.sub(r"\s+", " ", title).strip().lower()


def _parse_dt(iso, epoch):
    """Prefer the ISO datetime (carries the correct DST offset); fall back to epoch."""
    if iso:
        try:
            return datetime.fromisoformat(iso).astimezone(BERLIN)
        except ValueError:
            pass
    if epoch and epoch.lstrip("-").isdigit():
        return datetime.fromtimestamp(int(epoch), tz=BERLIN)
    return None


def _parse_start(li):
    span = li.select_one(".simcal-event-start")
    iso = span.get("content") if span else None
    return _parse_dt(iso, li.get("data-start"))


def _parse_end(li, start):
    span = li.select_one(".simcal-event-end")
    iso = span.get("content") if span else None
    end = _parse_dt(iso, li.get("data-end"))
    return end if end and end > start else None


def _clean_description(desc_el):
    if desc_el is None:
        return ""
    lines = [l.strip() for l in desc_el.get_text("\n", strip=True).split("\n")]
    cleaned = []
    for l in lines:
        # collapse runs of blank lines introduced by <br><br>
        if not l and (not cleaned or not cleaned[-1]):
            continue
        cleaned.append(l)
    return "\n".join(cleaned).strip()


def extract_events():
    res = requests.get(URL, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    # The page is rendered by the Simple Calendar (simcal) WordPress plugin, which
    # emits structured, microdata-tagged markup. Parsing the DOM directly is far more
    # robust than walking the flattened page text and avoids footer/nav bleed-through.
    container = soup.select_one("div.simcal-calendar-list")
    if container is None:
        raise ValueError(
            "simcal calendar container not found — the events page structure changed"
        )

    events = []
    for li in container.select("li.simcal-event"):
        title_el = li.select_one(".simcal-event-title")
        start = _parse_start(li)
        if title_el is None or start is None:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue
        events.append({
            "title": title,
            "start": start,
            "end": _parse_end(li, start),
            "desc": _clean_description(li.select_one(".simcal-event-description")),
        })
    return events


def generate_uid(title, start_dt):
    # Key on the normalized title + date only, so upstream casing fixes or small
    # time shifts don't mint a new UID (which subscribers would see as a duplicate).
    base = f"{normalize_title(title)}-{start_dt.date().isoformat()}"
    digest = hashlib.md5(base.encode()).hexdigest()
    return f"{digest}@{UID_DOMAIN}"


def make_ics_event(ev):
    e = Event()
    e.name = ev["title"]
    e.begin = ev["start"]
    if ev.get("end"):
        e.end = ev["end"]
    else:
        e.duration = DEFAULT_DURATION
    e.uid = generate_uid(ev["title"], ev["start"])
    e.location = "TransInterQueer e.V., Berlin"
    parts = []
    if ev.get("desc"):
        parts.append(ev["desc"])
    parts.append(f"Source: {TRIQ_EVENTS_URL}")
    parts.append(f"Instagram (for last-minute changes): {TRIQ_INSTAGRAM_URL}")
    e.description = "\n\n".join(parts)
    return e


def write_calendar(events, path, name):
    cal = Calendar()
    cal.extra.append(ContentLine("X-WR-CALNAME", {}, f"TrIQ: {name}"))
    seen = set()
    for ev in events:
        e = make_ics_event(ev)
        if e.uid in seen:
            continue
        seen.add(e.uid)
        cal.events.add(e)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(cal)


def calendar_row(display_name, filename, bold=False):
    ics_url = f"{BASE_URL}/{filename}"
    webcal_url = ics_url.replace("https://", "webcal://")
    google = f"https://calendar.google.com/calendar/render?cid={quote(webcal_url, safe='')}"
    apple = webcal_url
    outlook = f"https://outlook.live.com/calendar/0/addfromweb?url={quote(ics_url, safe='')}"
    name_class = "cal-name bold" if bold else "cal-name"
    return f"""    <li>
      <span class="{name_class}">{display_name}</span>
      <span class="links">
        <button class="copy-btn" onclick="copyLink(this, '{ics_url}')">Copy link</button>
        <a href="{ics_url}" class="ics-link">.ics</a>
        <a href="{google}" target="_blank" rel="noopener">Google</a>
        <a href="{apple}">Apple</a>
        <a href="{outlook}" target="_blank" rel="noopener">Outlook</a>
      </span>
    </li>
"""


def generate_index(series_entries):
    rows = calendar_row("All Events", "triq_all_events.ics", bold=True)
    for entry in sorted(series_entries, key=lambda e: e["display_name"].lower()):
        rows += calendar_row(entry["display_name"], entry["filename"])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TrIQ Berlin – Subscribable Calendars</title>
  <style>
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      max-width: 740px;
      margin: 3.5rem auto;
      padding: 0 2rem;
      color: #222;
      line-height: 1.6;
    }}
    h1 {{
      font-size: 1.2rem;
      font-weight: 600;
      margin-bottom: 2.5rem;
    }}
    h1 a {{ color: inherit; }}
    ul {{
      list-style: none;
      padding: 0;
      margin: 0 0 2.5rem 0;
    }}
    li {{
      display: grid;
      grid-template-columns: 17rem 1fr;
      align-items: center;
      gap: 1rem;
      padding: 0.85rem 0;
      border-bottom: 1px solid #eee;
    }}
    li:first-child {{ border-top: 1px solid #eee; }}
    .cal-name {{ font-weight: 400; }}
    .cal-name.bold {{ font-weight: 600; }}
    .links {{
      display: flex;
      gap: 0.4rem;
      flex-wrap: wrap;
      align-items: center;
    }}
    .links a, .copy-btn {{
      font-size: 0.78rem;
      font-weight: 500;
      padding: 0.3rem 0.75rem;
      border-radius: 999px;
      text-decoration: none;
      border: none;
      color: #fff;
      background: #1a1a1a;
      cursor: pointer;
      font-family: inherit;
      white-space: nowrap;
      transition: background 0.15s;
    }}
    .links a:hover, .copy-btn:hover {{ background: #3a3a3a; }}
    .copy-btn.copied {{ background: #16a34a; }}
    .ics-link {{
      background: transparent;
      color: #999;
      border: 1px solid #ddd;
    }}
    .ics-link:hover {{ background: #f5f5f5; color: #666; }}
    details {{ margin-top: 0.5rem; }}
    summary {{
      cursor: pointer;
      font-weight: 500;
      user-select: none;
      padding: 0.35rem 0;
    }}
    .instructions {{
      margin-top: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }}
    footer {{
      margin-top: 4rem;
      font-size: 0.9rem;
      color: #555;
    }}
    footer a {{ color: #555; }}
  </style>
</head>
<body>
  <h1>Unofficial, subscribable calendars for the <a href="{TRIQ_EVENTS_URL}" target="_blank" rel="noopener">events of TrIQ Berlin e.V.</a></h1>

  <ul>
{rows}  </ul>

  <details>
    <summary>How to subscribe</summary>
    <div class="instructions">
      <p><strong>Google</strong> — Click the Google button and confirm when prompted. Google will name the calendar after its URL; to rename it, click the three dots next to it in the sidebar → Settings → Name. The calendar syncs automatically every ~24 hours. On mobile, make sure the sync toggle is enabled for the calendar in the Google Calendar app settings.</p>
      <p><strong>Apple</strong> — Click the Apple button; it opens directly in Apple Calendar. Confirm when prompted. The calendar refreshes automatically based on your system's fetch interval (Calendar → Settings → Accounts → Fetch New Data).</p>
      <p><strong>Outlook</strong> — Click the Outlook button; it opens with the calendar pre-filled. Confirm when prompted. Outlook refreshes subscribed calendars automatically every few hours.</p>
      <p><strong>Proton Calendar</strong> — Click <strong>Copy link</strong>, then in Proton Calendar go to Settings → Calendars → Add calendar → Subscribe to calendar and paste the link. Proton refreshes subscribed calendars automatically.</p>
      <p><strong>Other apps</strong> — Click <strong>Copy link</strong> and paste the URL into your app's "subscribe" or "add by URL" feature. Most calendar apps refresh subscriptions automatically.</p>
    </div>
  </details>

  <footer>
    <p>For last-minute changes or cancellations, check TrIQ's <a href="{TRIQ_INSTAGRAM_URL}" target="_blank" rel="noopener">Instagram</a>.</p>
    <p>Updated every 12 hours &middot; Not affiliated with TransInterQueer e.V. &middot; <a href="https://github.com/supernovaria/triq-calendar">Source</a></p>
  </footer>

  <script>
    function copyLink(btn, url) {{
      navigator.clipboard.writeText(url).then(() => {{
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(() => {{
          btn.textContent = 'Copy link';
          btn.classList.remove('copied');
        }}, 2000);
      }});
    }}
  </script>
</body>
</html>
"""
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)


def main():
    events = extract_events()
    print(f"Found {len(events)} events")
    if not events:
        raise ValueError("No events parsed — parsing likely failed")

    # Group by normalized title, then pick the most common casing as the canonical
    # name so a single odd spelling upstream (e.g. "STrIQ-Treff") doesn't decide the
    # series name or filename. Apply it to every event so all feeds agree.
    series_map = defaultdict(list)
    for ev in events:
        series_map[normalize_title(ev["title"])].append(ev)
    for group in series_map.values():
        canonical = Counter(e["title"] for e in group).most_common(1)[0][0]
        for e in group:
            e["title"] = canonical

    written = set()

    write_calendar(events, "triq_all_events.ics", "All Events")
    written.add("triq_all_events.ics")
    print("Written: triq_all_events.ics")

    series_entries = []
    for group in series_map.values():
        if len(group) < 2:
            continue
        name = group[0]["title"]
        filename = f"triq_{slugify(name)}.ics"
        write_calendar(group, filename, name)
        written.add(filename)
        print(f"Written: {filename}")
        series_entries.append({"display_name": name, "filename": filename})

    # Prune series files that are no longer generated (e.g. a series that dropped
    # below the 2-event threshold), otherwise old feeds keep getting served stale.
    for path in glob.glob("triq_*.ics"):
        if path not in written:
            os.remove(path)
            print(f"Removed stale: {path}")

    generate_index(series_entries)
    print("Written: index.html")


if __name__ == "__main__":
    main()
