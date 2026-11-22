"""
@pyne
"""
from pynecore.lib import bar_index, close, script, ta


@script.indicator("mbb tv dyn trio", "mbbtv5", overlay=True)
def main():
    # change / roc / median silently returned na for ~20 bars after the length
    # grew under a small limit (the history the read needed was discarded) —
    # never a silent wrong value.
    length = 5 if bar_index < 100 else 30
    return {"ch": ta.change(close, length),
            "roc": ta.roc(close, length),
            "med": ta.median(close, length)}
