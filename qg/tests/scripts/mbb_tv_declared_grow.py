"""
@pyne
"""
from pynecore.lib import close, script


@script.indicator("mbb tv declared grow", "mbbtv1", overlay=True, max_bars_back=5)
def main():
    # One past the declared limit. TradingView grows the buffer on historical
    # bars (restart with a larger one), so the read is na until bar 6 and then
    # serves the value six bars back.
    return {"v": close[6]}
