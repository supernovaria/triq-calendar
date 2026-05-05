def extract_events():
    res = requests.get(URL, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    text_blocks = soup.get_text("\n", strip=True).split("\n")

    events = []
    current_date = None

    date_regex = re.compile(r"\b\w+,\s+\d{1,2}\s+\w+\s+\d{4}\b")
    event_regex = re.compile(r"^(\d{1,2}:\d{2})\s+(.*)")

    for line in text_blocks:
        line = line.strip()

        # detect date line
        if date_regex.search(line):
            try:
                current_date = normalize_date(date_regex.search(line).group())
            except Exception:
                current_date = None
            continue

        if not current_date:
            continue

        # detect event line
        match = event_regex.match(line)
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
