# Developing batch: the ring pairs a session close by producer timing (6.10.10-qg.10)

**PyneCore version:** 6.10.10 (measured on `6.10.10-qg.10`, pre-existing at `6.10.10-qg.8`).

## The problem (synthetic)

```pine
plot(request.security(syminfo.tickerid, "1D", close, lookahead = barmerge.lookahead_on), "dev")
plot(request.security(syminfo.tickerid, "1D", close[1], lookahead = barmerge.lookahead_on), "prev")
```

on an RTH 1-minute chart (09:30–16:00, six weekdays) through the ChartBarWindow wiring — the CLI's
batch path — with a supplied `1D` feed whose OHLC is a cent off the chart aggregate. Run the same
script N times in one process: the session-closing bars (index 389 of each 390-bar session) read the
OFFICIAL closed value where the per-bar transport (the exactness oracle) reads the developing one —
`dev` a cent off — and which runs and which sessions differ changes from run to run. The per-bar
path is deterministic.

## The mechanism (measured)

Enumerating the shared ring at day 3's close (16:00), after the child finished (probe of
`RingReader.last_close_at_or_before` + the block's live entries):

```
entry 1561  close 15:59  100.047   developing, chart-built
entry 1562  close 16:00  100.058   developing — the value the per-bar path returns
entry 1563  close 16:00  100.068   closed, official — appended LATER, wins the pairing
```

Two defects, one symptom:

1. **Keying.** A daily period on a 1-minute chart closes at 16:00 — the tick of the 15:59 bar —
   but the aggregator delivers the completed period with the NEXT session's first bar (09:30,
   tick 09:31). The planned `DEV_BATCH_CLOSED` record was keyed by the completed period's own
   scheduled close (`ctx.bar_close` = 16:00), so it landed at an instant the 15:59 bar's
   developing record already occupies, appended a whole session later in push order. "Last entry
   ≤ as-of" then answers the official bar for every read that happens after the child moved past
   the next session open — and the throttle's steady state is exactly that (the child runs ahead
   of the chart's watermark). The per-bar path sequences pushes by the delivering bar's tick and
   never sees the collision. `qg/upstream/htf-supplied-feed.md` had already excluded this shape on
   a D/W/M chart for the same reason ("a replaced value would make the batch ring's pairing
   race-dependent"); the intraday delivery case is the same hazard, unexcluded.
2. **Release.** Within one delivering bar's group the closed and the developing record share the
   tick; `FLAG_MORE_STEPS` caps the frontier below the tick until the group's last step, but
   `RingReader.wait_for_close`'s `has_close` arm releases a parked consumer on the FIRST tied
   entry — the closed one — a mid-group read.

Pre-existing: the private CI run `scici-95509cb-1121194658` (fork `6.10.10-qg.8`, `4d3fe88d` —
the `qg/main` base of this branch) failed the same parity; the defect predates the branch.

## The change

1. Every planned developing-batch record — the closed one included — keys its ring entry by the
   tick of the chart bar that DELIVERS it (`SecurityChildContext.dev_batch_record`, set where the
   planned record's OHLCV rides the step). The ring's ≤-order becomes the per-bar push order;
   ties exist only inside one delivering bar's group, where `FLAG_MORE_STEPS` already caps the
   frontier below the tick.
2. The chart's developing-batch read waits frontier-only
   (`wait_for_close(require_frontier=True)`): the frontier reaches the as-of exactly when the
   group's last step publishes, so a group is atomic to the read and `last_close_at_or_before`
   picks the group's final entry — the developing record — independent of producer timing. Bars
   with no record of their own (the `first_dev_only` compression) already waited frontier-only
   (no entry exists at their as-of), so their behavior is unchanged. The closed historical batch
   (`lookahead_off`) keeps scheduled-close keying and its `has_close` release: its entries sit at
   distinct instants and nothing ties.

## Tests

`qg/tests/test_htf_devbatch_repeat.py` + `qg/tests/scripts/htf_devbatch_repeat.py`: the shape
above, with a deterministic per-step burn in each session's last minutes — it widens the gap
between one bar's tied appends from one fast step to about a millisecond, so a mid-group or
shadowed read is a reproducible wrong answer, not scheduler luck (the burn touches no plot).
Four batch runs in one process must be identical AND equal the per-bar transport. RED 3/3 at
`6637a09f`: bars 389/779/1169/1559/1949 — every session close except the data's last bar, whose
period is never delivered — `dev` reading the official close, a cent off the oracle. Green after,
6/6 invocations; the eleven upstream dev-batch tests (062/063/064/080/085/086) and both suites
stay green.

## Not settled

Nothing. Not filed (sev, 2026-11-21): nothing is pushed upstream.
