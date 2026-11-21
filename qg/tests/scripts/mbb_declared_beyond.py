"""
@pyne
"""
from pynecore.lib import bar_index, close, script


@script.indicator("mbb declared beyond", "mbbb", overlay=True, max_bars_back=5)
def main():
    if bar_index == 7:
        # one past the declared limit: TradingView's runtime error, not a
        # silent na
        return {"v": close[6]}
    return {"v": 0.0}
