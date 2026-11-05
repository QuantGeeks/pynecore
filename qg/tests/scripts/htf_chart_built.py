"""
@pyne
"""
from pynecore.lib import barmerge, close, plot, request, script, syminfo


@script.indicator("Same-symbol intraday HTF, no supplied feed")
def main():
    plot(request.security(syminfo.tickerid, "240", close[1], lookahead=barmerge.lookahead_on), "on_prev")
