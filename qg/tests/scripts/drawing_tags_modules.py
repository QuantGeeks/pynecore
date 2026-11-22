"""
@pyne

Script for the drawing-tags cross-module test: a line from the imported
library's export next to one from this module's own call site.
"""
from pynecore.lib import bar_index, line, script
from pynecore.types import Line, Persistent

import drawing_tags_lib as dtl


@script.indicator("Drawing tags modules", "dtagm", overlay=True)
def main():
    if bar_index == 0:
        from_lib: Persistent[Line] = dtl.make()
        own: Persistent[Line] = line.new(1, 100.0, 6, 110.0)
