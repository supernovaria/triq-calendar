import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from ics import Calendar, Event
import re
import hashlib
import unicodedata
from collections import defaultdict

BERLIN = ZoneInfo("Europe/Berlin")

URL = "https://www.transinterqueer.org/en/offers-and-projects/events-2/"


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


def main():
    events = extract_events()
    print(f"Found {len(events)} events")
    if not events:
        raise ValueError("No events found — parsing likely failed")

    write_calendar(events, "triq_all_events.ics")
    print("Written: triq_all_events.ics")

    # Group by normalized title; any title appearing 2+ times gets its own file
    series_map = defaultdict(lambda: {"title": None, "events": []})
    for ev in events:
        key = ev["title"].lower().strip()
        if series_map[key]["title"] is None:
            series_map[key]["title"] = ev["title"]
        series_map[key]["events"].append(ev)

    for data in series_map.values():
        if len(data["events"]) >= 2:
            filename = f"triq_{slugify(data['title'])}.ics"
            write_calendar(data["events"], filename)
            print(f"Written: {filename}")


if __name__ == "__main__":
    main()
