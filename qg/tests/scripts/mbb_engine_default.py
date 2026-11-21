"""
@pyne
"""
from pynecore.lib import bar_index, close, script


@script.indicator("mbb engine default", "mbbe", overlay=True)
def main():
    # sized by the host's engine default, not the 5000 class default: a read
    # one past it is the runtime error
    if bar_index == 7:
        return {"v": close[5]}
    return {"v": close[4]}
