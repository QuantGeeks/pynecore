"""ScriptRunner(yield_intrabar=True): a live runner yields every intra-bar tick (is_closed False, after the
script ran, before the next pull); the ticks roll `var` back and never advance the bar; the closed bars equal
a run that never saw a tick, bit for bit.  The default (False) yields closed bars only, as upstream does."""
import random
import sys
from pathlib import Path

import pytest

from pynecore.core.script_runner import LIVE_TRANSITION, ScriptRunner
from pynecore.qg_gates.common import default_syminfo, synthetic_bars
from pynecore.types.ohlcv import OHLCV

SCRIPTS = Path(__file__).resolve().parent / "scripts"
HIST, LIVE = 120, 40


def _run(script: str, events, *, live: bool, yield_intrabar: bool = False):
    sys.modules.pop(script, None)
    runner = ScriptRunner(script_path=SCRIPTS / f"{script}.py", ohlcv_iter=iter(events), syminfo=default_syminfo(),
                          live=live, yield_intrabar=yield_intrabar, lossless_prices=True, lossless_volume=True)
    gen = runner.run_iter()
    out = []
    try:
        for item in gen:
            out.append((item[0], {k: repr(v) for k, v in item[1].items()}))
    finally:
        gen.close()
    return out


def _bars():
    return synthetic_bars(11, HIST + LIVE)


def _events(bars, seed, max_ticks=5):
    """History, the sentinel, then per live bar 0..max_ticks ticks inside the bar's range and the close."""
    rnd = random.Random(seed)
    ev, counts, last = list(bars[:HIST]) + [LIVE_TRANSITION], [], {}
    for b in bars[HIST:]:
        k = rnd.randint(0, max_ticks)
        counts.append(k)
        hi, lo = b.open, b.open
        for _ in range(k):
            px = round(rnd.uniform(b.low, b.high), 2)
            hi, lo = max(hi, px), min(lo, px)
            t = OHLCV(b.timestamp, b.open, hi, lo, px, b.volume * rnd.random(), is_closed=False)
            ev.append(t)
            last[b.timestamp] = t
        ev.append(b)
    return ev, counts, last


def _closed(rows):
    return [(c.timestamp, v) for c, v in rows if c.is_closed]


@pytest.mark.parametrize("script", ["rsi_macd", "var_varip"])
def __test_ticks_yield_once_and_closed_bars_equal_a_tickless_run__(script):
    bars = _bars()
    ev, counts, _ = _events(bars, seed=3)
    rows = _run(script, ev, live=True, yield_intrabar=True)
    ticks = [c for c, _ in rows if not c.is_closed]
    assert len(ticks) == sum(counts)
    assert len([1 for c, _ in rows if c.is_closed]) == HIST + LIVE
    # order: the ticks of a bar come before its close, once each
    live_rows = rows[HIST:]
    pos = 0
    for b, k in zip(bars[HIST:], counts):
        chunk = live_rows[pos:pos + k + 1]
        assert [c.is_closed for c, _ in chunk] == [False] * k + [True]
        assert {c.timestamp for c, _ in chunk} == {b.timestamp}
        pos += k + 1
    tickless = _run(script, bars[:HIST] + [LIVE_TRANSITION] + bars[HIST:], live=True)
    batch = _run(script, bars, live=False)
    got = _closed(rows)
    if script == "var_varip":  # varip counts executions, which ticks add to by design
        strip = lambda rs: [(t, {k: v for k, v in d.items() if k != "runs"}) for t, d in rs]
        got, tickless, batch = strip(got), strip(tickless), strip(batch)
    assert got == _closed(tickless) == _closed(batch)


def __test_varip_persists_across_ticks_and_var_rolls_back__():
    bars = _bars()
    ev, counts, _ = _events(bars, seed=5)
    rows = _run("var_varip", ev, live=True, yield_intrabar=True)
    closed = [d for c, d in rows if c.is_closed]
    for i in range(HIST + 1, HIST + LIVE):
        assert int(float(closed[i]["runs"])) - int(float(closed[i - 1]["runs"])) == counts[i - HIST] + 1
        assert int(float(closed[i]["n"])) - int(float(closed[i - 1]["n"])) == 1  # var: ticks rolled back
    for c, d in [r for r in rows if not r[0].is_closed]:
        assert d["n"] == closed[HIST + [b.timestamp for b in bars[HIST:]].index(c.timestamp)]["n"]


def __test_last_tick_equals_a_batch_run_ending_on_that_bar__():
    bars = _bars()
    ev, counts, last = _events(bars, seed=7, max_ticks=4)
    rows = _run("rsi_macd", ev, live=True, yield_intrabar=True)
    checked = 0
    for j in range(HIST, HIST + LIVE):
        ts = bars[j].timestamp
        if ts not in last:
            continue
        t = last[ts]
        last_tick = [v for c, v in rows if not c.is_closed and c.timestamp == ts][-1]
        batch = _run("rsi_macd", bars[:j] + [t._replace(is_closed=True)], live=False)
        assert last_tick == batch[-1][1], ts
        checked += 1
    assert checked >= 20


def __test_default_yields_closed_bars_only__():
    bars = _bars()
    ev, _, _ = _events(bars, seed=3)
    rows = _run("rsi_macd", ev, live=True)
    assert all(c.is_closed for c, _ in rows) and len(rows) == HIST + LIVE
    assert _closed(rows) == _closed(_run("rsi_macd", bars[:HIST] + [LIVE_TRANSITION] + bars[HIST:], live=True))


def __test_a_tick_no_longer_ends_the_runner__():
    bars = _bars()
    ev = bars[:HIST] + [LIVE_TRANSITION, bars[HIST]._replace(is_closed=False)]
    sys.modules.pop("rsi_macd", None)
    runner = ScriptRunner(script_path=SCRIPTS / "rsi_macd.py", ohlcv_iter=iter(ev), syminfo=default_syminfo(),
                          live=True, yield_intrabar=True, lossless_prices=True, lossless_volume=True)
    gen = runner.run_iter()
    for _ in range(HIST):
        next(gen)
    c, _p = next(gen)  # the tick yields; the runner is suspended, not ended
    assert c.is_closed is False
    gen.close()
