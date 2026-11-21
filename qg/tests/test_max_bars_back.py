"""The series history limit is honored from all three places it can come
from: the script declaration (``indicator(max_bars_back=)`` sizes every
series), the ``max_bars_back(var, num)`` function (statement form lowered to
the slot's setter), and the host's engine default
(``new_runner_state(max_bars_back_default=)``). A read past the limit raises
TradingView's runtime error (RE10143), never a silently wrong value; a read
at exactly the limit is legal. The ``ta.*`` machines grow the source buffer
past the engine default, so a length beyond it still computes."""
import sys
from pathlib import Path

import pytest

from pynecore.core import runner_state
from pynecore.core.script_runner import ScriptRunner
from pynecore.qg_gates.common import default_syminfo, synthetic_bars

SCRIPTS = Path(__file__).resolve().parent / "scripts"


def _run(script: Path, bars=None, state=None):
    sys.modules.pop(script.stem, None)
    runner = ScriptRunner(script_path=script,
                          ohlcv_iter=iter(bars if bars is not None
                                          else synthetic_bars(11, 8)),
                          syminfo=default_syminfo())
    return [dict(plot_data) for _candle, plot_data in runner.run_iter()]


def __test_the_declaration_sizes_every_series__():
    bars = synthetic_bars(11, 8)
    out = _run(SCRIPTS / "mbb_declared_within.py", bars)
    # close[5] is the deepest legal read: na for the first five bars, then the
    # value five bars back
    assert all(v["v"] != v["v"] for v in out[:5])
    assert [v["v"] for v in out[5:]] == [b.close for b in bars[:3]]


def __test_a_read_past_the_declared_limit_raises__():
    with pytest.raises(RuntimeError) as e:
        _run(SCRIPTS / "mbb_declared_beyond.py")
    assert str(e.value) == ("The requested historical offset (6) is beyond "
                            "the historical buffer's limit (5)")


def __test_the_function_form_resizes_the_series__():
    bars = synthetic_bars(11, 8)
    with pytest.raises(RuntimeError) as e:
        _run(SCRIPTS / "mbb_runtime_fn.py", bars)
    assert str(e.value) == ("The requested historical offset (3) is beyond "
                            "the historical buffer's limit (2)")


def __test_the_engine_default_bounds_the_runner__():
    script = SCRIPTS / "mbb_engine_default.py"
    # without a state the 5000 default serves the read: the script runs to the
    # end (close[4] and close[5] are both within it)
    bars = synthetic_bars(11, 8)
    out = _run(script, bars)
    # bar 6 reads close[4] -> bars[2]; bar 7's guarded read is close[5] -> bars[2]
    assert [v["v"] for v in out[6:]] == [bars[2].close, bars[2].close]

    # with the engine default at 4 the same script raises one past it
    sys.modules.pop(script.stem, None)
    state = runner_state.new_runner_state(max_bars_back_default=4)
    try:
        runner_state.activate(state)
        with pytest.raises(RuntimeError) as e:
            _run(script, bars)
        assert str(e.value) == ("The requested historical offset (5) is "
                                "beyond the historical buffer's limit (4)")
    finally:
        runner_state.discard(state)


def __test_ta_machines_grow_the_source_past_the_engine_default__():
    script = SCRIPTS / "mbb_ta_grow.py"
    bars = synthetic_bars(11, 8)
    state = runner_state.new_runner_state(max_bars_back_default=4)
    try:
        runner_state.activate(state)
        out = _run(script, bars)
        # ta.change(close, 6) grows close past the engine default: the change
        # is na for six bars, then computes
        assert all(v["ch"] != v["ch"] for v in out[:6])
        assert out[6]["ch"] == bars[6].close - bars[0].close
        assert out[7]["ch"] == bars[7].close - bars[1].close
    finally:
        runner_state.discard(state)


def __test_an_out_of_range_engine_default_is_refused__():
    with pytest.raises(ValueError, match="max_bars_back_default"):
        runner_state.new_runner_state(max_bars_back_default=5001)
