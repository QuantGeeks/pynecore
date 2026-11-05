"""
@pyne
"""
from pynecore.lib import barmerge, bar_index, earnings, plot, request, script, syminfo


@script.indicator("Earnings requested only on even bars")
def main():
    v = float("nan")
    if bar_index % 2 == 0:
        v = request.earnings(syminfo.tickerid, earnings.actual, gaps=barmerge.gaps_on)
    plot(v, "even_only")
