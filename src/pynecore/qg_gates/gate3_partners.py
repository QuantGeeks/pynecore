"""Gate 3 — co-resident runners equal per-process pristine runs (spec 13.1, gate 3).

``gate3.py`` kept, adapted: every job gets a PRISTINE reference — ``pristine.py``
run by path in its own process, plain PyneCore, no swap — then K=6 partner
trials (random pick of R = min(10, jobs) runners, pick rng seeded ``1000 + k``,
the first two forced to the same script on different data, random step order,
N=600) plus one trio trial per distinct script (the script on all three data,
R=5, two random others).  Every runner's rows are compared bar-by-bar to its
reference.  Layer A: 6 × 6 + 2 × 5 = 46 runners.
"""
import argparse
import random
import sys
import tempfile
from pathlib import Path

from pynecore.qg_gates import common

PRISTINE = Path(__file__).resolve().parent / "pristine.py"
K = 6
N = 600


def _dedupe(pick: list) -> list:
    """Jobs carry lists, so they are unhashable: dedupe by id."""
    seen: set[str] = set()
    return [j for j in pick if not (j.id in seen or seen.add(j.id))]


def _top_up(pick: list, jobs: list, r: int) -> list:
    """A trial holds exactly ``r`` runners: replacing pick[0]/pick[1] with the
    same-script pair can duplicate an entry, so refill from the unused jobs."""
    have = {j.id for j in pick}
    for j in jobs:
        if len(pick) >= r:
            break
        if j.id not in have:
            pick.append(j)
            have.add(j.id)
    return pick


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=common.Path, help="an indicator-scripts checkout (private CI)")
    a = ap.parse_args()
    import subprocess
    import pickle

    jobs = common.layer_a_jobs()
    if a.root:
        jobs += common.catalogue_jobs(a.root)

    refs: dict[str, list] = {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for i, job in enumerate(jobs):
            data, out = td / f"d{i}.pkl", td / f"o{i}.pkl"
            common.write_data(data, job.bars)
            p = subprocess.run([sys.executable, "-I", str(PRISTINE), "--script", str(job.script),
                                "--data", str(data), "--out", str(out)],
                               capture_output=True, text=True)
            if p.returncode != 0:
                print(p.stdout.strip() or p.stderr.strip())
                print(f"GATE3 total mismatching runners 1/{len(jobs)}")
                return 1
            refs[job.id] = pickle.loads(out.read_bytes())

    trials: list[tuple[str, list[common.Job], int]] = []
    for k in range(K):
        rnd = random.Random(1000 + k)
        R = min(10, len(jobs))
        pick = rnd.sample(jobs, R)
        same = [j for j in jobs if j.script == pick[0].script]
        if len(same) >= 2:  # same script, different data ([adapt] of the proof's symbols)
            pick[0], pick[1] = same[0], same[1]
        pick = _top_up(_dedupe(pick), jobs, R)
        trials.append((f"trial {k}", pick, k))
    for j, script in enumerate(sorted({j.script for j in jobs}, key=str)):
        rnd = random.Random(1000 + K + j)
        trio = [job for job in jobs if job.script == script][:3]
        others = [job for job in jobs if job.script != script]
        trio = _top_up(_dedupe(trio + rnd.sample(others, min(2, len(others)))), jobs, 5)[:5]
        trials.append((f"trio {script.stem}", trio, K + j))

    bad_total = runners_total = 0
    for name, pick, seed in trials:
        _solo, together = common.interleave(pick, order="random", seed=seed)
        bad = [job.id for job in pick if together.get(job.id) != refs[job.id]]
        bad_total += len(bad)
        runners_total += len(pick)
        print(f"{name}: {len(pick)} runners, mismatching vs pristine: {len(bad)} {bad[:4]}",
              file=sys.stderr)

    print(f"GATE3 total mismatching runners {bad_total}/{runners_total}")
    return 0 if bad_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
