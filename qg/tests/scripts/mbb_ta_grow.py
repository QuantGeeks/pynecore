"""
@pyne
"""
from pynecore.lib import close, script, ta


@script.indicator("mbb ta grow", "mbbt", overlay=True)
def main():
    # ta.change grows the source buffer past the engine default so the read
    # stays addressable; with the default at 4 this must still produce values
    return {"ch": ta.change(close, 6)}
