"""
@pyne
"""
from pynecore.lib import bar_index, color, line, script
from pynecore.types import Line, Persistent


@script.indicator("Journal cost", "jcost", overlay=True)
def main():
    if bar_index == 0:
        a: Persistent[Line] = line.new(0, 100.0, 5, 110.0)
        b: Persistent[Line] = line.new(1, 100.0, 6, 110.0)
    if bar_index == 1:
        # only b changes on bar 1; a must not be re-serialized by the drain
        line.set_color(b, color.green)
