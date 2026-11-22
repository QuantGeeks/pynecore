"""
@pyne
"""
from pynecore.lib import barmerge, close, plot, request, script


@script.indicator("cross-symbol same-timeframe lookahead_on contexts")
def main():
    sym = "AMEX:OTHER"
    plot(request.security(sym, "5", close, lookahead=barmerge.lookahead_on), "on_cur")
    plot(request.security(sym, "5", close[1], lookahead=barmerge.lookahead_on), "on_prev")
    plot(request.security(sym, "5", close), "off_cur")
    plot(request.security(sym, "5", close[1]), "off_prev")
