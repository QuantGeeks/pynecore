"""Drift gate — the fork's default build against upstream's, job by job.

The proof's drift line, adapted: every job (Layer A, plus the catalogue with
``--root``) runs batch, compensated, via ``pristine.py`` under each interpreter
— the baseline never calls ``set_sum_mode``, so an upstream install can be the
baseline — and the two row lists are compared for exact equality.
``--candidate-env`` adds environment variables to the candidate's runs only
(the per-mode control).  With ``--require-identical`` any differing job fails
the gate: the fork's default build is upstream's (spec §13.1, drift).
"""
import argparse
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

from pynecore.qg_gates import common

PRISTINE = Path(__file__).resolve().parent / "pristine.py"


def _version(python: str) -> str:
    p = subprocess.run([python, "-I", "-c",
                        "import importlib.metadata as m; print(m.version('pynesys-pynecore'))"],
                       capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else "?"


def _rows(python: str, job: common.Job, td: Path, env: dict) -> list:
    data, out = td / f"d_{job.id.replace('/', '_')}.pkl", td / f"o_{python_to_tag(python)}_{job.id.replace('/', '_')}.pkl"
    common.write_data(data, job.bars)
    p = subprocess.run([python, "-I", str(PRISTINE), "--script", str(job.script),
                        "--data", str(data), "--out", str(out)],
                       capture_output=True, text=True, env=env)
    if p.returncode != 0:
        print(p.stdout.strip() or p.stderr.strip())
        raise SystemExit(1)
    return pickle.loads(out.read_bytes())


def python_to_tag(python: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in python)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-python", required=True)
    ap.add_argument("--candidate-python", required=True)
    ap.add_argument("--candidate-env", action="append", default=[])
    ap.add_argument("--root", type=Path, help="an indicator-scripts checkout (private CI)")
    ap.add_argument("--require-identical", action="store_true")
    a = ap.parse_args()

    jobs = common.layer_a_jobs()
    if a.root:
        jobs += common.catalogue_jobs(a.root)
    cand_env = dict(__import__("os").environ, PYNE_SAVE_SCRIPT_TOML="0")
    for kv in a.candidate_env:
        k, _sep, v = kv.partition("=")
        cand_env[k] = v

    import os
    base_env = dict(os.environ, PYNE_SAVE_SCRIPT_TOML="0")
    differ = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for job in jobs:
            base = _rows(a.baseline_python, job, td, base_env)
            cand = _rows(a.candidate_python, job, td, cand_env)
            if base != cand:
                differ.append(job.id)

    line = (f"DRIFT {_version(a.candidate_python)} vs {_version(a.baseline_python)}: "
            f"{len(differ)}/{len(jobs)} jobs differ [{', '.join(differ)}]")
    print(line)
    if a.require_identical and differ:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
