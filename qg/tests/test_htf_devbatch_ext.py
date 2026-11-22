"""The ChartBarWindow (batch) transport of a lookahead_on higher-timeframe context on an
EXTENDED-session chart (04:00–20:00, not 09:30–16:00) is run-to-run exact in one process and
equals the per-bar transport — both when the chart's bars fit the declared session and when
they OVERRUN its end (bars outside every declared session, whose round tick then falls in
the calendar's scheduled break). The overrun shape is the one a private parity tool had to
route around (its in-memory-iterator workaround's "extended day" arm): pre-fix, the batch
child of the daily context died with "the developing batch published no round … the child's
chart bar stream diverged from the bar loop's" on every run of this test's shape — RED 3/3
with the fix's hunks reverse-applied, green after. The RTH twin is test_htf_devbatch_repeat.py.
Synthetic data only (the fork is public)."""
import json
import sys
import tempfile
from datetime import time as dtime
from pathlib import Path

from pynecore.core.ohlcv import ChartBarWindow, OHLCVWriter
from pynecore.core.script_runner import ScriptRunner
from pynecore.core.syminfo import SymInfoInterval, SymInfoSession
from pynecore.qg_gates.common import default_syminfo
from pynecore.types.ohlcv import OHLCV

SCRIPT = Path(__file__).resolve().parent / "scripts" / "htf_devbatch_ext.py"
MIN, DAY = 60_000, 86_400_000
T0_IN = 1_736_154_000_000  # 2025-01-06 04:00 America/New_York: bars fit the session
T0_OVER = 1_736_166_000_000  # 07:20 the same day: 16h of bars overrun the 20:00 end
DAYS, N_MIN = [0, 1, 2, 3, 4, 7], 960  # six weekdays, skipping the weekend
N_RUNS = 3


def _close_i(i):
    return round(100.0 + (i % 37) * 0.01 + (i % 11) * 0.001, 3)


def _chart_bars(t0):
    bars, i = [], 0
    for d in DAYS:
        for m in range(N_MIN):
            c = _close_i(i)
            bars.append(OHLCV(t0 + d * DAY + m * MIN, round(c - 0.02, 3), round(c + 0.05, 3),
                              round(c - 0.06, 3), c, 1.0 + (i % 5)))
            i += 1
    return bars


def _syminfo(period):
    si = default_syminfo()
    si.period, si.timezone = period, "America/New_York"
    si.prefix, si.ticker = "AMEX", "TEST"
    si.mintick, si.pricescale, si.minmove = 0.01, 100, 1
    si.opening_hours = [SymInfoInterval(day=d, start=dtime(4, 0), end=dtime(20, 0)) for d in range(5)]
    si.session_starts = [SymInfoSession(day=d, time=dtime(4, 0)) for d in range(5)]
    si.session_ends = [SymInfoSession(day=d, time=dtime(20, 0)) for d in range(5)]
    return si


def _run(bars, batch, t0):
    """``batch`` runs the ChartBarWindow transport (the CLI path: the window's own bar
    stream and the pinned clock a batch run replays against); otherwise the per-bar one."""
    sys.modules.pop(SCRIPT.stem, None)
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as td:
        feed = Path(td) / "DAILY.ohlcv"
        with OHLCVWriter(feed, "1D") as w:
            for d in DAYS:
                day = [b for b in bars if (b.timestamp - t0) // DAY == d]
                w.write(OHLCV(t0 + d * DAY, day[0].open, round(max(b.high for b in day) + 0.01, 3),
                              min(b.low for b in day), round(day[-1].close + 0.01, 3),
                              sum(b.volume for b in day)))
        _syminfo("1D").save_toml(feed.with_suffix(".toml"))
        extra, stream = {}, iter(bars)
        if batch:
            chart = Path(td) / "CHART.ohlcv"
            with OHLCVWriter(chart, "1") as w:
                for b in bars:
                    w.write(b)
            _syminfo("1").save_toml(chart.with_suffix(".toml"))
            window = ChartBarWindow(chart, bars[0].timestamp, bars[-1].timestamp)
            stream, extra = window.bars(), dict(
                chart_bar_window=window, last_bar_index=len(bars) - 1,
                last_bar_time=bars[-1].timestamp)
        import os
        import pynecore.lib as _lib
        was_env, was_lib = os.environ.get("PYNE_TIMENOW_MS"), _lib._timenow_ms
        os.environ["PYNE_TIMENOW_MS"] = str(bars[-1].timestamp)
        _lib._timenow_ms = bars[-1].timestamp
        try:
            r = ScriptRunner(script_path=SCRIPT, ohlcv_iter=stream, syminfo=_syminfo("1"),
                             security_data={"1D": str(feed)}, **extra)
            return [dict(pv) for _, pv in r.run_iter()]
        finally:
            if was_env is None:
                os.environ.pop("PYNE_TIMENOW_MS", None)
            else:
                os.environ["PYNE_TIMENOW_MS"] = was_env
            _lib._timenow_ms = was_lib


def _canonical(rows):
    """Row-wise canonical JSON: nan == nan (a plain == on the dicts would flunk every na row)."""
    return [json.dumps(r, default=str, sort_keys=True) for r in rows]


def _assert_exact(t0):
    bars = _chart_bars(t0)
    oracle = _canonical(_run(bars, batch=False, t0=t0))
    runs = [_canonical(_run(bars, batch=True, t0=t0)) for _ in range(N_RUNS)]
    for n, rows in enumerate(runs):
        bad = [i for i, (a, b) in enumerate(zip(rows, oracle)) if a != b]
        assert not bad, (f"batch run {n} differs from the per-bar transport at bars {bad[:8]}: "
                         f"{[(runs[n][i], oracle[i]) for i in bad[:2]]}")
    for n in range(1, N_RUNS):
        bad = [i for i, (a, b) in enumerate(zip(runs[n], runs[0])) if a != b]
        assert not bad, (f"batch run {n} differs from run 0 at bars {bad[:8]}: "
                         f"{[(runs[n][i], runs[0][i]) for i in bad[:2]]}")


def __test_an_extended_session_batch_is_exact_and_equals_the_per_bar_one__():
    _assert_exact(T0_IN)


def __test_an_extended_session_batch_stays_exact_when_the_bars_overrun_the_session_end__():
    _assert_exact(T0_OVER)
