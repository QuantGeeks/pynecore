# math.sum / ta.sma: a TradingView 1m export equals a re-summed window, not the compensated accumulator (6.10.10)

**PyneCore version:** 6.10.10 (the behaviour is the one whose 6.10.4 release note says the
compensated accumulator matches TradingView "bit for bit", measured there on EURUSD 60m).

## Minimal reproduction (synthetic data only)

```python
import random
from pynecore.lib import script, ta, plot, high, low
from pynecore.types.ohlcv import OHLCV
from pynecore.core.script_runner import ScriptRunner


def bars(n=3000):
    rnd, out, px = random.Random(20261031), [], 500.0
    for i in range(n):
        o = round(px, 2)
        c = round(o + rnd.uniform(-0.6, 0.6), 2)
        h = round(max(o, c) + rnd.uniform(0, 0.3), 2)
        l = round(min(o, c) - rnd.uniform(0, 0.3), 2)
        out.append(OHLCV(1779802200000 + 60000 * i, o, h, l, c,
                         float(rnd.randint(50000, 500000))))
        px = c
    return out


@script.indicator("sma re-sum repro")
def main():
    plot(ta.sma((high + low) / 2, 40), "sma40")


rows = [dict(p) for _c, p in ScriptRunner(script_path=Path(__file__), ohlcv_iter=bars()).run_iter()]
hl2 = [(b.high + b.low) / 2 for b in bars()]
match = sum(rows[i]["sma40"] == sum(hl2[i - 39:i + 1]) / 40 for i in range(39, len(rows)))
print(match, "of", len(rows) - 39, "bars equal the re-summed window")
```

Run with `PYNE_SAVE_SCRIPT_TOML=0`. On this synthetic series the printed count is
**407 of 2961** post-warm-up bars: `ta.sma`'s rolling compensated sum equals a plain
re-summed window (`sum(window) / length`, recomputed each bar, oldest first) on less than
14% of bars, and differs from it in the last bits on the rest. The two are different
accumulators, not two spellings of one.

## Observed vs expected

Against a **TradingView "Download chart data" export** (our numbers only; no TradingView
data is attached or offered here), for `ta.sma(hl2, 40)` over a 1-minute equity series of
41,340 bars, comparing every bar after a 1,500-bar warm-up:

| machine | bars equal to TradingView's export |
|---|---|
| re-summed window (`sum` of the last 40 values, each bar) | 41,301 of 41,301 |
| PyneCore 6.10.10 compensated accumulator | 428 of 41,301 |
| plain running sum (add new, subtract evicted) | 661 of 41,301 |

Expected — per the 6.10.4 release note — was that the compensated accumulator reproduces
TradingView bit for bit. Instead the export equals a re-summed window on 100% of bars.

## The question

Is TradingView's accumulator data- or timeframe-dependent? The release note's "bit for bit"
was measured on EURUSD 60m; our divergence is on 1-minute equity bars. If the engine keeps
one accumulator across both, PyneCore's and TradingView's should agree on our export too,
and they do not. We can share the comparison method (it is the table above applied to any
export you take); we cannot attach the export itself.

## What we did about it

We carry an opt-in `window` mode for `math.sum` (a `WindowSumMachine` that recomputes the
plain oldest-first sum of the last `length` non-na values each bar), leaving the default
compensated machine untouched, and are happy to contribute it — with its synthetic test —
if you want it as a setting or as evidence in pinning the accumulator down.
