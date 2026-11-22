"""TradingView's buffer semantics for ``max_bars_back`` (RE10143's manual):
the declaration, the function and the engine default set the INITIAL buffer
size; on historical bars the runtime GROWS an under-sized buffer (the runner
restarts with a larger one), so a run with a small limit equals the run with a
large-enough buffer from the start. RE10143 stays where TradingView raises it:
a realtime read beyond the buffer, a read beyond the hard cap (5000 for a
general series, 10000 for the open/high/low/close/time builtins), or a growth
request no restart can serve (a runtime shrink that re-applies on the replay).
Never a silent wrong value: the moving-length machines that used to return na
for ~20 bars after the length grew (the history the read needed was already
discarded) now grow instead."""
import itertools
import sys
from pathlib import Path

import pytest

from pynecore.core import runner_state
from pynecore.core.script_runner import LIVE_TRANSITION, ScriptRunner
from pynecore.qg_gates.common import default_syminfo, synthetic_bars
from pynecore.types.ohlcv import OHLCV

SCRIPTS = Path(__file__).resolve().parent / "scripts"


def _run(script: Path, bars, state=None, **kwargs):
    """Run ``script`` over ``bars``; a ``runner_state`` runs it under the
    engine default the state carries. Returns the list of plot dicts."""
    sys.modules.pop(script.stem, None)
    if state is None:
        runner = ScriptRunner(script_path=script, ohlcv_iter=iter(bars),
                              syminfo=default_syminfo(), **kwargs)
    else:
        runner = runner_state.create_runner(
            state, script_path=script, ohlcv_iter=iter(bars),
            syminfo=default_syminfo(), **kwargs)
    return [dict(plot) for _candle, plot in runner.run_iter()]


def _run_state(script: Path, bars, engine_default: int, **kwargs):
    state = runner_state.new_runner_state(max_bars_back_default=engine_default)
    try:
        runner_state.activate(state)
        return _run(script, bars, state, **kwargs)
    finally:
        runner_state.discard(state)


def _assert_same_run(got, expected):
    """Row-for-row equality, na (nan) equal to na."""
    assert len(got) == len(expected)
    for g_row, e_row in zip(got, expected):
        assert g_row.keys() == e_row.keys()
        for k in g_row:
            g, e = g_row[k], e_row[k]
            assert (g != g and e != e) or g == e, (k, g, e)


def __test_a_deep_read_grows_the_buffer_on_historical_bars__():
    # declared 5, read at 6: TradingView restarts with a bigger buffer, so the
    # read is na through bar 5 and serves the value six bars back from bar 6
    bars = synthetic_bars(7, 9)
    out = _run(SCRIPTS / "mbb_tv_declared_grow.py", bars)
    assert all(v["v"] != v["v"] for v in out[:6])
    assert [v["v"] for v in out[6:]] == [b.close for b in bars[:3]]


def __test_the_builtin_close_history_reaches_ten_thousand_bars__():
    # Under the plain 5000 default close[6000] grows close's buffer (the
    # OHLCV builtins keep up to 10000 bars) and serves the value from bar 6000
    bars = synthetic_bars(11, 6002)
    out = _run(SCRIPTS / "mbb_tv_close6000.py", bars)
    assert all(v["v"] != v["v"] for v in out[:6000])
    assert [v["v"] for v in out[6000:]] == [b.close for b in bars[:2]]


def __test_a_moving_length_matches_the_large_buffer_run_sma__():
    # engine default 10 vs the plain run: ta.sma over a length that grows 5 ->
    # 30 at bar 100 computes identically, the rolling-sum machine included
    bars = synthetic_bars(7, 200)
    expected = _run(SCRIPTS / "mbb_tv_dyn_sma.py", bars)
    got = _run_state(SCRIPTS / "mbb_tv_dyn_sma.py", bars, 10)
    _assert_same_run(got, expected)

    # the same body under a small DECLARED limit (10)
    declared = SCRIPTS / "mbb_tv_dyn_sma_declared.py"
    expected = _run(SCRIPTS / "mbb_tv_dyn_sma.py", bars)  # 5000 default
    got = _run(declared, bars)
    _assert_same_run(got, expected)


def __test_a_moving_length_matches_the_large_buffer_run_windows__():
    # wma / percentrank / stdev / math.sum: the slice and machine walks that
    # crashed with IndexError now compute identically to the large-buffer run
    bars = synthetic_bars(7, 200)
    script = SCRIPTS / "mbb_tv_dyn_window.py"
    expected = _run(script, bars)
    got = _run_state(script, bars, 10)
    _assert_same_run(got, expected)


def __test_a_moving_length_matches_the_large_buffer_run_change_roc_median__():
    # the three that silently returned na for ~20 bars after the length grew
    bars = synthetic_bars(7, 200)
    script = SCRIPTS / "mbb_tv_dyn_trio.py"
    expected = _run(script, bars)
    got = _run_state(script, bars, 10)
    _assert_same_run(got, expected)
    # the silent-na defect: at bar 100 the change must already compute against
    # the close of bar 70, not stay na waiting for new history
    assert got[100]["ch"] == bars[100].close - bars[70].close


def __test_alma_computes_under_a_small_declared_limit__():
    # declared 50, length 200: the read at offset 199 grows the buffer instead
    # of erroring on bar 0, and the whole run matches the undeclared one
    bars = synthetic_bars(7, 260)
    expected = _run(SCRIPTS / "mbb_tv_alma.py", bars)
    out = _run(SCRIPTS / "mbb_tv_alma.py", bars)
    assert len(out) == 260
    assert out[199]["a"] == out[199]["a"]  # computes from bar 199 on
    _assert_same_run(out, expected)


def __test_a_runtime_shrink_that_outruns_growth_raises__():
    # max_bars_back(s, 2) every bar, read at 11 under engine default 10:
    # growth learns 11 and restarts ONCE, the replay re-shrinks, and the
    # second request makes no progress — RE10143, the restart loop's exit
    bars = synthetic_bars(7, 8)
    script = SCRIPTS / "mbb_tv_shrink_loop.py"
    state = runner_state.new_runner_state(max_bars_back_default=10)
    try:
        runner_state.activate(state)
        sys.modules.pop(script.stem, None)
        runner = runner_state.create_runner(
            state, script_path=script, ohlcv_iter=iter(bars),
            syminfo=default_syminfo())
        with pytest.raises(RuntimeError) as e:
            for _ in runner.run_iter():
                pass
        assert str(e.value) == ("The requested historical offset (11) is beyond "
                                "the historical buffer's limit (2)")
        # exactly one restart served the first request; the second made no
        # progress and errored instead of looping
        assert runner._growth_restarts == 1
    finally:
        runner_state.discard(state)


def __test_a_realtime_read_beyond_the_limit_raises__():
    # no buffer growth on realtime bars: the first live tick's close[6] under
    # a declared 5 raises TradingView's RE10143
    base = 1_704_067_200_000

    def bar(ts, close_, closed):
        return OHLCV(timestamp=ts, open=close_, high=close_ + 1.0, low=close_ - 1.0,
                     close=close_, volume=1000.0, is_closed=closed)

    feed = itertools.chain(
        [bar(base + i * 60_000, 100.0 + i, True) for i in range(8)],
        [LIVE_TRANSITION],
        [bar(base + 8 * 60_000, 108.5, False)])
    with pytest.raises(RuntimeError) as e:
        _run(SCRIPTS / "mbb_tv_realtime.py", feed, live=True)
    assert str(e.value) == ("The requested historical offset (6) is beyond "
                            "the historical buffer's limit (5)")
