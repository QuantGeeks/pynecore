"""
@pyne
"""
from pynecore.lib import input, plot, script


@script.indicator("Int accumulation")
def main(n=input.int(3, "N")):
    f = 1
    for i in range(300):
        f = f * (n + 10)
    plot(f, "f")
    plot(-f, "g")
