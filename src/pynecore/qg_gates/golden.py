"""Golden gate — our values against a TradingView export, column by column.

The spec is Plan 1 Task 12's ``golden.json``: a JSON list of objects of exactly
``{"script": "standard/sma", "stem": "…", "columns": [{"tv_index": 6, "plot":
"MA", "shift": 0}]}`` with the optional keys ``inputs`` (default ``{}``),
``sum_mode`` (default ``"compensated"``, ruling 9) and ``warmup_bars``
(default 1500, the tvtruth method).  The column mapping is written once, by
``tv_index`` — no title matching.  Each entry's script runs on the export's own
bars under its own state; a column passes when rel9 covers every compared bar.
The E2 ``shift`` is applied here in the harness, as the service will (README
ruling 2): ``shifted(v, k) = v[k:] + [None] * k``.
"""
import argparse
import json
import sys
from pathlib import Path

from pynecore.qg_gates import common


def _shifted(values: list, k: int) -> list:
    return values if not k else values[k:] + [None] * k


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, type=Path, help="an indicator-scripts checkout (private CI)")
    ap.add_argument("--spec", required=True, type=Path, help="Plan 1 Task 12's golden.json")
    a = ap.parse_args()

    fx = a.root / "fixtures" / "tradingview"
    if not fx.is_dir():
        print(f"QG-GATES: {a.root} has no fixtures/tradingview/")
        return 2
    spec = json.loads(a.spec.read_text())

    def _num(v):
        if v is None:
            return float("nan")
        try:
            return float(v)
        except Exception:
            return float("nan")

    total = failed = 0
    for entry in spec:
        script = a.root / entry["script"] / f"{entry['script'].rsplit('/', 1)[-1]}.py"
        stem = entry["stem"]
        manifest = fx / f"{stem}.manifest.json"
        csv = fx / (json.loads(manifest.read_text())["file"] if manifest.is_file() else f"{stem}.csv.gz")
        bars, _headers, cols = common.load_tv_export(csv)
        rows = common._run_swapped(script, bars, entry.get("inputs") or {},
                                   entry.get("sum_mode", "compensated"))
        for col in entry["columns"]:
            total += 1
            tv = cols[col["tv_index"] - 6]
            ours = _shifted([_num(p.get(col["plot"])) for _c, p in rows], col.get("shift", 0))
            exact, rel9, n = common.compare_columns(tv, ours, entry.get("warmup_bars", 1500))
            print(f"GOLDEN {entry['script']} {stem} [{col['tv_index']}→{col['plot']}]: "
                  f"exact {exact}/{n} rel9 {rel9}/{n}")
            if rel9 != n:
                failed += 1

    if failed:
        print(f"GOLDEN FAIL {failed} of {total} columns")
        return 1
    print(f"GOLDEN PASS {total} columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
