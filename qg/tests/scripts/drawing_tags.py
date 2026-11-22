"""
@pyne
"""
from pynecore.core.pine_method import method_call
from pynecore.lib import (
    bar_index, box, chart, color, label, line, linefill, polyline, position, script, table,
)
from pynecore.types import Box, Label, Line, LineFill, Persistent, Polyline, Table


@script.indicator("Drawing tags", "dtag", overlay=True)
def main():
    if bar_index == 0:
        base: Persistent[Line] = line.new(0, 100.0, 5, 110.0, color=color.red)
        dup: Persistent[Line] = line.copy(base)
        lb: Persistent[Label] = label.new(2, 105.0, "hi")
        bx: Persistent[Box] = box.new(1, 110.0, 4, 100.0)
        pl: Persistent[Polyline] = polyline.new(
            [chart.point.from_index(0, 100.0), chart.point.from_index(1, 105.0)])
        lf: Persistent[LineFill] = linefill.new(base, dup, color.new(color.blue, 80))
        tbl: Persistent[Table] = table.new(position.top_right, 2, 2)
        table.cell(tbl, 0, 0, "A")
        # a cell whose first touch is a setter: the setter's site creates it
        table.cell_set_text(tbl, 1, 1, "B")
    if bar_index == 1:
        # the same source line of line.new as bar 0's first one? No: a second
        # call site of line.new, so a distinct tag; and a write through another
        # cell_set_text site to a cell that already exists keeps its creator's
        # tag.
        second: Persistent[Line] = line.new(1, 100.0, 6, 110.0)
        table.cell_set_text(tbl, 0, 0, "A2")
        # the METHOD form of copy, the dispatch a compiled Pine script rides:
        # stamped like the lib call, with this call site's own tag
        mth: Persistent[Line] = method_call('copy', second)
