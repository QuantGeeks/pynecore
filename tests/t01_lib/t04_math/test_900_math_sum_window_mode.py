"""
@pyne

Window re-sum mode for ``math.sum`` (QuantGeeks fork; spec 9.2, E1). With the mode set to
"window", a call site created afterwards returns the plain oldest-first sum of its last
``length`` non-na values, recomputed each bar; ``ta.sma``, ``ta.vwma`` and ``ta.stdev`` follow.
"""
import math as _m
import random as _r
from pynecore.lib import close, high, low, math, ta, plot, script
from pynecore.types.ohlcv import OHLCV
from pynecore.core import rolling_sum
from pynecore.core.window_sum import WindowSumMachine, window_sum_step


@script.indicator("Math Sum Window Mode")
def main():
    plot(ta.sma((high + low) / 2, 40), "sma40")
    plot(math.sum(close, 7), "sum7")
    plot(ta.vwma(close, 20), "vwma20")
    plot(ta.stdev(close, 20), "stdev20")


def __test_helper_bars(n: int = 3000) -> list:
    rnd, out, px = _r.Random(20261031), [], 500.0
    for i in range(n):
        o = round(px, 2)
        c = round(o + rnd.uniform(-0.6, 0.6), 2)
        h, l = round(max(o, c) + rnd.uniform(0, 0.3), 2), round(min(o, c) - rnd.uniform(0, 0.3), 2)
        out.append(OHLCV(1779802200000 + 60000 * i, o, h, l, c, float(rnd.randint(50000, 500000))))
        px = c
    return out


def __test_helper_run(runner, mode: str):
    bars = __test_helper_bars()
    rolling_sum.set_sum_mode(mode)
    try:
        return bars, [dict(p) for _c, p in runner(bars).run_iter()]
    finally:
        rolling_sum.set_sum_mode("compensated")


def __test_window_mode_is_the_plain_window_sum__(runner):
    """ sma, math.sum, vwma and stdev equal the re-summed window on every bar """
    bars, rows = __test_helper_run(runner, "window")
    hl2 = [(b.high + b.low) / 2 for b in bars]
    cl, vo = [b.close for b in bars], [b.volume for b in bars]
    cv = [b.close * b.volume for b in bars]
    assert _m.isnan(rows[38]["sma40"]) and not _m.isnan(rows[39]["sma40"])
    for i, p in enumerate(rows):
        if i >= 39:
            assert p["sma40"] == sum(hl2[i - 39:i + 1]) / 40, i
        if i >= 6:
            assert p["sum7"] == sum(cl[i - 6:i + 1]), i
        if i >= 19:
            assert p["vwma20"] == (sum(cv[i - 19:i + 1]) / 20) / (sum(vo[i - 19:i + 1]) / 20), i
            m = sum(cl[i - 19:i + 1]) / 20
            assert p["stdev20"] == _m.sqrt(max(0.0, sum(c * c for c in cl[i - 19:i + 1]) / 20 - m * m)), i


def __test_compensated_mode_differs_from_the_re_sum__(runner):
    """ Negative control: the default machine is not the re-sum on these bars """
    bars, rows = __test_helper_run(runner, "compensated")
    hl2 = [(b.high + b.low) / 2 for b in bars]
    assert any(rows[i]["sma40"] != sum(hl2[i - 39:i + 1]) / 40 for i in range(39, len(rows)))


def __test_sum_mode_setting__():
    """ Compensated by default; only the two named modes are accepted """
    assert rolling_sum.get_sum_mode() == "compensated"
    assert rolling_sum.SUM_MODES == ("compensated", "window")
    try:
        rolling_sum.set_sum_mode("kahan")
    except ValueError as e:
        assert str(e) == "sum mode must be one of ('compensated', 'window'), got 'kahan'"
    else:
        raise AssertionError("an unknown mode was accepted")
    assert rolling_sum.get_sum_mode() == "compensated"


def __test_window_machine_na_length_and_rollback__():
    """ na bars are not stored, a shorter length reads the newest values, a snapshot restores exactly """
    m = WindowSumMachine()
    assert _m.isnan(window_sum_step(m, 1.0, 3))
    window_sum_step(m, 2.0, 3)
    assert window_sum_step(m, 3.0, 3) == 6.0
    tok = m.__pyne_snapshot__()
    assert window_sum_step(m, 10.0, 3) == 15.0
    m.__pyne_restore__(tok)
    assert window_sum_step(m, 4.0, 3) == 9.0
    assert _m.isnan(window_sum_step(m, float("nan"), 3))
    assert window_sum_step(m, 5.0, 3) == 12.0
    assert window_sum_step(m, 6.0, 2) == 11.0
    assert window_sum_step(m, 7.0, 3) == 18.0
