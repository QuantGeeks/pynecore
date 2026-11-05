"""
Event series for ``request.earnings`` / ``request.dividends`` / ``request.splits``.

PyneCore has no data source of its own for corporate events; the host supplies them with
``ScriptRunner(event_data=...)``, the way it supplies ``security_data`` for ``request.security``.

Input: a dict whose key is a kind (``"earnings"``, ``"dividends"``, ``"splits"``) or an
``"EXCHANGE:SYMBOL:KIND"`` pair, and whose value is an iterable of rows. A row is a mapping with a
``time`` (UTC milliseconds, or a ``datetime``) and the kind's fields:

* earnings: ``actual``, ``estimate``, ``standardized``
* dividends: ``gross``, ``net``
* splits: ``numerator``, ``denominator``

A field a row leaves out (or sets to ``None``) is na.

Merge semantics. TradingView serves these requests from a DAILY event series merged into the chart
like a daily ``request.security`` series, and so does this module: a row belongs to the calendar day
of its ``time`` in the symbol's exchange timezone.

* ``lookahead_off`` (the default): the row is visible from the LAST bar of its day (``session.islastbar``;
  every bar of a later day), when the day's bar has closed.
* ``lookahead_on``: the row is visible from the FIRST bar of its day, before the event happened.
* ``gaps_off`` (the default): the latest visible row's value is held on every bar; na before the first.
* ``gaps_on``: the value shows only on the bar the row becomes visible, na elsewhere.

Several rows on one day: the latest by ``time`` wins. The ``currency`` argument of the requests is
accepted and ignored (values are returned as supplied).
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping
from datetime import datetime, UTC
from math import nan
from zoneinfo import ZoneInfo

__all__ = ['EventSeries', 'build_event_data', 'event_value']

EVENT_FIELDS = {
    'earnings': ('actual', 'estimate', 'standardized'),
    'dividends': ('gross', 'net'),
    'splits': ('numerator', 'denominator'),
}


class EventSeries:
    """The rows of one event series, sorted by time, with the day index of the last timezone asked."""

    __slots__ = ('kind', 'times', 'rows', '_tz_name', '_days')

    def __init__(self, kind: str, rows: list[tuple[int, Mapping[str, float | None]]]):
        rows = sorted(rows, key=lambda r: r[0])
        self.kind = kind
        self.times = [t for t, _ in rows]
        self.rows = [r for _, r in rows]
        self._tz_name: str | None = None
        self._days: list[int] = []

    def days(self, tz_name: str) -> list[int]:
        """The proleptic ordinal of each row's calendar day in the timezone (cached per timezone)."""
        if self._tz_name != tz_name:
            tz = _zone(tz_name)
            self._days = [datetime.fromtimestamp(t / 1000, tz).date().toordinal() for t in self.times]
            self._tz_name = tz_name
        return self._days


def _zone(tz_name: str):
    try:
        return ZoneInfo(tz_name) if tz_name else UTC
    except (KeyError, ValueError):
        return UTC


def _millis(value) -> int:
    if isinstance(value, datetime):
        return int((value if value.tzinfo else value.replace(tzinfo=UTC)).timestamp() * 1000)
    return int(value)


def build_event_data(raw: Mapping[str, Iterable[Mapping]] | None) -> dict[str, EventSeries] | None:
    """
    Validate and index the host's event data.

    :param raw: ``{"[EXCHANGE:SYMBOL:]KIND": rows}``, see the module docstring
    :return: ``{key: EventSeries}``, or ``None`` when nothing was supplied
    :raises ValueError: On an unknown kind, a row without ``time`` or a field the kind does not have
    """
    if not raw:
        return None
    out: dict[str, EventSeries] = {}
    for key, rows in raw.items():
        kind = str(key).rpartition(':')[2]
        if kind not in EVENT_FIELDS:
            raise ValueError(f"event_data key {key!r}: the kind must be one of {sorted(EVENT_FIELDS)}")
        parsed = []
        for row in rows:
            if 'time' not in row:
                raise ValueError(f"event_data {key!r}: a row has no 'time': {row!r}")
            unknown = set(row) - {'time'} - set(EVENT_FIELDS[kind])
            if unknown:
                raise ValueError(f"event_data {key!r}: unknown field(s) {sorted(unknown)} for {kind}")
            parsed.append((_millis(row['time']),
                           {f: (None if row.get(f) is None else float(row[f])) for f in EVENT_FIELDS[kind]}))
        out[str(key)] = EventSeries(kind, parsed)
    return out


def _visible(days: list[int], day: int, last_bar_of_day: bool, lookahead_on: bool) -> int:
    """Index of the latest row visible on a bar of ``day``, or -1."""
    i = bisect_right(days, day) - 1
    if not lookahead_on and i >= 0 and days[i] == day and not last_bar_of_day:
        i = bisect_left(days, day) - 1
    return i


def event_value(series: EventSeries, field: str | None, bar_dt: datetime, prev_time_ms: int | None,
                next_time_ms: int | None, is_last_bar_of_day: bool, gaps_on: bool, lookahead_on: bool,
                tz_name: str) -> float:
    """
    The value of an event series on the current bar.

    The previous and next bars come from the CHART, not from the bars this series happened to be read on, so a
    request inside an ``if`` sees the same value a request on every bar would.

    :param series: The event series
    :param field: The field to read (``None``: na)
    :param bar_dt: The current bar's open, in the exchange timezone
    :param prev_time_ms: The previous chart bar's open (UTC ms), ``None`` on the first bar
    :param next_time_ms: The next chart bar's expected open for a chart coarser than one day (a bar then
        covers several calendar days and sees every event up to its last one), otherwise ``None``
    :param is_last_bar_of_day: Whether the current bar is its session's last (``session.islastbar``)
    :param gaps_on: ``barmerge.gaps_on``
    :param lookahead_on: ``barmerge.lookahead_on``
    :param tz_name: The exchange timezone
    :return: The field's value, or na
    """
    days = series.days(tz_name)
    tz = _zone(tz_name)
    bar_day = bar_dt.date().toordinal()
    if next_time_ms is not None:
        # coarse bar: it is over on the day before the next bar opens; the previous bar was over the day
        # before this one opened
        bar_day = datetime.fromtimestamp((next_time_ms - 1) / 1000, tz).date().toordinal()
        prev_day = datetime.fromtimestamp(bar_dt.timestamp() - 0.001, tz).date().toordinal()
        cur = _visible(days, bar_day, True, lookahead_on)
        prev = -1 if prev_time_ms is None else _visible(days, prev_day, True, lookahead_on)
    else:
        cur = _visible(days, bar_day, is_last_bar_of_day, lookahead_on)
        if prev_time_ms is None:
            prev = -1
        else:
            prev_day = datetime.fromtimestamp(prev_time_ms / 1000, tz).date().toordinal()
            # the previous bar was the last of its day when the current one is on a later day
            prev = _visible(days, prev_day, bar_day > prev_day, lookahead_on)
    if cur < 0 or field is None:
        return nan
    if gaps_on and cur <= prev:
        return nan
    value = series.rows[cur].get(field)
    return nan if value is None else value
