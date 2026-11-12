"""Merge a source iCal feed with manual blocks from blocks.csv into one .ics file.

Env vars:
  SOURCE_ICAL_URL   URL of the source feed (GitHub Secret)
  OUTPUT_NAME       output file name without extension (GitHub Secret, long random string)
  SOURCE_ICAL_FILE  optional, local file instead of URL (for testing)
"""
import csv
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from icalendar import Calendar, Event


def load_source():
    local = os.environ.get("SOURCE_ICAL_FILE")
    if local:
        return Path(local).read_bytes()
    url = os.environ.get("SOURCE_ICAL_URL")
    if not url:
        sys.exit("ERROR: SOURCE_ICAL_URL is not set")
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content


def load_blocks(path):
    blocks = []
    with open(path, newline="", encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    for n, row in enumerate(csv.DictReader(lines), start=1):
        start = date.fromisoformat(row["start"].strip())
        end_raw = (row.get("end") or "").strip()
        end = date.fromisoformat(end_raw) if end_raw else start + timedelta(days=1)
        if end <= start:
            sys.exit(f"ERROR: blocks.csv row {n}: end must be after start ({start} to {end})")
        label = (row.get("label") or "").strip() or "Blocked"
        blocks.append((start, end, label))
    return blocks


def main():
    src = Calendar.from_ical(load_source())
    out = Calendar()
    out.add("prodid", "-//Merged calendar//EN")
    out.add("version", "2.0")
    out.add("calscale", "GREGORIAN")
    out.add("x-wr-calname", "Merged calendar")

    for tz in src.walk("VTIMEZONE"):
        out.add_component(tz)

    source_count = 0
    for ev in src.walk("VEVENT"):
        out.add_component(ev)
        source_count += 1

    blocks = load_blocks("blocks.csv")
    now = datetime.now(timezone.utc)
    for start, end, label in blocks:
        ev = Event()
        ev.add("uid", f"manual-{start.isoformat()}-{end.isoformat()}@merged-calendar")
        ev.add("dtstamp", now)
        ev.add("dtstart", start)
        ev.add("dtend", end)
        ev.add("summary", label)
        ev.add("transp", "OPAQUE")
        out.add_component(ev)

    name = os.environ.get("OUTPUT_NAME", "calendar").strip() or "calendar"
    site = Path("site")
    site.mkdir(exist_ok=True)
    (site / f"{name}.ics").write_bytes(out.to_ical())
    print(f"Wrote {len(blocks)} manual blocks + {source_count} source events")


if __name__ == "__main__":
    main()
