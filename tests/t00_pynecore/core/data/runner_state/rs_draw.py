"""
@pyne
"""
from pynecore.lib import script, bar_index, high, low, close, label, line, plot


@script.indicator("Runner state drawings", overlay=True, max_labels_count=500)
def main():
    if bar_index % 5 == 0:
        label.new(bar_index, high, "h")
    if bar_index % 10 == 0:
        line.new(bar_index - 1, low, bar_index, high)
    plot(close, "close")
