# Design: honoring max_bars_back — declaration, function, engine default, growth

**PyneCore version:** 6.10.10+qg.9 (limits), 6.10.10+qg.10 (TradingView growth
semantics).

## The problem

Series memory was bounded only by the measured TradingView default: every
series buffer grows to 5001 slots on a long run, whatever the script actually
indexes. The three places Pine bounds a series' history were not honored:

1. `indicator(max_bars_back=N)` / `strategy(max_bars_back=N)` was stored on
   the script object and **dead** — no series was ever sized by it.
2. `max_bars_back(var, num)` was a runtime **no-op**
   (`pynecore/lib/__init__.py`: `# noinspection PyUnusedLocal`). The
   statement form on a slot series is lowered to the slot's setter, but the
   `ta.*` machines' grow path (`max_bars_back(source, capacity)` inside
   `lib/ta.py`) called the runtime no-op with the value, so it grew nothing.
3. There was no engine-level default a host could set to bound a runner's
   series memory by what its scripts index.

## Minimal reproduction (synthetic data only)

```python
@script.indicator("mbb declared beyond", "mbbb", overlay=True, max_bars_back=5)
def main():
    return {"v": close[6]}   # one past the declared limit
```

Measured on the fork base 6.10.10-qg.8 (commit 4d3fe88d, scratch install,
`synthetic_bars(7, 20)`): the declaration sized nothing and the read was
**served, not na** — `v` is na on bars 0-5 (seven bars of history needed),
then equals `bars[i-6].close` on bars 6-19; bar 19 prints 498.92. An earlier
revision of this document claimed "na on every bar"; that measurement was
wrong, re-measured 2026-11-21.

## TradingView's actual rules (RE10143's manual, the Limitations page)

- The declaration and `max_bars_back()` set the **initial** buffer size. On
  historical bars the runtime "increases that buffer's size and restarts the
  script" when a read goes past it, repeating "until the system reaches the
  restart limit" (the count is not published).
- It "does not continue to resize historical buffers after the script loads":
  a read past the limit on a **realtime** bar is the RE10143 runtime error
  ("The requested historical offset (X) is beyond the historical buffer's
  limit (Y)").
- Most series cap at 5000; "some built-in series like open, high, low, close,
  and time have larger historical buffers that can reference up to 10,000
  bars".

## What the fork implements (6.10.10-qg.10)

- `SeriesImpl.default_max_bars_back(explicit)` resolves the chain (explicit
  slot value, script declaration, engine default, class default 5000) and
  floors it with `lib._max_bars_back_learned`; `lib.max_bars_back(var, num)`
  resizes a `SeriesImpl` value; `new_runner_state(max_bars_back_default=D)`
  (0..5000) is the per-runner engine default.
- A historical read past the limit — or past the size of a ring that has
  circularly overwritten (the `_overflowed` flag rides the rollback
  snapshots, so a discarded-history read after a rollback can never silently
  return na either) — raises `BufferGrowthNeeded`; a realtime read, or one
  past the hard cap (5000 general, 10000 for the `__lib·{open, high, low,
  close, time}` slots), raises RE10143 directly.
- `ScriptRunner._run_iter_with_restarts` serves a growth request by
  re-importing the script with `_max_bars_back_learned` raised to the
  requested offset and replaying the retained bars. The replay equals a run
  whose buffers were large enough from bar 0 (the machines' arithmetic
  depends only on window contents), so the consumer sees one row per bar
  whatever the restart count. A runtime shrink that re-applies on every
  replay (no progress), a bar-magnifier strategy loop, and the restart
  limit (100) surface as RE10143 instead of looping.
- The `ta.*` / `math.sum` machines grow with the same rule: `rolling_sum`
  (and its Cython twin) raise growth from an overflowed values ring instead
  of crashing with `IndexError`, and every length-history function (`change`,
  `cog`, `dev`, `median`, `mode`, `percentile_*`, `percentrank`, `rci`,
  `roc`, `wma`, and since qg.10 `alma`) carries the monotonic capacity seed.

## Costs and limits

- The runner retains every consumed historical bar for the replay: a
  measured 276 bytes per bar (tracemalloc over 100k synthetic bars — the
  boxed OHLCV fields plus list growth), about 66 MB on a 240k-bar daily run.
  Live bars are never retained; a growth request only arrives on historical
  bars, so a live runner never pays the restart.
- A strategy run under the bar magnifier refuses the restart (its sub-bar
  feed cannot be replayed) and raises RE10143 instead. A growth request
  raised inside a `request.security` child in multiprocess mode cannot be
  served by the parent's restart either; in-process children rebuild from
  `__security_contexts__` on the re-import.

## Evidence

`qg/tests/test_max_bars_back.py` (limits, seeds, the shrink loop) and
`qg/tests/test_max_bars_back_tv.py` (declared-grow, `close[6000]` on the
deep builtin buffer, moving-length equality with the large-buffer run for
sma/stdev/math.sum/wma/percentrank/change/roc/median, alma under declared
50, realtime RE10143). The drift gates prove default-mode output stays
bit-identical (the resolution chain collapses to the old 5000 constant when
nothing is declared and nothing grows).

## The open question

The builtin-argument form `max_bars_back(close, n)` still cannot size the
builtin up front: a builtin's history lives in per-call-site inline series,
which no module global addresses. Growth covers the correctness side (the
read itself restarts with a bigger buffer); only the up-front sizing of a
builtin would need transformer support for rewriting the subscript sites
that read it.
