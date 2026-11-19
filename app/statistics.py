"""Heartbeat coverage, not an electricity-meter reading.

Observed time is inferred conservatively from stored sessions, capped at the
last heartbeat + one expected interval, with known heartbeat gaps removed.
Unrecorded time is unknown; future time is never included in denominators.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from .config import TZ, INTERVAL
from .database import connect, utc_now


def local_bounds(day: date):
    start = datetime.combine(day, datetime.min.time(), TZ)
    # Construct the next local midnight explicitly to support 23/25h DST days.
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), TZ)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _parse(stamp):
    dt = datetime.fromisoformat(stamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _merge(intervals):
    result = []
    for a, b in sorted((a, b) for a, b in intervals if b > a):
        if result and a <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], b))
        else:
            result.append((a, b))
    return result


def _subtract(intervals, cuts):
    remaining = []
    for a, b in intervals:
        segments = [(a, b)]
        for c, d in cuts:
            newer = []
            for x, y in segments:
                if d <= x or c >= y:
                    newer.append((x, y))
                else:
                    if c > x: newer.append((x, c))
                    if d < y: newer.append((d, y))
            segments = newer
            if not segments: break
        remaining.extend(segments)
    return _merge(remaining)


def _overlap(intervals, start, end):
    return sum((min(b, end) - max(a, start)).total_seconds()
               for a, b in intervals if b > start and a < end)


def coverage(start, end, now=None):
    """Return one consistent snapshot and observed intervals for an elapsed window."""
    now = now or utc_now()
    end = min(end, now)
    if end <= start:
        return {"total": 0.0, "observed": 0.0, "unknown": 0.0,
                "gaps": [], "intervals": [], "start": start, "end": end}
    with connect() as db:
        sessions = db.execute(
            "SELECT started_at,last_seen FROM sessions "
            "WHERE started_at < ? AND last_seen >= ? ORDER BY started_at",
            (end.isoformat(), (start - timedelta(seconds=INTERVAL)).isoformat())
        ).fetchall()
        gaps = [dict(row) for row in db.execute(
            "SELECT * FROM gaps WHERE started_at < ? AND ended_at > ? ORDER BY started_at",
            (end.isoformat(), start.isoformat())
        ).fetchall()]
    raw = []
    for row in sessions:
        a = max(start, _parse(row['started_at']))
        # Heartbeat only proves monitoring through the expected next sample.
        b = min(end, _parse(row['last_seen']) + timedelta(seconds=INTERVAL))
        if b > a: raw.append((a, b))
    cuts = _merge([(max(start, _parse(g['started_at'])),
                    min(end, _parse(g['ended_at']))) for g in gaps])
    intervals = _subtract(_merge(raw), cuts)
    total = (end - start).total_seconds()
    observed = min(total, max(0.0, _overlap(intervals, start, end)))
    return {"total": total, "observed": observed,
            "unknown": max(0.0, total - observed), "gaps": gaps,
            "intervals": intervals, "start": start, "end": end}


def summary(start, end):
    data = coverage(start, end)
    return {key: data[key] for key in ('total', 'observed', 'unknown', 'gaps')}


def get_gaps(start, end):
    return coverage(start, end)['gaps']


def daily(day):
    return summary(*local_bounds(day))


def day_timeline(day, slots=48, now=None):
    """Each bin: observed, unknown, future seconds. No future-as-outage coloring."""
    now = now or utc_now()
    start, finish = local_bounds(day)
    data = coverage(start, finish, now)
    step = (finish - start) / slots
    bins = []
    for i in range(slots):
        a, b = start + step * i, start + step * (i + 1)
        elapsed = max(0.0, (min(b, now) - a).total_seconds()) if now > a else 0.0
        observed = _overlap(data['intervals'], a, min(b, now)) if elapsed else 0.0
        unknown = max(0.0, elapsed - observed)
        future = max(0.0, (b - a).total_seconds() - elapsed)
        bins.append((observed, unknown, future))
    return bins


def format_duration(seconds):
    # Round to the nearest minute for human-readable dashboard values.
    minutes = max(0, int((seconds + 30) // 60))
    hours, mins = divmod(minutes, 60)
    return f'{hours} год {mins:02d} хв'
