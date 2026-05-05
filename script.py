import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from ics import Calendar, Event
import re
import hashlib

URL = "https://www.transinterqueer.org/angebote/veranstaltungen/"

# German → English month mapping (for parsing)
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
    """
    Convert German date string like:
    'Mittwoch, 06 Mai 2026'
    → datetime.date
    """
    for de, en in GERMAN_MONTHS.items():
        date_str = date_str.replace(de, en)

    # Remove weekday
    parts = date_str.split(",", 1)
    if len(parts) == 2:
        date_str = parts[1].strip()

    return datetime.strptime(date_str, "%d %B %Y").date()


def extract_events():
    res = requests.get(URL, timeout=10)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    events = []
    current_date = None

    # The page uses headings + lists, so we iterate in order
    for el in soup.find_all(["h2", "h3", "p", "ul", "li"]):

        text = el.get_text(" ", strip=True)

        # Detect date lines (contain year + month)
        if re.search(r"\d{4}", text) and any(m in text for m in GERMAN_MONTHS):
            try:
                current_date = normalize_date(text)
            except Exception:
                continue

        # Extract list items as events
        if el.name == "li" and current_date:
            line = text

            # Match time at start (e.g. "19:00 Event name")
            match = re.match(r"(\d{1,2}:\d{2})\s+(.*)", line)
            if not match:
                continue

            time_str, title = match.groups()

            try:
                dt = datetime.strptime(time_str, "%H:%M").time()
            except ValueError:
                continue

            start_dt = datetime.combine(current_date, dt)

            events.append({
                "title": title.strip(),
                "start": start_dt
            })

    return events


def generate_uid(title, start_dt):
    """
    Stable UID based on content
    """
    base = f"{title}-{start_dt.isoformat()}"
    return hashlib.md5(base.encode()).hexdigest()


def build_calendar(events):
    cal = Calendar()

    for ev in events:
        e = Event()
        e.name = ev["title"]
        e.begin = ev["start"]
        e.duration = timedelta(hours=2)  # default duration

        # Stable UID (important!)
        e.uid = generate_uid(ev["title"], ev["start"])

        e.description = "Source: transinterqueer.org"
        e.location = "TransInterQueer e.V., Berlin"

        cal.events.add(e)

    with open("events.ics", "w", encoding="utf-8") as f:
        f.writelines(cal)


def main():
    events = extract_events()

    print(f"Found {len(events)} events")

    build_calendar(events)
    print("events.ics updated")


if __name__ == "__main__":
    main()