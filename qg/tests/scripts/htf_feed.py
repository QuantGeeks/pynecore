"""
@pyne
"""
from pynecore.lib import barmerge, close, high, plot, request, script, syminfo


@script.indicator("Same-symbol HTF with a supplied feed")
def main():
    tf = "1D"
    plot(request.security(syminfo.tickerid, tf, close[1], lookahead=barmerge.lookahead_on), "on_prev")
    plot(request.security(syminfo.tickerid, tf, high[1], lookahead=barmerge.lookahead_on), "on_high_prev")
    plot(request.security(syminfo.tickerid, tf, close[1], gaps=barmerge.gaps_on,
                          lookahead=barmerge.lookahead_on), "on_prev_gaps")
    plot(request.security(syminfo.tickerid, tf, close, lookahead=barmerge.lookahead_off), "off_cur")
    plot(request.security(syminfo.tickerid, tf, close[1], lookahead=barmerge.lookahead_off), "off_prev")
    plot(request.security(syminfo.tickerid, tf, close, gaps=barmerge.gaps_on,
                          lookahead=barmerge.lookahead_off), "off_cur_gaps")
