from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class CronSchedule:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]


def _parse_field(value: str, minimum: int, maximum: int, *, names: dict[str, int] | None = None) -> frozenset[int]:
    if not value:
        raise ValueError("empty cron field")

    aliases = {key.lower(): val for key, val in (names or {}).items()}
    values: set[int] = set()

    def parse_atom(atom: str) -> int:
        lower = atom.lower()
        if lower in aliases:
            parsed = aliases[lower]
        else:
            try:
                parsed = int(atom)
            except ValueError as exc:
                raise ValueError(f"invalid cron value: {atom}") from exc
        if parsed == 7 and maximum == 6:
            parsed = 0
        if parsed < minimum or parsed > maximum:
            raise ValueError(f"cron value {atom} outside {minimum}-{maximum}")
        return parsed

    for part in value.split(","):
        if not part:
            raise ValueError("empty cron list item")
        if "/" in part:
            base, step_text = part.split("/", 1)
            try:
                step = int(step_text)
            except ValueError as exc:
                raise ValueError(f"invalid cron step: {step_text}") from exc
            if step <= 0:
                raise ValueError("cron step must be positive")
        else:
            base, step = part, 1

        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            start, end = parse_atom(start_text), parse_atom(end_text)
            if end < start:
                raise ValueError("cron range end before start")
        else:
            start = end = parse_atom(base)

        values.update(range(start, end + 1, step))

    return frozenset(sorted(values))


def parse_cron_string(cron: str) -> CronSchedule:
    parts = cron.split()
    if len(parts) != 5:
        raise ValueError("cron must have 5 fields: minute hour day-of-month month day-of-week")
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    weekdays = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
    return CronSchedule(
        minutes=_parse_field(parts[0], 0, 59),
        hours=_parse_field(parts[1], 0, 23),
        days=_parse_field(parts[2], 1, 31),
        months=_parse_field(parts[3], 1, 12, names=months),
        weekdays=_parse_field(parts[4], 0, 6, names=weekdays),
    )


def _cron_weekday(moment: dt.datetime) -> int:
    return (moment.weekday() + 1) % 7


def _matches(schedule: CronSchedule, moment: dt.datetime) -> bool:
    return (
        moment.minute in schedule.minutes
        and moment.hour in schedule.hours
        and moment.day in schedule.days
        and moment.month in schedule.months
        and _cron_weekday(moment) in schedule.weekdays
    )


def next_cron_time(cron: str, now: dt.datetime) -> dt.datetime:
    schedule = parse_cron_string(cron)
    candidate = now.replace(second=0, microsecond=0)
    if candidate <= now:
        candidate += dt.timedelta(minutes=1)
    deadline = candidate + dt.timedelta(days=370)
    while candidate <= deadline:
        if _matches(schedule, candidate):
            return candidate
        candidate += dt.timedelta(minutes=1)
    raise ValueError("cron schedule has no matching time within 370 days")


def validate_cron_string(cron: str) -> str:
    schedule = parse_cron_string(cron)
    if len(schedule.minutes) * len(schedule.hours) > 1:
        raise ValueError("BWT cron schedule must run at most once per day")
    next_cron_time(cron, dt.datetime.now(dt.UTC))
    return cron
