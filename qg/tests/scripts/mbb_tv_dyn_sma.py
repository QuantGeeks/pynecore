"""
@pyne
"""
from pynecore.lib import bar_index, close, script, ta


@script.indicator("mbb tv dyn sma", "mbbtv3", overlay=True)
def main():
    # A length that grows past a small buffer limit mid-run: the moving-length
    # machines must keep computing, matching the run with a large buffer.
    length = 5 if bar_index < 100 else 30
    return {"v": ta.sma(close, length)}
