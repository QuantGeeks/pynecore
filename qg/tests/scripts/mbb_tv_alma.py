"""
@pyne
"""
from pynecore.lib import close, script, ta


@script.indicator("mbb tv alma", "mbbtv7", overlay=True, max_bars_back=50)
def main():
    # alma reads source[length - 1] with no capacity seed of its own; under a
    # small declared limit the buffer grows instead of erroring on bar 0.
    return {"a": ta.alma(close, 200, 0.85, 6)}
