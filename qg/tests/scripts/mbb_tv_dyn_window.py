"""
@pyne
"""
from pynecore.lib import bar_index, close, math, script, ta


@script.indicator("mbb tv dyn window", "mbbtv6", overlay=True)
def main():
    # The window walkers that read the buffer as a slice or through the
    # rolling-sum machine: wma, percentrank, stdev and math.sum all crashed
    # with IndexError when the length grew past a small limit.
    length = 5 if bar_index < 100 else 30
    return {"wma": ta.wma(close, length),
            "pr": ta.percentrank(close, length),
            "sd": ta.stdev(close, length),
            "ms": math.sum(close, length)}
