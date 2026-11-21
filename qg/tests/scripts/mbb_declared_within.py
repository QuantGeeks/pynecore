"""
@pyne
"""
from pynecore.lib import script
from pynecore.lib import close


@script.indicator("mbb declared within", "mbbw", overlay=True, max_bars_back=5)
def main():
    # offset == the declared limit is the deepest legal read (na while the
    # history is shorter than that, the value once it is not)
    return {"v": close[5]}
