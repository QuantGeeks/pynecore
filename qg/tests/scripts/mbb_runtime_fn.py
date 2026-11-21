"""
@pyne
"""
from pynecore.lib import bar_index, close, max_bars_back, script
from pynecore.types import Series


@script.indicator("mbb runtime function", "mbbf", overlay=True)
def main():
    s: Series[float] = close
    if bar_index == 0:
        # statement form on a series name: lowered to the slot's setter
        max_bars_back(s, 2)
    if bar_index == 7:
        return {"v": s[3]}
    return {"v": s[2]}
