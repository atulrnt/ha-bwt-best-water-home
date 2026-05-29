from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
from typing import Any, Iterable

from .api import BwtDataPoint


@dataclass(frozen=True)
class WaterAccumulatorState:
    total_l: float
    last_processed: dt.datetime | None

    @property
    def total_m3(self) -> float:
        return self.total_l / 1000.0


class WaterAccumulator:
    """Checkpointed accumulator for BWT daily delta buckets.

    BWT Skyline stats are bucketed consumption deltas. HA Energy wants a monotonic
    total. This class sums only closed daily buckets and remembers the latest
    bucket timestamp so duplicate polls do not double-count.
    """

    def __init__(self, total_l: float = 0.0, last_processed: dt.datetime | None = None) -> None:
        self.total_l = float(total_l)
        self.last_processed = last_processed

    @classmethod
    def from_state(cls, attrs: dict[str, Any] | None) -> "WaterAccumulator":
        attrs = attrs or {}
        total_l = float(attrs.get("total_l") or 0.0)
        raw_last = attrs.get("last_processed")
        last = dt.datetime.fromisoformat(raw_last) if raw_last else None
        return cls(total_l=total_l, last_processed=last)

    def as_state(self) -> WaterAccumulatorState:
        return WaterAccumulatorState(total_l=self.total_l, last_processed=self.last_processed)

    def update_from_daily_litre_points(
        self,
        points: Iterable[tuple[dt.datetime, float] | BwtDataPoint],
        *,
        now: dt.datetime | None = None,
    ) -> WaterAccumulatorState:
        now = now or dt.datetime.now(dt.UTC)
        closed_before = now - dt.timedelta(days=1)
        normalized: list[tuple[dt.datetime, float]] = []
        for point in points:
            if isinstance(point, BwtDataPoint):
                timestamp, value = point.date, point.value
            else:
                timestamp, value = point
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=dt.UTC)
            normalized.append((timestamp, float(value)))

        for timestamp, value in sorted(normalized, key=lambda item: item[0]):
            if timestamp > closed_before:
                continue
            if self.last_processed is not None and timestamp <= self.last_processed:
                continue
            self.total_l += value
            self.last_processed = timestamp
        return self.as_state()
