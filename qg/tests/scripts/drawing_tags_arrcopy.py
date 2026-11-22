"""
@pyne

Script for the drawing-tags array-copy guard: ``a.copy()`` on an array rides
the same stamped ``method_call('copy', ...)`` dispatch as a drawing's copy —
array.copy must never receive the tag keyword.
"""
from pynecore.core.pine_method import method_call
from pynecore.lib import array, script


@script.indicator("Drawing tags array copy", "dtaga", overlay=True)
def main():
    a = array.new_float()
    array.push(a, 1.5)
    array.push(a, 2.5)
    b = method_call('copy', a)
    return {"n": float(array.size(b)), "first": array.get(b, 0)}
