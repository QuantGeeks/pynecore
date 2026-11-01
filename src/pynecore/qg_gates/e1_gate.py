"""E1 gate — the window re-sum reproduction against an export's own SMA column.

Spec §9.2's gate: ``scripts/e1_sma40.py`` runs on each export's own bars in
BOTH sum modes, each mode in its own process (``pristine.py``), and its
``sma40`` plot is compared with the export's column index 6.  The reproduction
holds on the reference export when the window mode's exact count equals
``--expect-window``, the compensated count is below it, and equals
``--expect-compensated`` when given.  A further export agrees when the window
mode is exact on every compared bar and the compensated machine is not.  The
gate prints PASSED when two further exports agree; until then the window mode
stays off by default (README ruling 9).
"""
import argparse
import fnmatch
import json
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

from pynecore.qg_gates import common

PRISTINE = Path(__file__).resolve().parent / "pristine.py"
SCRIPT = Path(__file__).resolve().parent / "scripts" / "e1_sma40.py"
COL = 6  # the export's first plot column: the SMA


def _stems(fx: Path, pattern: str) -> list[str]:
    stems = sorted(m.name[:-len(".manifest.json")] for m in fx.glob("*.manifest.json"))
    return [s for s in stems if fnmatch.fnmatch(s, pattern)]


def _csv_for(fx: Path, stem: str) -> Path:
    manifest = fx / f"{stem}.manifest.json"
    return fx / (json.loads(manifest.read_text())["file"] if manifest.is_file() else f"{stem}.csv.gz")


def _run_modes(bars, syminfo=None) -> dict[str, list]:
    """The script in each sum mode, each in its own pristine process; the rows'
    plot values by name (repr round-trips a float exactly)."""
    out: dict[str, list] = {}
    with tempfile.TemporaryDirectory() as td:
        data = Path(td) / "d.pkl"
        common.write_data(data, bars, syminfo)
        for mode in ("compensated", "window"):
            rows_pkl = Path(td) / f"o_{mode}.pkl"
            p = subprocess.run([sys.executable, "-I", str(PRISTINE), "--script", str(SCRIPT),
                                "--data", str(data), "--out", str(rows_pkl), "--sum-mode", mode],
                               capture_output=True, text=True)
            if p.returncode != 0:
                print(p.stdout.strip() or p.stderr.strip())
                raise SystemExit(1)
            rows = pickle.loads(rows_pkl.read_bytes())
            out[mode] = [float(v) if k == "sma40" else v
                         for _ts, pairs, _d in rows for k, v in pairs if k == "sma40"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path, help="an indicator-scripts checkout (private CI)")
    ap.add_argument("--reference", required=True)
    ap.add_argument("--further", required=True, help="glob over further export stems")
    ap.add_argument("--expect-window", type=int, required=True)
    ap.add_argument("--expect-compensated", type=int)
    a = ap.parse_args()

    fx = a.root / "fixtures" / "tradingview"
    if not fx.is_dir():
        print(f"QG-GATES: {a.root} has no fixtures/tradingview/")
        return 2

    def exacts(stem: str) -> tuple[int, int, int, int]:
        bars, _headers, cols = common.load_tv_export(_csv_for(fx, stem))
        manifest = fx / f"{stem}.manifest.json"
        meta = json.loads(manifest.read_text()) if manifest.is_file() else {}
        modes = _run_modes(bars, common.fixture_syminfo(meta))
        c_ex, _c_r, n = common.compare_columns(cols[COL - 6], modes["compensated"], 0)
        w_ex, _w_r, _ = common.compare_columns(cols[COL - 6], modes["window"], 0)
        print(f"E1 {stem}: compensated exact {c_ex}/{n} window exact {w_ex}/{n}")
        return c_ex, w_ex, n

    c_ex, w_ex, n = exacts(a.reference)
    holds = w_ex == a.expect_window and c_ex < w_ex and \
        (a.expect_compensated is None or c_ex == a.expect_compensated)
    if not holds:
        print(f"E1 REPRODUCTION FAIL {a.reference}: compensated {c_ex} window {w_ex}")
        return 1

    agreeing = 0
    for stem in _stems(fx, a.further):
        if stem == a.reference:
            continue
        c_ex, w_ex, n = exacts(stem)
        if w_ex == n and c_ex < n:
            agreeing += 1
    if agreeing >= 2:
        print("E1 GATE (§9.2): PASSED")
    else:
        print(f"E1 GATE (§9.2): {agreeing} of 2 further exports agree; "
              f"window mode stays off by default")
    return 0


if __name__ == "__main__":
    sys.exit(main())
