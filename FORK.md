# Fork

QuantGeeks' fork of [PyneSys/pynecore](https://github.com/PyneSys/pynecore), the engine of the
indicator platform (spec `2026-10-15-indicator-platform-design.md` §4.9, ruling 16). It carries
upstream **v6.10.10** (commit `b9a764f94412d899c92125d3d771de7f05487a05`) plus a short stack of
upstream-shaped commits: per-runner state, the E1 window re-sum mode behind a switch, the
§13.1 bit-identity gates as `pynecore.qg_gates`, and the release/pin tooling. Default behaviour
is upstream's, bit for bit; the drift gate proves it.

The fork is **public** (a fork of a public repository cannot be private), so nothing private runs
or appears in it: no house script, no TradingView export, no member data, no production or
staging name, no secret. Tests use generated series; the `qg/upstream/` write-ups carry
synthetic reproductions only, never TradingView data. The golden, parity and performance gates
that need the real fixtures run in the private `QuantGeeks/indicator-scripts` CI against the
fork at its pinned tag.

## Branches and merge method

`main` mirrors upstream and is never committed to. `qg/main` is upstream's tag plus our commits.
Work branches start from `origin/qg/main`; PRs target `qg/main` and are squash-merged. The PR
title is the squashed commit's subject and the `FORK.md` row's "Commit" cell, verbatim.
Commit subjects follow upstream's Conventional Commits when a change is upstream-offerable
(`feat(math): …`, `feat(core): …`) and `qg: …` when it is fork-only.

## The write-up procedure

(sev, 2026-10-31: **nothing is pushed to upstream** — no issue, no PR; we make our own
system work.)

1. write `qg/upstream/<slug>.md` (title line, PyneCore version, minimal synthetic repro
   script, observed vs expected with numbers, our evidence, the open question) before the
   code — it is the record a future contributor or rebase needs;
2. the row's "Upstream" cell is `not filed (sev, 2026-10-31)`; `pending:` marks a write-up
   not yet finished and keeps the PR red;
3. when upstream ships an equivalent, the row's status becomes `drop at next rebase
   (upstream <version>)` and Task 5's drift gate decides the equivalence.

## Carried patches

| Commit | Why (spec) | Upstream | Status |
|---|---|---|---|
| feat(math): window re-sum mode for math.sum | spec §9.2 E1; default off until the §9.2 gate (Task 5) | not filed (sev, 2026-10-31); write-up qg/upstream/e1-window-resum.md | carried, default off |
| feat(core): per-runner state for co-resident runners | spec §4.2, §4.9 | not filed (sev, 2026-10-31); write-up qg/upstream/per-runner-state.md | carried |
| test(ast): the lib-route registry scan skips the fork's qg_gates scripts | gates package layout (Plan 2 Task 4; Review Focus 5) | not filed (sev, 2026-10-31) | carried |
| fix(lib): syminfo mirrors every SymInfo slot at import | spec §4.2, §13.1 gate 2 (Plan 2 Task 7) | not filed (sev, 2026-10-31); write-up qg/upstream/syminfo-slots-at-import.md | carried |
| feat(core): yield_intrabar for live runners; release 6.10.10-qg.7 | spec §1.5, §7.1 (forming values) | not filed (sev, 2026-10-31); write-up qg/upstream/intrabar-yield.md | carried, default off |
| fix(ta): pivot_point_levels returns every level each type defines | indicator port gap B | not filed (sev, 2026-10-31); write-up qg/upstream/pivot-levels-outer.md | carried |
| fix(security): a supplied same-symbol HTF feed is the source of its closed periods | indicator port gap C | not filed (sev, 2026-10-31); write-up qg/upstream/htf-supplied-feed.md | carried |
| feat(request): earnings, dividends and splits read the event series the runner is given | indicator port gap A | not filed (sev, 2026-10-31); write-up qg/upstream/event-requests.md | carried |
| fix(input): input.int and drawing coordinates are Python ints | indicator port gap D | not filed (sev, 2026-10-31); write-up qg/upstream/int-input.md | carried |
| feat(core): engine gaps from an indicator port (pivot levels, HTF feed, event series, int inputs); release 6.10.10-qg.8 | the four rows above, as one squash | not filed (sev, 2026-10-31); write-ups as above | carried |
| feat(drawing): engine call-site tags on every drawing object | per-viewer restyle without style inputs in the computation key | not filed (sev, 2026-10-31); write-up qg/upstream/drawing-tags.md | carried |
| feat(viz): exact drawing change journal with call-site tags | the host renders drawings per update: applying the journal from an empty set reproduces the drawing set at every point | not filed (sev, 2026-10-31); write-up qg/upstream/drawing-journal.md | carried |
| feat(core): honor max_bars_back from the declaration, the function and an engine default | series memory bounded by what scripts index; RE10143 parity | not filed (sev, 2026-10-31); write-up qg/upstream/max-bars-back.md | carried |
| feat(core): TradingView buffer growth semantics for max_bars_back | declared/function/engine bounds grow on demand, shrink once at most, alma seeds per RE10143; moving lengths never na silently | not filed (sev, 2026-10-31); write-up qg/upstream/max-bars-back.md | carried |
| docs(qg): max-bars-back design doc — TradingView growth semantics, corrected base truth | the write-up's base truth re-measured against RE10143 | not filed (sev, 2026-10-31); write-up qg/upstream/max-bars-back.md | carried |
| feat(drawing): tag consistency — method-form copy stamped, per-module tag ranges | copy keeps the creator's tag; tags unique across imported modules | not filed (sev, 2026-10-31); write-up qg/upstream/drawing-tags.md | carried |
| feat(viz): per-change journal drain — drawing version tracking | the journal carries only what changed, per field, with exact rollback replay | not filed (sev, 2026-10-31); write-up qg/upstream/drawing-journal.md | carried |
| fix(ci): CI rot — typer range, gate4 inventory for the gates env, twin-invariant tracked names | the gates env and the suite pin what the code now defines; no bound loosened | not filed (sev, 2026-10-31) | carried |
| fix(qg): drawing_tags test leaked its pyne library into the process | test isolation: the registered-libraries snapshot restores | not filed (sev, 2026-10-31) | carried |
| fix(qg): runner_state negative control was count-based and order-dependent | the control asserts the exact set difference, never a count | not filed (sev, 2026-10-31) | carried |
| fix(core): the drawing-copy registry walked in address order | gate 2's fingerprint is process-order independent | not filed (sev, 2026-10-31) | carried |
| fix(core): developing-batch ring entries pair at their delivering bar's tick | the batch transport of a lookahead_on HTF context is run-to-run exact — determinism rule (spec §4.9) | not filed (sev, 2026-11-21); write-up qg/upstream/devbatch-session-close-tie.md | carried |
| perf(core): a same-timeframe lookahead_on context batches like lookahead_off | a same-TF ON context pairs the same bar as OFF on history (no aggregator → the confirmed-time rule is lookahead-blind), so the blanket ON exclusion cost the batch transport for nothing — measured 2x on a 63-column, 41,340-bar twin (20.2 s → 10.9 s, private CI) | not filed (sev, 2026-11-21) | carried |
| fix(drawing): the call-site tag is a slot, not a field — identity forms cannot see it | the tag is host metadata, never part of a drawing's value: a field-walking snapshot/identity must not carry it (a private-CI twin failed exactly there, two script versions equal on every field but tag) | not filed (sev, 2026-11-21); write-up qg/upstream/drawing-tags.md | carried |
| fix(core): a developing-batch step's frontier stays below its next planned record's tick | a planned tick inside a scheduled break (chart bars overrunning the declared session end) published the break-end extension as its frontier, releasing the chart's per-bar read early — a wrong pairing, or a stale value with no error for a dev_skip context; determinism rule (spec §4.9) | not filed (sev, 2026-11-21); write-up qg/upstream/devbatch-out-of-session-frontier.md | carried |

## Engine findings without a patch

| Finding | Spec | Upstream | Status |
|---|---|---|---|
| `ta.pivot_point_levels`: R4/S4/R5/S5 are NaN | §9.2 | to file | not offered until fixed (§9.2) |
| `smc_luxalgo`: live crash with FVG-15m and daily levels both on (each alone passes) | §1.5 | to file | watched |
| `request.security`: contexts frozen in live with host data | §4.7 | upstream #49 watched | served by the service's shared feeds (§4.7), not PyneCore's contexts |
| the multi-timeframe ribbon helper shape does not batch: a run-constant guard keeps `signal_per_bar` unproved and cross-reads make every context a dependent/consumer — both exclusions are correctness boundaries, and lifting them needs an exactness proof first | §4.9 (determinism rule: batch must equal per-bar) | n/a (fork-only batch machinery); write-up qg/upstream/ribbon-contexts-batch.md | spec written; not implemented (2026-11-21) |

## Gates

`pynecore.qg_gates` (Task 4; Task 5 adds golden, E1, drift and speed), run by `qg/gates/run_all.sh` in the `qg-gates` workflow on synthetic data only — Layer A is this package's own `gate_ta`/`gate_draw` scripts on three seeds; the catalogue over Plan 1's `indicator-scripts` layout (fixtures and house scripts) is run only by the **private CI**, which passes `--root`.

- **GATE1** proves co-resident runners equal their solo runs, batch and live: `GATE1 batch 0/7 live 0/7`. Control: `--control` drops the per-step activate and must print `GATE1 CONTROL corrupted <k>/<n>` (exit 0 only when k > 0).
- **GATE2** proves no unmanaged state survives a run (warm pass, then sequential and interleaved forms with a fresh state installed before each fingerprint, and a two-series data-dependence probe): `GATE2 steady 0 interleaved 0 data-dependent 0`. The walker records `typing` aliases as leaves and never walks `pynecore.transformers` (two rulings of 2026-10-31: the walk was otherwise `__pycache__`-dependent).
- **GATE3** proves co-resident runners equal per-process pristine runs (`pristine.py`, plain PyneCore, one process each) over K=6 random-partner trials plus one trio trial per script: `GATE3 total mismatching runners 0/46` on Layer A.
- **GATE4** pins the static state inventory: `GATE4 inventory unchanged (3649 paths)`. `qg/gates/inventory.json` is updated by re-running `gate4_inventory --write` in the Linux candidate image and committing it in the same PR — that diff is the person's review (spec §13.1); the CI never rewrites it.

- **GOLDEN** (Task 5; Task 11: full-header `tv_index`, X0; private CI with `--root` and Plan 1 Task 12's `golden.json`): our values against a TradingView export, column by column — the spec is a JSON list of `{"script","stem","columns":[{"tv_index","plot","shift"}]}` with optional `inputs` (default `{}`), `sum_mode` (default `"compensated"`, ruling 9) and `warmup_bars` (default 1500, the tvtruth method); the column mapping is written once by `tv_index`, the E2 `shift` is applied in the harness.  Per column `GOLDEN <script> <stem> [<tv_index>→<plot>]: exact <a>/<n> rel9 <b>/<n>`; a column passes iff rel9 covers every compared bar; `GOLDEN PASS <c> columns` / `GOLDEN FAIL <k> of <c> columns`.
- **E1** (Task 5; Task 8: `--warmup 39`): `e1_gate --root --reference <stem> --further '<glob>' --expect-window 41301 --expect-compensated 428` runs `scripts/e1_sma40.py` in both sum modes on each export's own bars (each mode its own process) and compares with column index 6 **from bar 39, the first bar the script can compute (its length − 1)** — a custom-range export carries TradingView's prior-history values in its first 39 cells, where the script on the export's own bars is na (measured 2026-11-01: the NVDA 5m and SPX 1D further exports were each short by exactly 39 bars).  The reproduction holds on the reference when the window mode is exact on every compared bar and the compensated machine is not (`E1 REPRODUCTION FAIL …`, exit 1, otherwise); the gate prints `E1 GATE (§9.2): PASSED` once **two further exports agree** — until then `… <k> of 2 further exports agree; window mode stays off by default` (both exit 0): the window mode becomes the default only after PASSED (README ruling 9 — the flip is its own ruling; the default stays `compensated`).  With `--warmup 0` the comparison starts at bar 0 (the Task 5 behaviour, explicit).
- **DRIFT** (Task 5; fork CI with `--upstream-python`): every Layer A job batch, compensated, via `pristine.py` under each interpreter — the baseline is upstream `v6.10.10`, whose install never calls `set_sum_mode`.  `DRIFT 6.10.10+qg.2 vs 6.10.10: 0/7 jobs differ []`; `--require-identical` fails on any difference: the fork's default build is upstream's.
- **PERF** (Task 5): µs/bar per script and mode — the first 200 bars skipped, one process per run; with a baseline, `--runs` (default 5) INTERLEAVED rounds — per round, per script, the head's two modes and the base run back to back, the first serve alternating by round parity so slow drift lands on both sides equally.  Budget **25.5 µs/bar = 1.5 × 17.0**, the slowest median of the 25 standard scripts (ichimoku, SPY RTH 1m, `proof/catalogue/REPORT.md`); Layer A runs on `synthetic_bars(7, 8580)`; `house/` scripts are reported only (a heavy house script is the governor's case, spec §4.2).  Gated (rulings 2026-11-01 and 2026-11-02): with `--baseline-python`, the **compensated** mode fails on the **median of per-round ratios r > 1.25** against upstream, one ratio per interleaved round — like for like, the only comparison that means anything on unknown hardware — and the **window** mode on **its cost over the SAME run's compensated time**, `y_window / y_compensated > 1.75` (measured 1.14–1.42 on Layer A and the catalogue, bollinger's three sums 1.42; 1.75 leaves the margin the 1.25 ratio leaves Layer A): an absolute budget on a shared runner measures the runner, not the code (2026-11-02: `gate_ta compensated 22.2 / window 25.9` on code whose normal window is 15.7).  Like for like is ENFORCED, not ruled (2026-11-22, replacing the 2026-11-21 ruling the fleet falsified): the gate fingerprints both interpreters — implementation, `sys.version`, `sysconfig.get_platform()`, and which compiled natives the install carries (`_native_math`/`_native_color`/`_native_rolling_sum`) — and REFUSES (exit 2, `PERF BUDGET REFUSED`) before a single timing on any mismatch. The two confounds the ruling described are refusals now, not noise: the PyPI wheel carries the compiled natives and a git/sdist install may not (a wheel baseline against a natives-free fork measured 8 scripts at 1.31–1.74, `gate_ta` 1.73, on matched uv CPythons), and a homebrew CPython measured ~15% off the uv build of the same 3.12. What the ruling called runner noise — base columns swinging 1.12–1.71× between same-code runs — is what the interleaving and the median-of-per-round-ratios absorb: one noisy round moves one ratio, not the budget.  The window line prints `… ratio <r> vs compensated <w>`.  Without a baseline (a local run), both modes gate on the absolute `y > 25.5`.  `run_all.sh` and CI always pass the baseline.  `PERF <id> <mode> <y> us/bar (budget 25.5) [base <x> ratio <r> rounds <r0/r1/…>]`, `PERF activate p50 <x> us (60 states)` (reference 100 µs, `proof/scale/REPORT.md`, not gated), `PERF BUDGET PASS` / `PERF BUDGET FAIL <k> scripts`.  `QG_PERF_INJECT_US=<n>` busy-waits n µs per bar under the measured interpreter only (the control).
Negative controls in CI (`gates-negative` job): the gate1 control above, and the five adversarial injections (`qg/gates/adversarial/`, `ADV=A..E`) — a class counter, a closure cache, a dict inside a module-level tuple, an ALLCAPS module dict, a latent class attribute — each must be caught (measured: A by GATE1, B/C/D by GATE3, E by GATE2; `run_all` stops at the first failing gate).

## Releases and the service pin

The release tag is `6.10.10-qg.11`, the package version `6.10.10+qg.11` (PEP 440;
spec §4.9). Never a GitHub Release (it triggers upstream's PyPI workflow); the
tag push and the rebase force-push are operator steps — `UPGRADING.md` is the
procedure, step by step.

The service pins the tag exactly (Task 6):

```toml
[project]
dependencies = ["pynesys-pynecore==6.10.10+qg.11"]

[tool.uv.sources]
pynesys-pynecore = { git = "https://github.com/QuantGeeks/pynecore", tag = "6.10.10-qg.11" }
```

`uv lock` records the tag's commit sha; the image needs a C compiler (Cython
builds the native extensions on install). The worker calls
`pynecore.qg_build.assert_build(<the image's expected-manifest file>)` at start
(spec §13.1 item 1): a wheel or interpreter that is not the one the manifest was
produced from refuses to run. `python -m pynecore.qg_build` prints that manifest
(sorted keys, indent 2).
