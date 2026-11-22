"""
@pyne
"""
from pynecore.lib import close, script


@script.indicator("mbb tv close6000", "mbbtv2", overlay=True)
def main():
    # The builtin close history reaches 10000 bars on TradingView; under the
    # 5000 default this read grows the buffer (restart) and serves the value
    # from bar 6000 on.
    return {"v": close[6000]}
