# Design: honoring max_bars_back — declaration, function, engine default

**PyneCore version:** 6.10.10.

## The problem

Series memory is bounded only by the measured TradingView default: every
series buffer grows to 5001 slots on a long run, whatever the script actually
indexes. The three places Pine bounds a series' history were not honored:

1. `indicator(max_bars_back=N)` / `strategy(max_bars_back=N)` was stored on
   the script object and **dead** — no series was ever sized by it.
2. `max_bars_back(var, num)` was a runtime **no-op**
   (`pynecore/lib/__init__.py`: `# noinspection PyUnusedLocal`). The
   statement form on a slot series is lowered to the slot's setter, but the
   `ta.*` machines' grow path (`max_bars_back(source, capacity)` inside
   `lib/ta.py`) calls the runtime no-op with the value, so it grew nothing.
3. There was no engine-level default a host could set to bound a runner's
   series memory by what its scripts index.

And a read past a buffer's limit returned `na` — a **wrong value**, where
TradingView raises its runtime error RE10143 ("The requested historical
offset (X) is beyond the historical buffer's limit (Y)").

## Minimal reproduction (synthetic data only)

```python
@script.indicator("mbb declared beyond", "mbbb", overlay=True, max_bars_back=5)
def main():
    return {"v": close[6]}   # one past the declared limit
```

- Observed (6.10.10): the run completes; `v` is `na` on every bar — the
  declaration sized nothing and the deep read silently returned na.
- Expected: the declaration sizes every series to 5, and the read at 6
  raises RE10143; a read at exactly the limit (5) is legal and returns the
  value five bars back once history is long enough.

## Observed vs expected (numbers)

`qg/tests/test_max_bars_back.py`, synthetic bars:

- declared 5: `close[5]` is na on bars 0-4, then equals
  `bars[i-5].close` on bars 5-7; `close[6]` raises RE10143 with
  TradingView's exact message ("…offset (6) … limit (5)").
- function form `max_bars_back(s, 2)` on a declared series (statement form
  lowered to the slot setter): `s[2]` stays legal, `s[3]` raises
  ("…offset (3) … limit (2)").
- engine default `new_runner_state(max_bars_back_default=4)`: the same
  script that runs to the end under the 5000 default raises at `close[5]`;
  a value outside 0..5000 is refused at the state.
- `ta.change(close, 6)` under engine default 4: the machine grows its source
  buffer past the default (its own `capacity` seed follows the resolved
  default now, so `length > capacity` fires and the statement-form setter in
  `lib/ta.py` resizes), and the change computes on bars 6-7 exactly as under
  the 5000 default.

## Our evidence

The six tests of `qg/tests/test_max_bars_back.py` (above); the drift gates
prove the default-mode output is bit-identical (the resolution order —
explicit slot, script declaration, engine default, class default 5000 —
collapses to the old constant when nothing is declared).

## The change

- `SeriesImpl.default_max_bars_back(explicit)` resolves the chain; every
  series constructor and the `ta.*` / `math.sum` capacity seeds go through
  it (the Cython twin `_native_rolling_sum.pyx` kept in sync).
- `SeriesImpl.__getitem__` raises RE10143 when `offset > limit` (an offset
  within the limit but before history stays na; negative stays na).
- `lib.max_bars_back(var, num)` is implemented: it resizes a `SeriesImpl`
  value (the lowered statement form already rewrote slot-series calls).
- `new_runner_state(max_bars_back_default=D)`, 0 = engine default (5000),
  validated 0..5000; it lands in the tracked global
  `pynecore.lib:_max_bars_back_default` so it is per-runner state.

## The open question

The builtin-argument form `max_bars_back(close, n)` still cannot size the
builtin: a builtin's history lives in per-call-site inline series, which no
module global addresses. A script that needs a deeper builtin history
declares `indicator(max_bars_back=)` (which sizes every series including the
inline ones); per-site resizing of a builtin would need transformer support
for rewriting the subscript sites that read it.
