"""
@pyne
"""
from pynecore.lib import bar_index, color, line, linefill, script
from pynecore.types import Line, LineFill, Persistent


@script.indicator("Journal linefill", "jfill", overlay=True)
def main():
    if bar_index == 0:
        a: Persistent[Line] = line.new(0, 100.0, 5, 110.0)
        b: Persistent[Line] = line.new(1, 100.0, 6, 110.0)
        f: Persistent[LineFill] = linefill.new(a, b, color.blue)
    if bar_index == 1:
        # the fill embeds a's serialized state (line1_state), so a's color
        # change must re-serialize the fill, not only a
        line.set_color(a, color.green)
