"""
@pyne
"""
from pynecore.lib import barmerge, dividends, earnings, plot, request, script, splits, syminfo


@script.indicator("Earnings, dividends and splits")
def main():
    t = syminfo.tickerid
    plot(request.earnings(t), "e_default")
    plot(request.earnings(t, earnings.estimate), "e_estimate")
    plot(request.earnings(t, earnings.standardized), "e_standardized")
    plot(request.earnings(t, earnings.actual, gaps=barmerge.gaps_on), "e_off_gaps")
    plot(request.earnings(t, earnings.actual, lookahead=barmerge.lookahead_on), "e_on")
    plot(request.earnings(t, earnings.actual, gaps=barmerge.gaps_on, lookahead=barmerge.lookahead_on), "e_on_gaps")
    plot(request.dividends(t), "d_default")
    plot(request.dividends(t, dividends.net), "d_net")
    plot(request.splits(t, splits.numerator), "s_num")
    plot(request.splits(t, splits.denominator, gaps=barmerge.gaps_on), "s_den_gaps")
    plot(request.earnings("NYSE:OTHER", earnings.actual, ignore_invalid_symbol=True), "e_other")
