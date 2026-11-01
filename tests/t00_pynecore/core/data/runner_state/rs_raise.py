"""
@pyne
"""
from pynecore.lib import script, ta, close, high, low, plot, input, bar_index
from pynecore.types import Persistent


@script.indicator("Runner state raise")
def main(length: int = input.int(14, "Length")):
    if bar_index == 250:
        raise ValueError("rs_raise at 250")
    count: Persistent[int] = 0
    count += 1
    plot(ta.sma(close, length), "sma")
    plot(ta.rsi(close, length), "rsi")
    plot(ta.stdev(close, length), "stdev")
    plot(ta.ema(close, length), "ema")
    plot(ta.highest(high, length) - ta.lowest(low, length), "range")
    plot(count, "count")
