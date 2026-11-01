# Fork

QuantGeeks' fork of [PyneSys/pynecore](https://github.com/PyneSys/pynecore), the engine of the
indicator platform (spec `2026-10-15-indicator-platform-design.md` §4.9, ruling 16). It carries
upstream **v6.10.10** (commit `b9a764f94412d899c92125d3d771de7f05487a05`) plus a short stack of
upstream-shaped commits: per-runner state, the E1 window re-sum mode behind a switch, the
§13.1 bit-identity gates as `pynecore.qg_gates`, and the release/pin tooling. Default behaviour
is upstream's, bit for bit; the drift gate proves it.

The fork is **public** (a fork of a public repository cannot be private), so nothing private runs
or appears in it: no house script, no TradingView export, no member data, no production or
staging name, no secret. Tests use generated series; upstream issues carry synthetic
reproductions, never TradingView data. The golden, parity and performance gates that need the
real fixtures run in the private `QuantGeeks/indicator-scripts` CI against the fork at its
pinned tag.

## Branches and merge method

`main` mirrors upstream and is never committed to. `qg/main` is upstream's tag plus our commits.
Work branches start from `origin/qg/main`; PRs target `qg/main` and are squash-merged. The PR
title is the squashed commit's subject and the `FORK.md` row's "Commit" cell, verbatim.
Commit subjects follow upstream's Conventional Commits when a change is upstream-offerable
(`feat(math): …`, `feat(core): …`) and `qg: …` when it is fork-only.

## The upstream-first procedure

1. write `qg/upstream/<slug>.md` (title line, PyneCore version, minimal repro script, observed
   vs expected with numbers, our evidence, the question) before the code;
2. sev files it: `gh issue create -R PyneSys/pynecore --title "<title line>" --body-file qg/upstream/<slug>.md`;
3. the row's issue cell becomes the URL (`check_fork_md.py` keeps the PR red until then);
4. a PR to upstream only where the issue invites one (upstream closes external PRs and
   re-implements from reproductions, `pynecore-upstream/FINDINGS.md` "External PRs");
5. when upstream ships an equivalent, the row's status becomes `drop at next rebase (upstream
   <version>)` and Task 5's drift gate decides the equivalence.

## Carried patches

| Commit | Why (spec) | Upstream issue | Status |
|---|---|---|---|
| feat(math): window re-sum mode for math.sum | spec §9.2 E1; default off until the §9.2 gate (Task 5) | pending: qg/upstream/e1-window-resum.md | carried, default off |

## Engine findings without a patch

| Finding | Spec | Upstream | Status |
|---|---|---|---|
| `ta.pivot_point_levels`: R4/S4/R5/S5 are NaN | §9.2 | to file | not offered until fixed (§9.2) |
| `smc_luxalgo`: live crash with FVG-15m and daily levels both on (each alone passes) | §1.5 | to file | watched |
| `request.security`: contexts frozen in live with host data | §4.7 | upstream #49 watched | served by the service's shared feeds (§4.7), not PyneCore's contexts |

## Gates

Filled by Tasks 4 and 5: the §13.1 bit-identity gates (pristine, fingerprint, partners, inventory) and the golden, E1, drift and speed gates ship as the installed package `pynecore.qg_gates` and run in this fork's CI on synthetic data; the catalogue run over the real fixtures is Plan 1's private CI.

## Releases and the service pin

Filled by Task 6: release tag `6.10.10-qg.1` (package version `6.10.10+qg.1`, PEP 440), never a GitHub Release (it triggers upstream's PyPI workflow), and the indicator service's pin `pynesys-pynecore==6.10.10+qg.1` via `[tool.uv.sources]` on tag `6.10.10-qg.1`.
