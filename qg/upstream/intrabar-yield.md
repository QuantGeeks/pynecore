# `ScriptRunner(yield_intrabar=True)`: yield after every live intra-bar tick (6.10.10-qg.7)

**PyneCore version:** 6.10.10 (measured on the fork's `6.10.10-qg.6`; upstream's live loop is the same).

## The problem (measured, synthetic)

In live mode the runner executes an intra-bar tick (`OHLCV(..., is_closed=False)`) with `var`
rollback, `barstate.isconfirmed` False and `varip` persisting: the open path
(`script_runner.py`, "Bar open (first intra-bar tick)") and the repeat path ("Subsequent
intra-bar tick"). Neither path yields. `run_iter()` yields only when a bar closes. A host that
owns the `ohlcv_iter` and drives the generator one `next()` at a time (one thread, many runners)
therefore cannot read a forming bar's values:

```python
# warm 60 bars, LIVE_TRANSITION, then ONE tick; the feeder has nothing more to give yet
f.items.append(tick._replace(is_closed=False))
next(gen)   # StopIteration: the loop ran the tick, pulled the next item, found none
```

The values exist (`lib._plot_data` right after the run, readable only from inside the
`ohlcv_iter`'s `__next__`), but control cannot return to the caller without a thread or a
coroutine. With two ticks and a close queued, one `next()` runs both ticks and yields only at the
close. The only way a single-threaded caller can use ticks is to feed them as new closed bars,
which advances the runner (every series, every `var`) once per tick.

## The change

`ScriptRunner(..., yield_intrabar: bool = False)`. With `live=True` and `yield_intrabar=True`,
each tick that executed the script yields `(candle, plot_data)` (a strategy with a position:
`(candle, plot_data, [])`) with `candle.is_closed` False, after the run and before the next
item is pulled; the per-run containers are then cleared as the closed-bar path does. The closed
bar is unchanged: it rolls back, re-runs on the final OHLCV and yields. Ticks of a script that
does not run on every tick (a strategy without `calc_on_every_tick`) execute nothing and yield
nothing. Default False: no new statement runs, the generator's behaviour is upstream's.

## Tests (`qg/tests/test_intrabar_yield.py`, synthetic bars)

* RSI+MACD and a `var`/`varip` script: 0-5 seeded ticks inside each live bar's range; each tick
  yields once with `is_closed` False, before its bar's close; every closed bar equals the run
  that saw no ticks and the batch run, bit for bit (`varip` excluded: it counts executions).
* `varip` grows by ticks+1 per bar, `var` by 1 (rollback); a tick's `var` equals its bar's.
* The last tick's values equal a batch run whose last bar is that forming bar.
* Flag off: closed bars only, equal to the tickless run.
* One tick no longer ends the generator.

Not filed (sev, 2026-10-31): nothing is pushed upstream.
