"""
@pyne
"""
from pynecore.lib import script, ta, close, high, low, plot, input
from pynecore.types import Persistent


@script.indicator("Runner state TA")
def main(length: int = input.int(14, "Length")):
    count: Persistent[int] = 0
    count += 1
    plot(ta.sma(close, length), "sma")
    plot(ta.rsi(close, length), "rsi")
    plot(ta.stdev(close, length), "stdev")
    plot(ta.ema(close, length), "ema")
    plot(ta.highest(high, length) - ta.lowest(low, length), "range")
    plot(ta.mom(close, length), "mom")
    plot(count, "count")
