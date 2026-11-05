"""A same-symbol higher-timeframe request.security with a supplied feed reads the feed's (official) bars, with
lookahead_on and lookahead_off, gaps on and off, and the close[1] idiom. Synthetic hourly 24/7 chart, daily feed
whose OHLC deliberately differs from the hourly aggregate. Without a feed the context is built from the chart's
own bars, as before."""
import sys
import tempfile

import pytest
from datetime import time as dtime
from pathlib import Path

from pynecore.core.ohlcv import ChartBarWindow, OHLCVWriter
from pynecore.core.script_runner import ScriptRunner
from pynecore.core.syminfo import SymInfo, SymInfoInterval, SymInfoSession
from pynecore.qg_gates.common import default_syminfo
from pynecore.types.ohlcv import OHLCV

SCRIPT = Path(__file__).resolve().parent / "scripts" / "htf_feed.py"
T0, HOUR, DAY, N_DAYS = 1_735_689_600_000, 3_600_000, 86_400_000, 5  # 2025-01-01 UTC


def _hourly(day, hour):
    return float(1000 * (day + 1) + hour)  # day d's last hourly close is 1000 * (d + 1) + 23


def _official_close(day):
    return 5000.0 + day  # never any hourly value


def _official_high(day):
    return 6000.0 + day


def _chart_bars():
    return [OHLCV(T0 + (d * 24 + h) * HOUR, _hourly(d, h), _hourly(d, h), _hourly(d, h), _hourly(d, h), 1.0)
            for d in range(N_DAYS) for h in range(24)]


def _syminfo(period):
    si = default_syminfo()
    si.period = period
    return si


def _write_feed(path):
    with OHLCVWriter(path, "1D") as w:
        for d in range(N_DAYS):
            w.write(OHLCV(T0 + d * DAY, 4000.0 + d, _official_high(d), 3000.0 + d, _official_close(d), 9.0))
    si = _syminfo("1D")
    si.save_toml(path.with_suffix(".toml"))
    return str(path)


def _run(feed, chart_file=False):
    """``chart_file`` gives the runner the chart's own feed file too, which arms the historical
    developing batch (the other transport of the same context); without it the per-bar path runs."""
    sys.modules.pop(SCRIPT.stem, None)
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as td:
        data = {"1D": _write_feed(Path(td) / "DAILY.ohlcv")} if feed else {}
        bars, extra = _chart_bars(), {}
        if chart_file:
            path = Path(td) / "CHART.ohlcv"
            with OHLCVWriter(path, "60") as w:
                for bar in bars:
                    w.write(bar)
            window = ChartBarWindow(path, bars[0].timestamp, bars[-1].timestamp)
            extra = dict(chart_bar_window=window, last_bar_index=len(bars) - 1, last_bar_time=bars[-1].timestamp)
        r = ScriptRunner(script_path=SCRIPT, ohlcv_iter=iter(bars), syminfo=_syminfo("60"),
                         security_data=data, **extra)
        rows = {}
        for candle, pv in r.run_iter():
            m = (candle.timestamp - T0) // HOUR
            rows[(m // 24, m % 24)] = dict(pv)
    return rows


def _na(v):
    return v != v or type(v).__name__ == "NA"


@pytest.mark.parametrize("chart_file", [False, True], ids=["per_bar", "dev_batch"])
def __test_supplied_daily_feed_is_the_source_of_same_symbol_htf__(chart_file):
    rows = _run(feed=True, chart_file=chart_file)
    for d in range(1, N_DAYS):
        for h in (0, 1, 12, 22, 23):
            r = rows[(d, h)]
            # lookahead_on + the close[1] idiom: yesterday's OFFICIAL close, not the last hourly close
            assert r["on_prev"] == _official_close(d - 1), (d, h, r["on_prev"])
            assert r["on_high_prev"] == _official_high(d - 1), (d, h, r["on_high_prev"])
            assert r["on_prev_gaps"] == _official_close(d - 1) or _na(r["on_prev_gaps"]), (d, h)
    for d in range(1, N_DAYS):
        # lookahead_off: the last closed daily bar, official; day d-1's arrives with its last chart bar
        assert rows[(d, 12)]["off_cur"] == _official_close(d - 1), (d, rows[(d, 12)]["off_cur"])
        assert rows[(d, 23)]["off_cur"] == _official_close(d), (d, rows[(d, 23)]["off_cur"])
        if d >= 2:
            assert rows[(d, 12)]["off_prev"] == _official_close(d - 2), (d, rows[(d, 12)]["off_prev"])
        # gaps_on: the value lands on the bar a daily bar closes on and is na elsewhere
        assert _na(rows[(d, 12)]["off_cur_gaps"]), (d, rows[(d, 12)]["off_cur_gaps"])
        assert rows[(d, 23)]["off_cur_gaps"] == _official_close(d), (d, rows[(d, 23)]["off_cur_gaps"])
    # gaps_on + lookahead_on: whatever bars carry the value, it is never a chart-built one
    for d in range(1, N_DAYS):
        for h in range(24):
            v = rows[(d, h)]["on_prev_gaps"]
            assert _na(v) or v == _official_close(d - 1), (d, h, v)
        assert rows[(d, 0)]["on_prev_gaps"] == _official_close(d - 1), (d, rows[(d, 0)]["on_prev_gaps"])


def __test_a_daily_context_without_a_feed_is_refused_not_guessed__():
    """Daily/weekly/monthly bars are never derived from the chart's bars: with no feed the read fails and
    names the parameter that supplies it (documented in request.security's docstring)."""
    with pytest.raises(ValueError, match="security_data"):
        _run(feed=False)


def __test_an_intraday_context_without_a_feed_is_built_from_the_chart_bars__():
    """The documented fallback: an intraday same-symbol HTF context with no supplied feed is aggregated
    from the chart's own feed, so close[1] is the last chart close of the previous period."""
    script = SCRIPT.with_name("htf_chart_built.py")
    sys.modules.pop(script.stem, None)
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as td:
        path = Path(td) / "CHART.ohlcv"
        with OHLCVWriter(path, "60") as w:
            for bar in _chart_bars():
                w.write(bar)
        _syminfo("60").save_toml(path.with_suffix(".toml"))
        r = ScriptRunner(script_path=script, ohlcv_iter=iter(_chart_bars()), syminfo=_syminfo("60"),
                         chart_data_path=path)
        rows = {}
        for candle, pv in r.run_iter():
            m = (candle.timestamp - T0) // HOUR
            rows[(m // 24, m % 24)] = dict(pv)
    for d in range(1, N_DAYS):
        assert rows[(d, 13)]["on_prev"] == _hourly(d, 11), (d, rows[(d, 13)]["on_prev"])
