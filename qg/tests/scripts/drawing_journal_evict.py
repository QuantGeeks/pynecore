"""
@pyne
"""
from pynecore.lib import bar_index, close, label, line, script


@script.indicator("Journal eviction", "jev", overlay=True,
                  max_lines_count=3, max_labels_count=2)
def main():
    # A fresh line and label every bar: past the caps the registries evict the
    # oldest (FIFO), so the journal sees a create and a delete in the same bar.
    line.new(bar_index, 0.0, bar_index, close)
    label.new(bar_index, close, "b")
