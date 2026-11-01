"""Speed budget — µs per bar per script and mode, against the catalogue's worst.

``run_one.py``'s timing kept: the wall time between ``run_iter`` yields, the
first 200 bars skipped, the median — one process per run, the median of
``--runs`` (default 5) per-run medians.  Layer A runs on ``synthetic_bars(7,
8580)`` (8,580 = the proof's SPY RTH 1m count); the catalogue's scripts (with
``--root``) run on their first fixture's bars.  The budget is 25.5 µs/bar —
1.5× the slowest median of the 25 standard scripts (ichimoku, SPY RTH 1m,
``proof/catalogue/REPORT.md``) — for Layer A and ``standard/`` in both modes;
``house/`` scripts are reported only (a heavy house script is the governor's
case, spec §4.2, not an engine regression).  With ``--baseline-python`` each
line carries the base (compensated under the baseline, which has no window
mode) and the ratio.  What is gated (ruling 2026-11-01, after CI failed the
absolute budget on a 2-core runner while laptop and docker passed): WITH a
baseline, a script fails when any mode's ratio r > 1.25 — upstream measured on
the same machine in the same run is the only comparison that means anything on
unknown hardware — and the absolute y is reported only; WITHOUT a baseline
(laptop-class hardware), the absolute y > 25.5 gates.  ``run_all.sh`` and the
CI workflow always pass the baseline, so CI gates the ratio.
``QG_PERF_INJECT_US`` busy-waits
n µs per bar under the measured python only (the control).  The per-state
``activate`` p50 over 60 states is reported too (reference 100 µs,
``proof/scale/REPORT.md``), never gated.
"""
import argparse
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
RATIO_BUDGET = 1.25  # against upstream measured in the same run (ruling 2026-11-01)
LAYER_A_DIR = Path(common.__file__).resolve().parent / "scripts"

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
for _c, _p in r.run_iter():
    n = time.perf_counter()
    if t_prev is not None:
        ts.append(n - t_prev)
    if inject:
        end = n + inject * 1e-6
        while time.perf_counter() < end:
            pass
    t_prev = n
w = ts[200:] if len(ts) > 400 else ts
print("%.3f" % (statistics.median(w) * 1e6))
"""


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
    return statistics.median(times)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", required=True)
    ap.add_argument("--baseline-python")
    ap.add_argument("--root", type=Path, help="an indicator-scripts checkout (private CI)")
    ap.add_argument("--runs", type=int, default=5)
    a = ap.parse_args()

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
            data.write_bytes(pickle.dumps((bars, common.default_syminfo())))
            scripts.append((job.script.stem if LAYER_A_DIR in job.script.parents
                            else job.id.rsplit("@", 1)[0], job.script, data))

        base_by_script: dict[Path, float] = {}
        if a.baseline_python:
            for sid, script, data in scripts:
                runs = [_median_us(a.baseline_python, script, data, base_env) for _ in range(a.runs)]
                base_by_script[script] = statistics.median(runs)

        failed = 0
        for sid, script, data in scripts:
            bad = False
            for mode in ("compensated", "window"):
                menv = dict(env)
                if mode == "window":
                    menv["PYNE_SUM_MODE"] = "window"
                y = statistics.median([_median_us(a.python, script, data, menv)
                                       for _ in range(a.runs)])
                ratio = y / base_by_script[script] if script in base_by_script else None
                line = f"PERF {sid} {mode} {y:.1f} us/bar (budget {BUDGET})"
                if ratio is not None:
                    line += f" base {base_by_script[script]:.1f} ratio {ratio:.2f}"
                print(line)
                gated = ratio > RATIO_BUDGET if ratio is not None else y > BUDGET
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
