# Design: hosting many ScriptRunners in one process (per-runner module state)

**PyneCore version:** 6.10.10.

## The problem

Bar state and per-call-site `ta` state live in module globals
(`instance_state._root_vectors`, the `Persistent` slots the import hook rewrites into
module attributes, the drawing registries), so two `ScriptRunner`s stepping in one
process corrupt each other: in our interleaving control, 11 of 15 runner pairs
produced values different from their pristine per-process runs (spec 1.5, measured in
the `ctxswap` proof; 50/50 sampled keys bit-identical once the swap below is used).
A second defect compounds it: `drawing_snapshot._REGISTRIES` is a tuple of the
*baseline* drawing registries built at import (an ALLCAPS constant), so after any
state swap a `DrawingSnapshot` saves and restores the empty originals and live
drawings pile up to the 500-object cap until `_REGISTRIES` is rebound.

## Minimal reproduction (synthetic data only)

Interleave six runners (two scripts × three seeds) round-robin in one process; after
each `next()` on a runner's iterator, activate that runner's state before stepping the
next one. The control drops the activation. Synthetic bars only:

```python
import random
from pynecore.core.script_runner import ScriptRunner
from pynecore.types.ohlcv import OHLCV

def bars(seed, n=600):
    rnd, out, px = random.Random(seed), [], 500.0
    for i in range(n):
        o = round(px, 2); c = round(o + rnd.uniform(-0.6, 0.6), 2)
        out.append(OHLCV(1779802200000 + 60000 * i, o,
                         round(max(o, c) + rnd.uniform(0, 0.3), 2),
                         round(min(o, c) - rnd.uniform(0, 0.3), 2), c,
                         float(rnd.randint(50000, 500000))))
        px = c
    return out

def rows(script, seed):
    return [dict(p) for _c, p in
            ScriptRunner(script_path=script, ohlcv_iter=bars(seed)).run_iter()]

# six iterators round-robin, no activation:
#   -> at least one runner's rows != rows(script, seed) run alone (11/15 pairs corrupted)
# with a per-runner module-state activation before each next():
#   -> every runner equals its alone run bit for bit, plots and drawing counts (15/15)
```

The per-state activation is the whole of our fix: save the outgoing state's tracked
globals, install the incoming one's (fresh `instance_state._root_vectors`,
per-state `_shared_caches` contents, per-state `sys.modules` entry for the script),
and rebind `drawing_snapshot._REGISTRIES` to the live registries after every switch.
The tracked set is 426 module globals at 6.10.10 (lowercase, non-dunder,
non-callable, with type-name exclusions), plus the fork's sum-mode global.

## Observed vs expected

- Without activation, interleaved runners corrupt: 11/15 pairs differ from pristine
  runs (plots, and drawing counts under live mode with intrabar ticks).
- With per-runner activation, 15/15 interleaved runners equal their pristine
  per-process runs bit for bit, and live drawings stay within their caps once
  `_REGISTRIES` is rebound (without the rebind, live drawings pile up to the 500
  cap: the proof's P7).
- A runner that raises mid-run must be evicted under its own state (its generator's
  `finally` resets whichever globals are current); with that, its neighbours stay
  bit-exact.

## Our offer, and the long-term ask

We carry `pynecore.core.runner_state`: an import guard (refuse the import while a
runner is live, so the baseline is never captured mid-run), `new_runner_state`,
`activate`, `create_runner`, `discard`, `tracked_names`, `swap_sha` — a small,
testable module implementing the above. The long-term ask is the better design this
works around: runner state off the module globals, so hosting many runners in one
process is a PyneCore property rather than a swap.
