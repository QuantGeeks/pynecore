"""
@pyne
"""
from pynecore.lib import close, max_bars_back, script
from pynecore.types import Series


@script.indicator("mbb tv shrink loop", "mbbtv8", overlay=True)
def main():
    # A runtime shrink to 2 every bar, then a read at 11: growth learns 11 and
    # restarts once, but the shrink re-applies on the replay, so the second
    # growth request cannot make progress — TradingView's runtime error.
    s: Series[float] = close
    max_bars_back(s, 2)
    return {"v": s[11]}
