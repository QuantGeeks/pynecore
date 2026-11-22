"""
@pyne
"""
from pynecore.lib import bar_index, box, color, label, line, linefill, script

from pynecore.types import Box, Label, Line, LineFill, Persistent


@script.indicator("Tag identity B", "tgvb", overlay=True)
def main():
    if bar_index == 0:
        a: Persistent[Line] = line.new(0, 100.0, 5, 110.0, color=color.red)
        # A version change: one creation site ADDED above the shared ones below
        # renumbers every later tag of the module (drawing_tags.py's stability
        # caveat) — a site that never runs still takes its number, so the two
        # versions create the SAME drawings with shifted tags.
        if bar_index == 5:
            never: Persistent[Box] = box.new(9, 90.0, 12, 80.0)
        b: Persistent[Line] = line.copy(a)
        lb: Persistent[Label] = label.new(2, 105.0, "hi")
        bx: Persistent[Box] = box.new(1, 110.0, 4, 100.0)
        lf: Persistent[LineFill] = linefill.new(a, b, color.new(color.blue, 80))
