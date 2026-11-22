"""
@pyne
"""
from pynecore.lib import bar_index, close, script, ta


@script.indicator("mbb tv dyn sma declared", "mbbtv4", overlay=True, max_bars_back=10)
def main():
    # The same moving length under a small DECLARED limit.
    length = 5 if bar_index < 100 else 30
    return {"v": ta.sma(close, length)}
