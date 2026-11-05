"""
@pyne
"""
from pynecore.lib import bar_index, close, input, label, line, plot, script


@script.indicator("Int inputs and drawings", overlay=True)
def main(width=input.int(2, "Width"), offset=input.int(3, "Offset"), bars=input.int(10, "Bars", minval=1)):
    plot(width, "width")
    if bar_index == 20:
        line.new(bar_index - bars, close, bar_index + offset, close, width=width)
        # the Python spelling of the values themselves: an int prints 2, a double 2.0
        label.new(bar_index + offset, close, f"{width}|{offset * 2 + width}|{bars}")
