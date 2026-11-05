"""request.earnings / request.dividends / request.splits read the event series the caller supplies
(ScriptRunner(event_data=...)); with none supplied they behave as before (na with ignore_invalid_symbol, an
explicit NotImplementedError otherwise). Events are merged like a daily request.security series:
lookahead_off shows an event from the last bar of its day, lookahead_on from the first bar of its day,
gaps_off holds the value, gaps_on shows it on that one bar. Synthetic hourly 24/7 UTC chart."""
import math
import sys
from pathlib import Path

import pytest

from pynecore.core.script_runner import ScriptRunner
from pynecore.qg_gates.common import default_syminfo
from pynecore.types.ohlcv import OHLCV

SCRIPT = Path(__file__).resolve().parent / "scripts" / "events.py"
T0, HOUR, DAY = 1_735_689_600_000, 3_600_000, 86_400_000  # 2025-01-01 00:00 UTC
N_DAYS = 5
TID = "PYTEST:TEST"  # the default test syminfo's tickerid

EVENTS = {
    # release times inside day 1 and day 3 (the hour is irrelevant: events are daily)
    "earnings": [
        {"time": T0 + DAY + 20 * HOUR, "actual": 1.5, "estimate": 1.25, "standardized": 0.75},
        {"time": T0 + 3 * DAY + 8 * HOUR, "actual": 2.0, "estimate": 2.5, "standardized": -0.5},
    ],
    "dividends": [{"time": T0 + 2 * DAY, "gross": 0.5, "net": 0.4}],
    "splits": [{"time": T0 + 2 * DAY + 5 * HOUR, "numerator": 4, "denominator": 1}],
}


def _bars():
    return [OHLCV(T0 + i * HOUR, 10.0, 11.0, 9.0, 10.5, 1.0) for i in range(N_DAYS * 24)]


def _run(event_data):
    sys.modules.pop(SCRIPT.stem, None)
    si = default_syminfo()
    si.period = "60"
    si.type = "stock"  # a crypto chart answers its own unfed corporate-action requests with na
    r = ScriptRunner(script_path=SCRIPT, ohlcv_iter=iter(_bars()), syminfo=si, event_data=event_data)
    rows = {}
    for candle, pv in r.run_iter():
        m = (candle.timestamp - T0) // HOUR
        rows[(m // 24, m % 24)] = dict(pv)
    return rows


def _na(v):
    return v is None or v != v or type(v).__name__ == "NA"


def _series(rows, name):
    return {k: v[name] for k, v in rows.items()}


def __test_lookahead_off_gaps_off_holds_from_the_last_bar_of_the_event_day__():
    rows = _run(EVENTS)
    for (d, h), r in rows.items():
        want = None if (d, h) < (1, 23) else 1.5 if (d, h) < (3, 23) else 2.0
        for name, vals in (("e_default", (1.5, 2.0)), ("e_estimate", (1.25, 2.5)), ("e_standardized", (0.75, -0.5))):
            want_v = None if want is None else vals[0 if want == 1.5 else 1]
            got = r[name]
            assert (_na(got) if want_v is None else got == want_v), (name, d, h, got, want_v)


def __test_lookahead_on_shows_the_event_from_the_first_bar_of_its_day__():
    rows = _run(EVENTS)
    for (d, h), r in rows.items():
        want = None if d < 1 else 1.5 if d < 3 else 2.0
        got = r["e_on"]
        assert (_na(got) if want is None else got == want), (d, h, got, want)


def __test_gaps_on_shows_each_event_on_the_one_bar_it_arrives__():
    rows = _run(EVENTS)
    off = {k: v for k, v in _series(rows, "e_off_gaps").items() if not _na(v)}
    assert off == {(1, 23): 1.5, (3, 23): 2.0}, off
    on = {k: v for k, v in _series(rows, "e_on_gaps").items() if not _na(v)}
    assert on == {(1, 0): 1.5, (3, 0): 2.0}, on
    # a splits event with gaps_on, lookahead_off: the one last bar of its day
    den = {k: v for k, v in _series(rows, "s_den_gaps").items() if not _na(v)}
    assert den == {(2, 23): 1.0}, den


def __test_dividends_and_splits_fields__():
    rows = _run(EVENTS)
    assert _na(rows[(2, 22)]["d_default"]) and rows[(2, 23)]["d_default"] == 0.5 and rows[(4, 5)]["d_default"] == 0.5
    assert rows[(2, 23)]["d_net"] == 0.4
    assert _na(rows[(2, 22)]["s_num"]) and rows[(2, 23)]["s_num"] == 4 and rows[(4, 0)]["s_num"] == 4


def __test_keys_are_kind_or_symbol_and_kind_and_other_symbols_stay_na__():
    qualified = {f"{TID}:{k}": v for k, v in EVENTS.items()}
    rows = _run(qualified)
    assert rows[(2, 12)]["e_default"] == 1.5
    # the requested "NYSE:OTHER" has no series of its own: na (ignore_invalid_symbol), not the chart's events
    assert all(_na(r["e_other"]) for r in _run(EVENTS).values())
    # events keyed to another symbol are not the chart symbol's
    with pytest.raises(NotImplementedError):
        _run({f"NYSE:OTHER:{k}": v for k, v in EVENTS.items()})


def __test_no_event_data_keeps_the_old_behavior__():
    """Nothing supplied: the explicit NotImplementedError of an unfed request stays (na only with
    ignore_invalid_symbol), exactly as before."""
    with pytest.raises(NotImplementedError):
        _run(None)


def _run_script(script, bars, period, event_data):
    path = SCRIPT.with_name(script)
    sys.modules.pop(path.stem, None)
    si = default_syminfo()
    si.period = period
    si.type = "stock"
    r = ScriptRunner(script_path=path, ohlcv_iter=iter(bars), syminfo=si, event_data=event_data)
    return [(c.timestamp, dict(p)) for c, p in r.run_iter()]


def __test_a_weekly_bar_sees_the_events_of_all_its_days__():
    """A 1W bar (Mon 2024-12-30, 01-06, 01-13...) contains the Wednesday 01-08 report: lookahead_on and _off
    both show it on THAT bar (its last day is Sunday 01-12), gaps_on on that bar only."""
    monday = T0 - 2 * DAY
    bars = [OHLCV(monday + w * 7 * DAY, 10.0, 11.0, 9.0, 10.5, 1.0) for w in range(6)]
    events = {"dividends": [], "splits": [],
              "earnings": [{"time": T0 + 7 * DAY + 12 * HOUR, "actual": 1.5},
                           {"time": T0 + 15 * DAY + 12 * HOUR, "actual": 2.0}]}
    rows = [p for _, p in _run_script("events.py", bars, "1W", events)]
    for name in ("e_default", "e_on"):
        got = [None if _na(r[name]) else r[name] for r in rows]
        assert got == [None, 1.5, 2.0, 2.0, 2.0, 2.0], (name, got)
    got = [None if _na(r["e_on_gaps"]) else r["e_on_gaps"] for r in rows]
    assert got == [None, 1.5, 2.0, None, None, None], got
    got = [None if _na(r["e_off_gaps"]) else r["e_off_gaps"] for r in rows]
    assert got == [None, 1.5, 2.0, None, None, None], got


def __test_gaps_on_does_not_depend_on_which_bars_ask__():
    """The event shows on the bar it arrives on, wherever the request sits: asked only on even bars it is
    dropped when it arrives on an odd bar (the merged series is the same either way), never deferred to the
    next bar that asks."""
    bars = [OHLCV(T0 + i * DAY, 10.0, 11.0, 9.0, 10.5, 1.0) for i in range(8)]
    events = {"earnings": [{"time": T0 + 2 * DAY, "actual": 1.5},   # arrives on bar 2 (even)
                           {"time": T0 + 5 * DAY, "actual": 2.0}]}  # arrives on bar 5 (odd)
    out = _run_script("events_if.py", bars, "1D", events)
    even = [None if _na(p["even_only"]) else p["even_only"] for _, p in out]
    # (nothing else reads the series: the old "previous READ bar" rule deferred the bar-5 event to bar 6)
    assert even == [None, None, 1.5, None, None, None, None, None], even
    # a second run starts clean (no state kept on the series)
    again = _run_script("events_if.py", bars, "1D", events)
    assert [None if _na(p["even_only"]) else p["even_only"] for _, p in again] == even
