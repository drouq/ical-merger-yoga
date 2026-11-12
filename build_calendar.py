"""Merge a source iCal feed with manual blocks from blocks.csv into one .ics file.

- Manual blocks are checked against the source events. Only nights that are not
  already booked get a block event, so nothing overlaps.
- All events in the output are sorted by start date.

Env vars:
  SOURCE_ICAL_URL   URL of the source feed (GitHub Secret)
  OUTPUT_NAME       output file name without extension (GitHub Secret, long random string)
  SOURCE_ICAL_FILE  optional, local file instead of URL (for testing)
"""
import csv
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from icalendar import Calendar, Event

# Times copied from the source feed (UTC): bookings start 07:00Z (15:00 Bali) and end 04:00Z (12:00 Bali).
# Manual blocks use the same times so they look like the source events.
START_TIME_UTC = time(7, 0)
END_TIME_UTC = time(4, 0)

# Dates are read as Bali dates, because a night belongs to the property's local day.
LOCAL_TZ = ZoneInfo("Asia/Makassar")


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


def to_local_date(value):
    """Turn an iCal date or datetime into a Bali calendar date."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(LOCAL_TZ)
        return value.date()
    return value


def event_nights(ev):
    """Return (first_night, checkout_date) for a source event, or None to skip it."""
    if str(ev.get("STATUS", "")).upper() == "CANCELLED":
        return None
    if "DTSTART" not in ev:
        return None
    start = to_local_date(ev.decoded("DTSTART"))
    if "DTEND" in ev:
        end = to_local_date(ev.decoded("DTEND"))
    else:
        end = start + timedelta(days=1)
    if end <= start:
        return None
    return start, end


def merge_ranges(ranges):
    """Merge overlapping or touching (start, end) ranges. End is exclusive."""
    merged = []
    for s, e in sorted(ranges):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def free_segments(start, end, covered):
    """Parts of [start, end) that are not inside any covered range."""
    segments = []
    cur = start
    for s, e in merge_ranges(covered):
        if e <= cur:
            continue
        if s >= end:
            break
        if s > cur:
            segments.append((cur, min(s, end)))
        cur = max(cur, e)
        if cur >= end:
            break
    if cur < end:
        segments.append((cur, end))
    return segments


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


def sort_key(ev):
    nights = event_nights(ev)
    day = nights[0] if nights else date.max
    return (day, str(ev.get("UID", "")))


def main():
    src = Calendar.from_ical(load_source())

    source_events = list(src.walk("VEVENT"))
    covered = [n for n in (event_nights(ev) for ev in source_events) if n]

    now = datetime.now(timezone.utc)
    manual_events = []
    for start, end, label in load_blocks("blocks.csv"):
        segments = free_segments(start, end, covered)
        total = (end - start).days
        free = sum((e - s).days for s, e in segments)
        print(f"Block {start} to {end} '{label}': {total} nights, "
              f"{total - free} already booked, {free} nights blocked in {len(segments)} event(s)")
        if not segments:
            print("  WARNING: every night is already booked, no event created")
        for s, e in segments:
            ev = Event()
            ev.add("summary", label)
            ev.add("dtstart", datetime.combine(s, START_TIME_UTC, tzinfo=timezone.utc))
            ev.add("dtend", datetime.combine(e, END_TIME_UTC, tzinfo=timezone.utc))
            ev.add("dtstamp", now)
            ev.add("uid", f"manual-{s.isoformat()}-{e.isoformat()}@merged-calendar")
            manual_events.append(ev)
        covered.extend(segments)  # later rows cannot overlap earlier rows

    out = Calendar()
    out.add("prodid", "-//Merged calendar//EN")
    out.add("version", "2.0")
    out.add("calscale", "GREGORIAN")
    out.add("x-wr-calname", "Merged calendar")
    for tz in src.walk("VTIMEZONE"):
        out.add_component(tz)
    for ev in sorted(source_events + manual_events, key=sort_key):
        out.add_component(ev)

    name = os.environ.get("OUTPUT_NAME", "calendar").strip() or "calendar"
    site = Path("site")
    site.mkdir(exist_ok=True)
    (site / f"{name}.ics").write_bytes(out.to_ical())
    print(f"Wrote {len(source_events)} source events + {len(manual_events)} manual events, sorted by date")


if __name__ == "__main__":
    main()
