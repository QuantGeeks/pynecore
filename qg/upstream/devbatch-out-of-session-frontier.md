# Defect: a developing-batch step published its frontier into the scheduled break

**PyneCore version:** 6.10.10+qg.11 (found while investigating the extended-session
batch path; the underlying replay transport is qg.10's).

## The symptom

With `ChartBarWindow` (the CLI/production batch path), a `lookahead_on` higher-timeframe
context's batch child died mid-run on charts whose bars OVERRUN the syminfo's declared
session end — bars outside every declared session, so their round tick falls in the
trading calendar's scheduled break:

```
RuntimeError: security context 'sec·…': the developing batch published no round in
(1736211660000, 1736211720000] (nearest close 1736211660000) — the child's chart bar
stream diverged from the bar loop's
```

Which bar it died on moved a bar or two between runs. The per-bar transport of the same
bars was exact — this is the second half of the divergence a private parity tool had
worked around by keeping the in-memory iterator for any extended-day chart (its
`_lookahead_htf` arm): the session-close tie half was fixed by
`qg/upstream/devbatch-session-close-tie.md`, and this is what was left.

## The reproduction (synthetic data only)

`qg/tests/test_htf_devbatch_ext.py` — an extended-session 1m chart (04:00–20:00), an
official daily feed a cent off the chart aggregate, and sixteen hours of 1m bars per day.
With `T0` at the session open the batch transport is exact (the first test); starting
the same bars at 07:20 so they overrun the 20:00 end makes every batch run die at the
first bar past the session close (the second test, RED before this fix, green after —
3 batch runs, each equal to the per-bar oracle and to each other).

## The root cause

A developing-batch child replays the planned record sequence
(`iter_dev_batch_records`), one entry per chart bar's tick, and publishes each entry
with its frontier. For a step whose tick falls inside a scheduled break,
`_developing_frontier()` returns the break's END — the extension that serves the per-bar
transport, where it is sound: there, a producer pushes one entry per ROUND on its own
grid (a daily context closes entries at daily closes), and nothing of it can close
inside the break, so claiming "everything closing at or before the break end is
published" costs nothing and releases D/W/M peers that ask into the break
(`_peer_asof`).

The batch replay closes one entry at EVERY chart bar's tick — including the break
bars'. At the first bar past the session end the child published
`frontier = <next session open>` while its next planned records (every later break
bar's) still closed below that instant:

```
WRITE close_ms=1736211540000 frontier=1736211540000   # 19:59 bar: frontier = own tick
WRITE close_ms=1736211600000 frontier=1736240400000   # 20:00 bar: frontier = NEXT DAY 04:00
```

The ring frontier's contract is "everything closing at or before it is published", and
the chart's per-bar read waits on exactly that (`wait_for_close(..., require_frontier=
True)`). Released early, the read paired the newest entry at or below its as-of — an
EARLIER bar's value. With `batch_expects_entry` set (a context whose value changes on
this bar) the pairing window check caught it and raised the divergence error; for a
`dev_skip` context (`first_dev_only`, whose reads expect no fresh entry mid-period) the
same early release would have answered a STALE value with no error at all — the
inexactness class the determinism rule forbids, not a crash.

Why the RTH-feed twin of the same chart never tripped it: `break_end_after` resolves
the break against the CHART's calendar. A feed toml with narrower sessions only moves
the aggregator's period anchor; the chart's bars stayed inside the chart's own declared
sessions, so no tick ever fell in a break and the extension never fired.

## The fix

The replay already holds its next record one step ahead (`dev_batch_next` — the
iterator is kept one record ahead for `FLAG_MORE_STEPS`). A replayed developing step
now caps its published frontier below that next record's tick:

```python
sec_ctx.frontier = _developing_frontier()
if dev_batch_running and dev_batch_next is not None:
    sec_ctx.frontier = min(sec_ctx.frontier, dev_batch_next[7] - 1)
```

The cap is exactly the frontier's contract: everything the plan closes at or below the
published frontier IS published. It also carries the same-tie group atomicity of the
session-close fix for free — a step followed by a same-tick record (a closed record and
its developing one on a delivering bar) caps below the shared tick, and the group's
last step, whose next record has a strictly later tick, still releases readers at its
own. The sequence's last step has no next record and keeps the full break extension,
which is again sound: nothing of this context closes after it. The per-bar transport is
untouched — its rounds are hand-shaken per bar and its break extension is what a D/W/M
peer reading into the break needs.

## What this says about the workaround it retires

The private parity tool's "extended day" arm (route any chart whose session ends past
16:00 through the in-memory iterator) is no longer needed for correctness: both halves
of its divergence — the session-close tie and this break-bar frontier — are fixed on
the batch path, and the batch transport equals the per-bar one on in-session AND
overrunning bars. Dropping the workaround is the scripts side's call; the engine no
longer requires it.
