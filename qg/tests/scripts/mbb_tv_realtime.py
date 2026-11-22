"""
@pyne
"""
from pynecore.lib import bar_index, barstate, close, script


@script.indicator("mbb tv realtime", "mbbtv9", overlay=True, max_bars_back=5)
def main():
    # Historical bars stay shallow; the first realtime tick reads one past the
    # limit, where TradingView raises RE10143 (no buffer growth on realtime
    # bars).
    if barstate.isrealtime:
        return {"v": close[6]}
    return {"v": close[0]}
