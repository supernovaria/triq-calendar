import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from ics import Calendar, Event
from urllib.parse import quote
import re
import hashlib
import unicodedata
from collections import defaultdict

BERLIN = ZoneInfo("Europe/Berlin")

URL = "https://www.transinterqueer.org/en/offers-and-projects/events-2/"
BASE_URL = "https://supernovaria.github.io/triq-calendar"
TRIQ_EVENTS_URL = "https://www.transinterqueer.org/en/offers-and-projects/events-2/"


def parse_date(line):
    try:
        parts = line.split(",", 1)
        if len(parts) == 2:
            return datetime.strptime(parts[1].strip(), "%d %B %Y").date()
    except ValueError:
        pass
    return None


def is_time_only(line):
    return bool(re.match(r"^\d{1,2}:\d{2}$", line.strip()))


def slugify(title):
    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", "ignore").decode("ascii")
    title = re.sub(r"[^\w]+", "_", title)
    return title.strip("_")


def extract_events():
    res = requests.get(URL, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")
    lines = [l for l in soup.get_text("\n", strip=True).split("\n") if l.strip()]

    events = []
    current_date = None
    pending_time = None

    for line in lines:
        line = line.strip()

        date = parse_date(line)
        if date:
            current_date = date
            pending_time = None
            continue

        if not current_date:
            continue

        if is_time_only(line):
            pending_time = line
            continue

        if pending_time:
            try:
                time_obj = datetime.strptime(pending_time, "%H:%M").time()
                start_dt = datetime.combine(current_date, time_obj).replace(tzinfo=BERLIN)
                events.append({"title": line, "start": start_dt})
            except ValueError:
                pass
            pending_time = None

    return events


def generate_uid(title, start_dt):
    base = f"{title}-{start_dt.isoformat()}"
    return hashlib.md5(base.encode()).hexdigest()


def make_ics_event(ev):
    e = Event()
    e.name = ev["title"]
    e.begin = ev["start"]
    e.duration = timedelta(hours=2)
    e.uid = generate_uid(ev["title"], ev["start"])
    e.location = "TransInterQueer e.V., Berlin"
    e.description = "Source: transinterqueer.org"
    return e


def write_calendar(events, path):
    cal = Calendar()
    for ev in events:
        cal.events.add(make_ics_event(ev))
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(cal)


def calendar_row(display_name, filename):
    ics_url = f"{BASE_URL}/{filename}"
    google = f"https://calendar.google.com/calendar/r/settings/addbyurl?url={quote(ics_url, safe='')}"
    apple = ics_url.replace("https://", "webcal://")
    outlook = f"https://outlook.live.com/calendar/0/addfromweb?url={quote(ics_url, safe='')}"
    return f"""    <li>
      <span class="cal-name">{display_name}</span>
      <span class="links">
        <a href="{google}" target="_blank" rel="noopener">Google</a>
        <a href="{apple}">Apple</a>
        <a href="{outlook}" target="_blank" rel="noopener">Outlook</a>
        <button class="copy-btn" onclick="copyLink(this, '{ics_url}')">Copy link</button>
        <a href="{ics_url}" class="ics-link">.ics</a>
      </span>
    </li>
"""


def generate_index(series_entries):
    rows = calendar_row("All Events", "triq_all_events.ics")
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
      max-width: 700px;
      margin: 2rem auto;
      padding: 0 1.5rem;
      color: #222;
      line-height: 1.6;
    }}
    h1 {{
      font-size: 1.25rem;
      font-weight: 600;
      margin-bottom: 1.5rem;
    }}
    h1 a {{ color: inherit; }}
    ul {{
      list-style: none;
      padding: 0;
      margin: 0 0 2rem 0;
    }}
    li {{
      display: flex;
      align-items: baseline;
      gap: 0.75rem;
      padding: 0.5rem 0;
      border-bottom: 1px solid #eee;
      flex-wrap: wrap;
    }}
    li:first-child {{ border-top: 1px solid #eee; }}
    .cal-name {{
      font-weight: 500;
      min-width: 12rem;
    }}
    .links {{
      display: flex;
      gap: 0.4rem;
      flex-wrap: wrap;
      align-items: center;
    }}
    .links a, .copy-btn {{
      font-size: 0.8rem;
      padding: 0.2rem 0.55rem;
      border-radius: 4px;
      text-decoration: none;
      border: 1px solid #ccc;
      color: #444;
      background: #f8f8f8;
      cursor: pointer;
      font-family: inherit;
      white-space: nowrap;
    }}
    .links a:hover, .copy-btn:hover {{ background: #eee; }}
    .copy-btn.copied {{ color: green; border-color: green; }}
    .ics-link {{ color: #999; }}
    details {{ margin-top: 1rem; }}
    summary {{
      cursor: pointer;
      font-weight: 500;
      user-select: none;
      padding: 0.25rem 0;
    }}
    .instructions {{ margin-top: 1rem; }}
    .instructions h3 {{
      font-size: 1rem;
      margin: 1.25rem 0 0.25rem;
    }}
    .instructions h3:first-child {{ margin-top: 0.5rem; }}
    .instructions ol, .instructions p {{
      margin: 0;
      padding-left: 1.25rem;
    }}
    .instructions p {{ padding-left: 0; }}
    footer {{
      margin-top: 3rem;
      font-size: 0.8rem;
      color: #999;
    }}
    footer a {{ color: #999; }}
  </style>
</head>
<body>
  <h1>Unofficial, subscribable calendars for the <a href="{TRIQ_EVENTS_URL}" target="_blank" rel="noopener">events of TrIQ Berlin e.V.</a></h1>

  <ul>
{rows}  </ul>

  <details>
    <summary>How to subscribe</summary>
    <div class="instructions">
      <h3>Google Calendar</h3>
      <ol>
        <li>Click the <strong>Google</strong> link next to the calendar you want.</li>
        <li>Click <em>Add calendar</em> to confirm.</li>
      </ol>

      <h3>Apple Calendar (macOS / iOS)</h3>
      <ol>
        <li>Click the <strong>Apple</strong> link next to the calendar you want.</li>
        <li>Your calendar app opens and asks to subscribe — click <em>Subscribe</em>.</li>
      </ol>

      <h3>Outlook</h3>
      <ol>
        <li>Click the <strong>Outlook</strong> link next to the calendar you want.</li>
        <li>Sign in if prompted, then click <em>Import</em>.</li>
      </ol>

      <h3>Proton Calendar</h3>
      <ol>
        <li>Click <strong>Copy link</strong> next to the calendar you want — this copies the calendar URL to your clipboard.</li>
        <li>Open Proton Calendar and go to <em>Settings → Calendars</em>.</li>
        <li>Click <em>Add calendar → Subscribe to calendar</em> and paste the copied link.</li>
      </ol>

      <h3>Other apps</h3>
      <p>Click <strong>Copy link</strong> and paste the URL into your app's "subscribe" or "add by URL" feature. Any calendar app that supports iCal subscriptions will work.</p>
    </div>
  </details>

  <footer>
    <p>Updated every 12 hours. Not affiliated with TransInterQueer e.V. &middot; <a href="https://github.com/supernovaria/triq-calendar">Source</a></p>
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
        raise ValueError("No events found — parsing likely failed")

    write_calendar(events, "triq_all_events.ics")
    print("Written: triq_all_events.ics")

    series_map = defaultdict(lambda: {"title": None, "events": []})
    for ev in events:
        key = ev["title"].lower().strip()
        if series_map[key]["title"] is None:
            series_map[key]["title"] = ev["title"]
        series_map[key]["events"].append(ev)

    series_entries = []
    for data in series_map.values():
        if len(data["events"]) >= 2:
            filename = f"triq_{slugify(data['title'])}.ics"
            write_calendar(data["events"], filename)
            print(f"Written: {filename}")
            series_entries.append({"display_name": data["title"], "filename": filename})

    generate_index(series_entries)
    print("Written: index.html")


if __name__ == "__main__":
    main()
