import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from ics import Calendar, Event
from urllib.parse import quote
from ics.grammar.parse import ContentLine
import re
import hashlib
import unicodedata
from collections import defaultdict

BERLIN = ZoneInfo("Europe/Berlin")

URL = "https://www.transinterqueer.org/en/offers-and-projects/events-2/"
BASE_URL = "https://supernovaria.github.io/triq-calendar"
TRIQ_EVENTS_URL = "https://www.transinterqueer.org/en/offers-and-projects/events-2/"
TRIQ_INSTAGRAM_URL = "https://www.instagram.com/transinterqueer/"


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
    current_event = None

    def flush():
        if current_event:
            events.append(current_event)

    for line in lines:
        line = line.strip()

        date = parse_date(line)
        if date:
            flush()
            current_event = None
            current_date = date
            pending_time = None
            continue

        if not current_date:
            continue

        if is_time_only(line):
            flush()
            current_event = None
            pending_time = line
            continue

        if pending_time:
            try:
                time_obj = datetime.strptime(pending_time, "%H:%M").time()
                start_dt = datetime.combine(current_date, time_obj).replace(tzinfo=BERLIN)
                current_event = {"title": line, "start": start_dt, "desc": []}
            except ValueError:
                pass
            pending_time = None
        elif current_event is not None:
            current_event["desc"].append(line)

    flush()
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
    parts = []
    if ev.get("desc"):
        parts.append("\n".join(ev["desc"]))
    parts.append(f"Source: {TRIQ_EVENTS_URL}")
    parts.append(f"Instagram (for last-minute changes): {TRIQ_INSTAGRAM_URL}")
    e.description = "\n\n".join(parts)
    return e


def write_calendar(events, path, name):
    cal = Calendar()
    cal.extra.append(ContentLine("X-WR-CALNAME", {}, f"TrIQ: {name}"))
    for ev in events:
        cal.events.add(make_ics_event(ev))
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
    .ig-note {{ font-size: 0.9rem; color: #555; margin-bottom: 2rem; }}
    .ig-note a {{ color: #555; }}
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
      font-size: 0.8rem;
      color: #aaa;
    }}
    footer a {{ color: #aaa; }}
  </style>
</head>
<body>
  <h1>Unofficial, subscribable calendars for the <a href="{TRIQ_EVENTS_URL}" target="_blank" rel="noopener">events of TrIQ Berlin e.V.</a></h1>

  <ul>
{rows}  </ul>

  <p class="ig-note">For last-minute changes or cancellations, check TrIQ's <a href="{TRIQ_INSTAGRAM_URL}" target="_blank" rel="noopener">Instagram</a>.</p>

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

    write_calendar(events, "triq_all_events.ics", "All Events")
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
            write_calendar(data["events"], filename, data["title"])
            print(f"Written: {filename}")
            series_entries.append({"display_name": data["title"], "filename": filename})

    generate_index(series_entries)
    print("Written: index.html")


if __name__ == "__main__":
    main()
