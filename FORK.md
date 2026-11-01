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

## Engine findings without a patch

| Finding | Spec | Upstream | Status |
|---|---|---|---|
| `ta.pivot_point_levels`: R4/S4/R5/S5 are NaN | §9.2 | to file | not offered until fixed (§9.2) |
| `smc_luxalgo`: live crash with FVG-15m and daily levels both on (each alone passes) | §1.5 | to file | watched |
| `request.security`: contexts frozen in live with host data | §4.7 | upstream #49 watched | served by the service's shared feeds (§4.7), not PyneCore's contexts |

## Gates

`pynecore.qg_gates` (Task 4; Task 5 adds golden, E1, drift and speed), run by `qg/gates/run_all.sh` in the `qg-gates` workflow on synthetic data only — Layer A is this package's own `gate_ta`/`gate_draw` scripts on three seeds; the catalogue over Plan 1's `indicator-scripts` layout (fixtures and house scripts) is run only by the **private CI**, which passes `--root`.

- **GATE1** proves co-resident runners equal their solo runs, batch and live: `GATE1 batch 0/<n> live 0/<n>`. Control: `--control` drops the per-step activate and must print `GATE1 CONTROL corrupted <k>/<n>` (exit 0 only when k > 0).
- **GATE2** proves no unmanaged state survives a run (warm pass, then sequential and interleaved forms with a fresh state installed before each fingerprint, and a two-series data-dependence probe): `GATE2 steady 0 interleaved 0 data-dependent 0`. The walker records `typing` aliases as leaves and never walks `pynecore.transformers` (two rulings of 2026-10-31: the walk was otherwise `__pycache__`-dependent).
- **GATE3** proves co-resident runners equal per-process pristine runs (`pristine.py`, plain PyneCore, one process each) over K=6 random-partner trials plus one trio trial per script: `GATE3 total mismatching runners 0/46` on Layer A.
- **GATE4** pins the static state inventory: `GATE4 inventory unchanged (3587 paths)`. `qg/gates/inventory.json` is updated by re-running `gate4_inventory --write` in the Linux candidate image and committing it in the same PR — that diff is the person's review (spec §13.1); the CI never rewrites it.

- **GOLDEN** (Task 5; private CI with `--root` and Plan 1 Task 12's `golden.json`): our values against a TradingView export, column by column — the spec is a JSON list of `{"script","stem","columns":[{"tv_index","plot","shift"}]}` with optional `inputs` (default `{}`), `sum_mode` (default `"compensated"`, ruling 9) and `warmup_bars` (default 1500, the tvtruth method); the column mapping is written once by `tv_index`, the E2 `shift` is applied in the harness.  Per column `GOLDEN <script> <stem> [<tv_index>→<plot>]: exact <a>/<n> rel9 <b>/<n>`; a column passes iff rel9 covers every compared bar; `GOLDEN PASS <c> columns` / `GOLDEN FAIL <k> of <c> columns`.
- **E1** (Task 5; private CI): `e1_gate --root --reference <stem> --further '<glob>' --expect-window 41301 --expect-compensated 428` runs `scripts/e1_sma40.py` in both sum modes on each export's own bars (each mode its own process) and compares with column index 6.  The reproduction holds on the reference when the window mode is exact on every bar and the compensated machine is not (`E1 REPRODUCTION FAIL …`, exit 1, otherwise); the gate prints `E1 GATE (§9.2): PASSED` once **two further exports agree** — until then `… <k> of 2 further exports agree; window mode stays off by default` (both exit 0): the window mode becomes the default only after PASSED (README ruling 9).
- **DRIFT** (Task 5; fork CI with `--upstream-python`): every Layer A job batch, compensated, via `pristine.py` under each interpreter — the baseline is upstream `v6.10.10`, whose install never calls `set_sum_mode`.  `DRIFT 6.10.10+qg.1 vs 6.10.10: 0/6 jobs differ []`; `--require-identical` fails on any difference: the fork's default build is upstream's.
- **PERF** (Task 5): µs/bar per script and mode — the median of 5 per-run medians, the first 200 bars skipped, one process per run.  Budget **25.5 µs/bar = 1.5 × 17.0**, the slowest median of the 25 standard scripts (ichimoku, SPY RTH 1m, `proof/catalogue/REPORT.md`); Layer A runs on `synthetic_bars(7, 8580)`; `house/` scripts are reported only (a heavy house script is the governor's case, spec §4.2).  `PERF <id> <mode> <y> us/bar (budget 25.5) [base <x> ratio <r>]`, `PERF activate p50 <x> us (60 states)` (reference 100 µs, `proof/scale/REPORT.md`, not gated), `PERF BUDGET PASS` / `PERF BUDGET FAIL <k> scripts`.  `QG_PERF_INJECT_US=<n>` busy-waits n µs per bar under the measured interpreter only (the control).
Negative controls in CI (`gates-negative` job): the gate1 control above, and the five adversarial injections (`qg/gates/adversarial/`, `ADV=A..E`) — a class counter, a closure cache, a dict inside a module-level tuple, an ALLCAPS module dict, a latent class attribute — each must be caught (measured: A by GATE1, B/C/D by GATE3, E by GATE2; `run_all` stops at the first failing gate).

## Releases and the service pin

Filled by Task 6: release tag `6.10.10-qg.1` (package version `6.10.10+qg.1`, PEP 440), never a GitHub Release (it triggers upstream's PyPI workflow), and the indicator service's pin `pynesys-pynecore==6.10.10+qg.1` via `[tool.uv.sources]` on tag `6.10.10-qg.1`.
