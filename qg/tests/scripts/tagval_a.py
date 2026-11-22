"""
@pyne
"""
from pynecore.lib import bar_index, box, color, label, line, linefill, script

from pynecore.types import Box, Label, Line, LineFill, Persistent


@script.indicator("Tag identity A", "tgva", overlay=True)
def main():
    if bar_index == 0:
        a: Persistent[Line] = line.new(0, 100.0, 5, 110.0, color=color.red)
        b: Persistent[Line] = line.copy(a)
        lb: Persistent[Label] = label.new(2, 105.0, "hi")
        bx: Persistent[Box] = box.new(1, 110.0, 4, 100.0)
        lf: Persistent[LineFill] = linefill.new(a, b, color.new(color.blue, 80))
