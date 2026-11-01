"""Gate 1 — co-resident runners equal their solo runs (spec 13.1, gate 1).

``gatelib.interleave`` kept, on Layer A (plus the catalogue with ``--root``):
every job runs once alone for its reference, then all jobs round-robin in one
process under the per-runner state; a job matches when its rows — plots by
``repr`` and drawing counts, batch and live — are equal.  ``--control`` drops
the per-step ``activate`` and must corrupt at least one runner.
"""
import argparse
import sys

from pynecore.qg_gates import common


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=common.Path, help="an indicator-scripts checkout (private CI)")
    ap.add_argument("--control", action="store_true")
    a = ap.parse_args()

    jobs = common.layer_a_jobs()
    if a.root:
        jobs += common.catalogue_jobs(a.root)
    n = len(jobs)

    if a.control:
        solo, together = common.interleave(jobs, control=True)
        k = len(common.mismatching(jobs, solo, together))
        print(f"GATE1 CONTROL corrupted {k}/{n}")
        return 0 if k > 0 else 1

    solo, together = common.interleave(jobs)
    batch_bad = len(common.mismatching(jobs, solo, together))
    solo, together = common.interleave(jobs, live=True)
    live_bad = len(common.mismatching(jobs, solo, together))
    print(f"GATE1 batch {batch_bad}/{n} live {live_bad}/{n}")
    return 0 if batch_bad == 0 and live_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
