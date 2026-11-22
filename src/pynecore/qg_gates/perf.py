"""Speed budget — µs per bar per script and mode, against the catalogue's worst.

``run_one.py``'s timing kept: the wall time between ``run_iter`` yields, the
first 200 bars skipped, the median — one process per run.  Layer A runs on
``synthetic_bars(7, 8580)`` (8,580 = the proof's SPY RTH 1m count); the
catalogue's scripts (with ``--root``) run on their first fixture's bars.  The
budget is 25.5 µs/bar — 1.5× the slowest median of the 25 standard scripts
(ichimoku, SPY RTH 1m, ``proof/catalogue/REPORT.md``) — for Layer A and
``standard/`` in both modes; ``house/`` scripts are reported only (a heavy
house script is the governor's case, spec §4.2, not an engine regression).

LIKE FOR LIKE IS ENFORCED, NOT RULED (2026-11-22, replacing the 2026-11-21
ruling the fleet falsified): with ``--baseline-python`` the gate first
fingerprints BOTH interpreters — implementation, ``sys.version``,
``sysconfig.get_platform()``, and whether each compiled native
(``_native_math``, ``_native_color``, ``_native_rolling_sum``) is importable —
and REFUSES (exit 2) on any mismatch before a single timing.  A PyPI wheel
against a git/sdist install differs in the natives; a homebrew CPython differs
in the build string (~15% slower than the uv build of the same 3.12, measured
2026-11-21); neither may reach a ratio.

MEASUREMENT, with a baseline: base and head INTERLEAVE round-robin — each of
``--runs`` (default 5) rounds measures, per script, the head (compensated,
then window) and the base back to back, the order alternating by round parity
so slow drift (thermal, load, page cache) lands on both sides equally; never
all of one side first.  The budgeted statistic is the MEDIAN OF PER-ROUND
RATIOS head/base (compensated) — one noisy round cannot fail the gate, a real
slowdown present every round still does — and for the window mode the median
of per-round ``window/compensated``.  WITHOUT a baseline (laptop-class
hardware) the absolute median y > 25.5 gates.  ``run_all.sh`` and the CI
workflow always pass the baseline, so CI gates the ratio.

The window mode is judged against the SAME run's compensated time, never
upstream's: the window re-sum is O(length) against the O(1) accumulator, so
window-vs-upstream compares two algorithms (ruling 2026-11-02; a shared runner
printed compensated 22.2 / window 25.9 on code whose normal window is 15.7).
``QG_PERF_INJECT_US`` busy-waits n µs per bar under the measured python only
(the control); ``QG_PERF_INJECT_WINDOW_US`` and
``QG_PERF_INJECT_WINDOW_FACTOR`` do the same for the window mode.  The
per-state ``activate`` p50 over 60 states is reported too (reference 100 µs,
``proof/scale/REPORT.md``), never gated.
"""
import argparse
import json
import os
import pickle
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pynecore.qg_gates import common

BUDGET = 25.5       # absolute, laptop-class hardware (no baseline given)
RATIO_BUDGET = 1.25  # median of per-round ratios, compensated vs upstream
# window vs the same run's compensated: measured 1.14-1.42 (bollinger's three
# sums 1.42), 1.75 leaves the margin the 1.25 ratio leaves Layer A
WINDOW_OVER_COMPENSATED = 1.75
LAYER_A_DIR = Path(common.__file__).resolve().parent / "scripts"
_NATIVES = ("_native_math", "_native_color", "_native_rolling_sum")

# The identity a measured python must report: the interpreter build plus which
# compiled natives the install actually carries.  A wheel install answers with
# all three, a git/sdist install with none (its setup does not build them) --
# the confound that once settled a red gate by ruling instead of by refusal.
_PROBE_CODE = """
import importlib.util, json, sys, sysconfig
try:
    natives = sorted(n for n in %(natives)r
                     if importlib.util.find_spec("pynecore.core." + n) is not None)
except Exception:
    natives = None  # pynecore itself is not importable under this interpreter
print(json.dumps({"implementation": sys.implementation.name, "version": sys.version,
                  "platform": sysconfig.get_platform(), "natives": natives}))
""" % {"natives": _NATIVES}

_RUN_CODE = """
import os, time, statistics, pickle
from pathlib import Path
if os.environ.get("PYNE_SUM_MODE") == "window":
    from pynecore.core import rolling_sum
    rolling_sum.set_sum_mode("window")
from pynecore.core.script_runner import ScriptRunner
bars, syminfo = pickle.loads(Path(%(data)r).read_bytes())
r = ScriptRunner(script_path=Path(%(script)r), ohlcv_iter=iter(bars), syminfo=syminfo,
                 lossless_prices=True, lossless_volume=True)
t_prev = None
ts = []
inject = float(os.environ.get("QG_PERF_INJECT_US", "0") or "0")
if not inject and os.environ.get("PYNE_SUM_MODE") == "window":
    inject = float(os.environ.get("QG_PERF_INJECT_WINDOW_US", "0") or "0")
# Relative window injection (ruling 2026-11-02): an absolute us divided by the
# machine's own step time is machine-dependent; factor x the bar's own measured
# step keeps the ratio (1 + factor) on every machine.
win_factor = 0.0
if os.environ.get("PYNE_SUM_MODE") == "window":
    win_factor = float(os.environ.get("QG_PERF_INJECT_WINDOW_FACTOR", "0") or "0")
for _c, _p in r.run_iter():
    n = time.perf_counter()
    if t_prev is not None:
        if win_factor:
            # Sleep factor x THIS bar's own step: the clock is reset after every
            # sleep, so a step never contains a previous sleep and the ratio is
            # exactly (1 + factor) -- a sleep proportional to the interval since
            # t_prev would feed back on itself and diverge for factor >= 1.
            step = n - t_prev
            end = n + win_factor * step
            while time.perf_counter() < end:
                pass
            n = time.perf_counter()
            ts.append(n - t_prev)
        else:
            ts.append(n - t_prev)
    if inject:
        end = n + inject * 1e-6
        while time.perf_counter() < end:
            pass
    t_prev = n
w = ts[200:] if len(ts) > 400 else ts
print("%.3f" % (statistics.median(w) * 1e6))
"""


def _fingerprint(python: str) -> dict:
    """The probe's one JSON line, parsed; ``natives`` is None when pynecore
    itself is not importable under ``python``."""
    p = subprocess.run([python, "-I", "-c", _PROBE_CODE], capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stdout.strip() or p.stderr.strip(), file=sys.stderr)
        raise SystemExit(1)
    return json.loads(p.stdout.strip().splitlines()[-1])


def _like_for_like_error(head: dict, base: dict, head_py: str, base_py: str) -> str | None:
    """Why these two installs may not be compared, or None if they may."""
    if head["implementation"] != base["implementation"]:
        return (f"interpreter implementation differs: {head['implementation']} "
                f"({head_py}) vs {base['implementation']} ({base_py})")
    if head["version"] != base["version"]:
        return (f"interpreter build differs: {head_py} is {head['version']!r}, "
                f"{base_py} is {base['version']!r}")
    if head["platform"] != base["platform"]:
        return (f"binary platform differs: {head_py} is {head['platform']}, "
                f"{base_py} is {base['platform']}")
    if head["natives"] is None or base["natives"] is None:
        missing = head_py if head["natives"] is None else base_py
        return f"pynecore is not importable under {missing}"
    if head["natives"] != base["natives"]:
        return (f"compiled natives differ: {head_py} carries {head['natives']}, "
                f"{base_py} carries {base['natives']} -- a wheel-vs-sdist install mismatch")
    return None


def _round_order(round_index: int) -> tuple[str, ...]:
    """Which side runs first inside this round; the winner flips every round so
    slow drift (thermal, load, page cache) lands on both sides equally."""
    return ("head", "base") if round_index % 2 == 0 else ("base", "head")


def _median_us(python: str, script: Path, data_pkl: Path, env: dict) -> float:
    code = _RUN_CODE.replace("%(data)r", repr(str(data_pkl))).replace("%(script)r", repr(str(script)))
    p = subprocess.run([python, "-I", "-c", code], capture_output=True, text=True, env=env)
    if p.returncode != 0:
        print(p.stdout.strip() or p.stderr.strip(), file=sys.stderr)
        raise SystemExit(1)
    return float(p.stdout.strip().splitlines()[-1])


def _activate_p50_us() -> float:
    from pynecore.core import runner_state as rs
    states = [rs.new_runner_state() for _ in range(60)]
    rs.activate(states[0])
    times = []
    for i in range(600):
        t = time.perf_counter()
        rs.activate(states[i % 60])
        times.append((time.perf_counter() - t) * 1e6)
    for s in states:  # leave no state current (qg/tests/conftest.py enforces it)
        rs.discard(s)
    return statistics.median(times)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", required=True)
    ap.add_argument("--baseline-python")
    ap.add_argument("--root", type=Path, help="an indicator-scripts checkout (private CI)")
    ap.add_argument("--runs", type=int, default=5)
    a = ap.parse_args()

    base_by_script: dict[Path, list[float]] = {}
    if a.baseline_python:
        error = _like_for_like_error(_fingerprint(a.python), _fingerprint(a.baseline_python),
                                     a.python, a.baseline_python)
        if error is not None:
            print(f"PERF REFUSE head and base are not like for like: {error}")
            print("PERF BUDGET REFUSED (fix the interpreters/installs, do not re-run hoping)")
            return 2

    env = dict(os.environ, PYNE_SAVE_SCRIPT_TOML="0")
    # QG_PERF_INJECT_US reaches the measured runs only (under P1), never the baseline's
    base_env = {k: v for k, v in env.items() if k != "QG_PERF_INJECT_US"}

    jobs = common.layer_a_jobs()
    if a.root:
        jobs += common.catalogue_jobs(a.root)

    scripts: list[tuple[str, Path, Path]] = []  # (id, script, bars+syminfo pickle for the subprocess)
    with tempfile.TemporaryDirectory() as td:
        for job in jobs:
            if any(s[1] == job.script for s in scripts):
                continue
            bars = common.synthetic_bars(7, 8580) if LAYER_A_DIR in job.script.parents else job.bars
            data = Path(td) / f"{job.id.replace('/', '_')}.pkl"
            data.write_bytes(pickle.dumps((bars, job.syminfo or common.default_syminfo())))
            scripts.append((job.script.stem if LAYER_A_DIR in job.script.parents
                            else job.id.rsplit("@", 1)[0], job.script, data))

        # Interleaved rounds: per round, per script, the head's two modes and
        # the base run back to back, first serve alternating by round parity --
        # never all of one side first (the fleet's base columns swung 1.12-1.71x
        # between same-code runs measured back to back, 2026-11-21).
        comp_by_script: dict[Path, list[float]] = {}
        win_by_script: dict[Path, list[float]] = {}
        for r in range(a.runs):
            order = _round_order(r) if a.baseline_python else ("head",)
            for _sid, script, data in scripts:
                for side in order:
                    if side == "head":
                        comp_by_script.setdefault(script, []).append(
                            _median_us(a.python, script, data, env))
                        win_env = dict(env, PYNE_SUM_MODE="window")
                        win_by_script.setdefault(script, []).append(
                            _median_us(a.python, script, data, win_env))
                    else:
                        base_by_script.setdefault(script, []).append(
                            _median_us(a.baseline_python, script, data, base_env))

        failed = 0
        for sid, script, data in scripts:
            bad = False
            for mode in ("compensated", "window"):
                rounds = (comp_by_script if mode == "compensated" else win_by_script)[script]
                y = statistics.median(rounds)  # robust per-script summary
                rounds_b = base_by_script.get(script) if a.baseline_python else None
                ratios = ([h / b for h, b in zip(rounds, rounds_b)] if rounds_b else None)
                ratio = statistics.median(ratios) if ratios else None
                line = f"PERF {sid} {mode} {y:.1f} us/bar (budget {BUDGET})"
                gated = False
                if mode == "compensated":
                    if ratio is not None:
                        # Like for like with upstream: the only comparison that
                        # means anything on unknown hardware (ruling 2026-11-01),
                        # now enforced per round and judged on the median.
                        line += (f" base {statistics.median(rounds_b):.1f} ratio {ratio:.2f}"
                                 f" rounds {'/'.join(f'{x:.2f}' for x in ratios)}")
                        gated = ratio > RATIO_BUDGET
                    else:
                        gated = y > BUDGET
                else:
                    if ratio is not None:
                        # The window re-sum is O(length) against the O(1)
                        # accumulator, so window-vs-upstream compares two
                        # algorithms and an absolute budget measures the runner,
                        # not the code; the like-for-like comparison is the
                        # window cost over the SAME run's compensated time.
                        over = statistics.median([w / c for w, c in zip(rounds, comp_by_script[script])])
                        line += (f" base {statistics.median(rounds_b):.1f} ratio {ratio:.2f}"
                                 f" vs compensated {over:.2f}"
                                 f" rounds {'/'.join(f'{x:.2f}' for x in ratios)}")
                        gated = over > WINDOW_OVER_COMPENSATED
                    else:
                        # A local run without a baseline: the absolute budget.
                        gated = y > BUDGET
                print(line)
                if gated and not sid.startswith("house/"):
                    bad = True
            if bad:
                failed += 1

    print(f"PERF activate p50 {_activate_p50_us():.0f} us (60 states)")
    if failed:
        print(f"PERF BUDGET FAIL {failed} scripts")
        return 1
    print("PERF BUDGET PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
