"""
@pyne
"""
from pynecore.lib import bar_index, close, label, line, script
from pynecore.types import Line, Persistent


@script.indicator("Journal live ticks", "jlv", overlay=True)
def main():
    if bar_index == 0:
        ln: Persistent[Line] = line.new(0, 0.0, 0, close)
    # The forming bar re-points the line at the latest price on every executed
    # tick; only y2 differs between a bar's ticks, so the journal's update is a
    # single-field diff.
    line.set_xy2(ln, bar_index, close)
    # A drawing whose lifetime is one run: the next tick's rollback deletes the
    # previous tick's copy and the re-run creates a fresh one.
    label.new(bar_index, close, "tick")
