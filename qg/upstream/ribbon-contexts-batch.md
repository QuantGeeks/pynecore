# Investigation: a batch path for the multi-timeframe ribbon helper shape

**PyneCore version:** 6.10.10+qg.11. Investigation only — no patch; the exclusions it
documents are the correctness boundary, and lifting them is specified here for whoever
takes it up.

## The shape

A helper called once per timeframe of a ribbon (say 5/15/60/1D), each invocation its own
compiled function instance and therefore its own security context: same symbol, a
COARSER timeframe than the chart, `lookahead=barmerge.lookahead_on`, `calc_bars`-free,
the whole helper gated by an input. Two structural properties hold of the real shape and
not of a bare `request.security` call:

* **the signal is behind a guard.** The context's call site sits under
  `(shown and not same)` — `shown` an input, `same` a static timeframe comparison — so
  the call is RUN-CONSTANT, yet not provably once per chart bar by the current analysis
  (`signal_per_bar` is False);
* **the contexts read each other.** Every security child re-runs the whole script
  (function isolation), so the child of context A executes the sibling call sites too
  and reads their rings — `depends` is true of every ribbon context, and each is a
  consumer of the rest.

## What was measured (synthetic twin, `~/stocks/scratch`, synthetic data only)

A six-invocation ribbon twin on a 1m chart, unconditional call sites, no cross-reads:
every context reports `agg=True same_tf=False signal_per_bar=True depends=[]` — the
developing batch arms for all six and the run is exact against the per-bar oracle
(the same transport `qg/upstream/devbatch-out-of-session-frontier.md` just hardened).
The guard and the cross-reads are the only two things between the real shape and that
arm, and each is excluded for a correctness reason, not conservatism
(`dev_batch_eligible`'s docstring):

* **`signal_per_bar` False — the plan holds one round per chart bar.** Every signal
  consumes the next planned round; a signal the analysis cannot prove fires exactly
  once per bar would pair a bar with another bar's round. For THIS guard the risk is
  theoretical — the condition is run-constant, so the signal fires every bar or never —
  but the analysis has no notion of run-constancy: a proof would have to show the
  guarding expression references only inputs and constants (loop-invariant across the
  bar loop) and would then license `signal_per_bar=True` for the always-arm. That part
  is a contained transformers change.
* **`depends`/consumers — the planned rounds all carry their own bar's tick, but a peer
  read's cap and a consumer's pairing are derived from the round the CHART is on.** A
  dev-batch child runs AHEAD of the chart; its sibling reads inside the re-run would ask
  at its own planned tick, which the sibling's replay has typically already published
  past — `last_close_at_or_before` would answer deterministically, and the throttle
  bounds the run-ahead so the entry is there. What is NOT proven is the state side: the
  re-tick rollback that makes a replayed round invisible (`var`, function instances,
  `IBPersistent`) is per-context, and a child whose re-run both replays its own records
  and reads peers at planned ticks has no proof that the pair produces the per-bar
  path's values — the per-bar path reads peers at the CHART's round, after the chart
  settled every context of that bar. The exclusion is the honest statement of that gap.

## Why no patch this round

The two lifts are separable but only land value together (the guard proof alone still
leaves `depends` excluding the shape), and the `depends` lift needs the exactness proof
the determinism rule demands — a failing-first twin of the full ribbon (guard + cross
reads), oracle-equal over the batch path, plus a live-transition proof — before any
eligibility change. That is a round of its own; the write-up above is the spec. Until
then the ribbon keeps the per-bar handshake, and the same-timeframe and
plain-`request.security` shapes (the measured 20.2 s → 10.9 s twin, and the synthetic
six-context ribbon) batch.

Related: `qg/upstream/devbatch-out-of-session-frontier.md` — the extended-session and
overrunning-bar batch transports are now exact, so the private parity tool's
"in-memory iterator for extended days" workaround is no longer needed for correctness;
the ribbon's lock-step is a different, documented exclusion.
