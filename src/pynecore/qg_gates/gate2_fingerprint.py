"""Gate 2 — no unmanaged state survives a run (spec 13.1, gate 2).

``fp_run.py`` kept, in its three forms: a warm pass (lazy one-time
initialisation done), then a sequential pass — every job in a shuffled order on
rotated data — and an interleaved pass; after each run a FRESH state is
installed (everything the swap manages goes back to baseline values) and every
reachable pynecore leaf is fingerprinted (``fingerprint.py``, kept whole).  A
path that changes between consecutive fingerprints is state a run mutated that
the swap does NOT manage.  The data-dependence form runs each distinct script
on two different series and compares the fingerprints.  ``pynecore.transformers``
paths are ignored, as the proof's ``g2_summary`` ignored them.
"""
import argparse
import random
import sys

from pynecore.qg_gates import common
from pynecore.qg_gates import fingerprint as FP

IGN = ("pynecore.transformers",)


def _take(rs):
    rs.activate(rs.new_runner_state())
    return {k: v for k, v in FP.fingerprint().items() if not k.startswith(IGN)}


def _run(rs, job, bars):
    s = rs.new_runner_state()
    g = rs.create_runner(s, script_path=job.script, ohlcv_iter=iter(bars),
                         syminfo=common.default_syminfo(),
                         lossless_prices=True, lossless_volume=True).run_iter()
    for _ in g:
        pass
    rs.discard(s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=common.Path, help="an indicator-scripts checkout (private CI)")
    a = ap.parse_args()

    from pynecore.core import runner_state as rs
    jobs = common.layer_a_jobs()
    if a.root:
        jobs += common.catalogue_jobs(a.root)
    pool = [common.synthetic_bars(s) for s in (1, 2, 3)]  # the proof's SPY/QQQ/NVDA

    for job in jobs:  # warm pass: one-time initialisation, never compared
        _run(rs, job, job.bars)

    fps = [("start", _take(rs))]
    order = list(jobs)
    random.Random(3).shuffle(order)
    for k, job in enumerate(order):  # sequential pass, rotated data pairing
        _run(rs, job, pool[k % 3])
        fps.append((f"{job.id} on seed {k % 3 + 1}", _take(rs)))
    steady: set[str] = set()
    for (_n0, f0), (_n1, f1) in zip(fps, fps[1:]):
        steady |= set(FP.diff(f0, f1))

    common.interleave(order)  # interleaved pass
    interleaved = set(FP.diff(fps[-1][1], _take(rs)))

    data_dependent = 0
    for script in sorted({job.script for job in jobs}, key=str):
        probe = common.Job(f"probe", script, [])
        _run(rs, probe, pool[0])
        fa = _take(rs)
        _run(rs, probe, pool[1])
        fb = _take(rs)
        if FP.diff(fa, fb):
            data_dependent += 1

    print(f"GATE2 steady {len(steady)} interleaved {len(interleaved)} data-dependent {data_dependent}")
    return 0 if not steady and not interleaved and data_dependent == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
