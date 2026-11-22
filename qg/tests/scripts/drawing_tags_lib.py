"""
@pyne

Library module for the drawing-tags cross-module test: one ``line.new`` site
inside an export, so the library module and the importing script each count a
creation site of their own.
"""
from pynecore.core.pine_export import Exported, export
from pynecore.lib import line, script
from pynecore.types import Line

make = Exported()


@script.library("Drawing Tags Lib")
def main():
    @export
    def make() -> Line:
        return line.new(0, 100.0, 5, 110.0)

    return {}
