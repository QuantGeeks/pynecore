"""
@pyne
"""
from pynecore.lib import script, close, plot
from pynecore.types import Persistent, IBPersistent


@script.indicator("Intrabar var varip")
def main():
    n: Persistent[int] = 0
    total: Persistent[float] = 0.0
    runs: IBPersistent[int] = 0
    n += 1
    total += close
    runs += 1
    plot(n, "n")
    plot(total, "total")
    plot(runs, "runs")
