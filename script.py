import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from ics import Calendar, Event
import re
import hashlib

URL = "https://www.transinterqueer.org/angebote/veranstaltungen/"

GERMAN_MONTHS = {
    "Januar": "January",
    "Februar": "February",
    "März": "March",
    "April": "April",
    "Mai": "May",
    "Juni": "June",
    "Juli": "July",
    "August": "August",
    "September": "September",
    "Oktober": "October",
    "November": "November",
    "Dezember": "December"
}

def normalize_date(date_str):
    for de, en in GERMAN_MONTHS.items():
        date_str = date_str.replace(de, en)

    # remove weekday (e.g. "Mittwoch,")
    parts = date_str.split(",", 1)
    if len(parts) == 2:
        date_str = parts[1].strip()

    return datetime.strptime(date_str, "%d %B %Y").date()


def extract_events():
    res = requests.get(URL, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    events = []
    current_date = None

    # go through all visible text blocks in order
    elements = soup.find_all(["h2", "h3", "h4", "p", "li"])

    for el in elements:
        text = el.get_text(" ", strip=True)

        # match date like "Mittwoch, 06 Mai 2026"
        date_match = re.search(r"\b\w+,\s+\d{1,2}\s+\w+\s+\d{4}\b", text)
        if date_match:
            try:
                current_date = normalize_date(date_match.group())
            except Exception:
                current_date = None
            continue

        if not current_date:
            continue

        # match event line like "19:00 Event Name"
        match = re.match(r"^(\d{1,2}:\d{2})\s+(.*)", text)
        if match:
            time_str, title = match.groups()

            try:
                time_obj = datetime.strptime(time_str, "%H:%M").time()
            except ValueError:
                continue

            start_dt = datetime.combine(current_date, time_obj)

            events.append({
                "title": title.strip(),
                "start": start_dt
            })

    return events


def generate_uid(title, start_dt):
    base = f"{title}-{start_dt.isoformat()}"
    return hashlib.md5(base.encode()).hexdigest()


def build_calendar(events):
    cal = Calendar()

    for ev in events:
        e = Event()
        e.name = ev["title"]
        e.begin = ev["start"]
        e.duration = timedelta(hours=2)
        e.uid = generate_uid(ev["title"], ev["start"])
        e.location = "TransInterQueer e.V., Berlin"
        e.description = "Source: transinterqueer.org"

        cal.events.add(e)

    with open("events.ics", "w", encoding="utf-8") as f:
        f.writelines(cal)


def main():
    try:
        events = extract_events()
        print(f"Found {len(events)} events")

        if not events:
            raise ValueError("No events found — parsing likely failed")

        build_calendar(events)
        print("events.ics updated")

    except Exception as e:
        print("ERROR:", e)
        raise


if __name__ == "__main__":
    main()
