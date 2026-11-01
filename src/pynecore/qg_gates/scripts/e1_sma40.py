"""
@pyne
"""
from pynecore.lib import script, ta, high, low, plot


@script.indicator("E1 SMA40")
def main():
    plot(ta.sma((high + low) / 2, 40), "sma40")
