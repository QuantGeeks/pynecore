"""
@pyne
"""
from pynecore.lib import barmerge, close, hour, minute, plot, request, script, syminfo


@script.indicator("lookahead_on daily context, dev-batch repeat")
def main():
    tf = "1D"
    # A deterministic per-step burn in each session's last minutes: it widens the
    # gap between one chart bar's tied ring entries (the closed record and the
    # developing one share the session-close tick) from one fast step to about a
    # millisecond, so a consumer released mid-group by the first entry is a
    # reproducible wrong read, not scheduler luck. The burn touches no plot.
    burn = 0.0
    if hour == 15 and minute >= 55:
        for i in range(1, 9000):
            burn += close * i * 1e-12
    plot(request.security(syminfo.tickerid, tf, close, lookahead=barmerge.lookahead_on), "dev")
    plot(request.security(syminfo.tickerid, tf, close[1], lookahead=barmerge.lookahead_on), "prev")
