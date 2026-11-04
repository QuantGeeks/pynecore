"""
@pyne
"""
from pynecore.lib import script, ta, close, plot


@script.indicator("Intrabar RSI MACD")
def main():
    plot(ta.rsi(close, 14), "rsi")
    macd_line, signal, hist = ta.macd(close, 12, 26, 9)
    plot(macd_line, "macd")
    plot(signal, "signal")
    plot(hist, "hist")
