"""
@pyne
"""
from pynecore.lib import barmerge, close, hour, minute, plot, request, script, syminfo


@script.indicator("lookahead_on daily context, dev-batch extended session")
def main():
    tf = "1D"
    # Same burn as htf_devbatch_repeat.py, moved to the EXTENDED session's last
    # minutes (19:55..19:59): it widens the gap between one chart bar's tied
    # ring entries (the closed record and the developing one share the
    # session-close tick) so a consumer released mid-group by the first entry
    # is a reproducible wrong read, not scheduler luck. The burn touches no
    # plot.
    burn = 0.0
    if hour == 19 and minute >= 55:
        for i in range(1, 9000):
            burn += close * i * 1e-12
    plot(request.security(syminfo.tickerid, tf, close, lookahead=barmerge.lookahead_on), "dev")
    plot(request.security(syminfo.tickerid, tf, close[1], lookahead=barmerge.lookahead_on), "prev")
