#!/usr/bin/env python3
"""Run one script pristine, in its own process (spec 13.1; the gates' reference).

Standalone on purpose — imports only upstream modules, so an upstream install can
run it (Task 5's drift gate) — run by path, never as a module:

    python -I <dir of pynecore.qg_gates>/pristine.py --script <path> --data <in.pkl> \
        --out <out.pkl> [--live] [--sum-mode compensated|window]

``<in.pkl>`` is ``pickle.dumps((events, syminfo))`` as written by
``pynecore.qg_gates.common.write_data``.  Writes the rows — one
``(timestamp, sorted (plot, repr(value)) pairs, drawing counts)`` tuple per bar,
exactly the gates' ``row`` — to ``<out.pkl>``.  The mode is passed only by
``--sum-mode``; the default ``compensated`` never calls ``set_sum_mode``, so an
upstream PyneCore can run this file unchanged.
"""
import argparse
import os
import pickle
import sys
from pathlib import Path

os.environ.setdefault("PYNE_SAVE_SCRIPT_TOML", "0")


def _row(c, p):
    from pynecore.lib import label, line, box
    return (c.timestamp, tuple(sorted((k, repr(v)) for k, v in p.items())),
            (len(label.all()), len(line.all()), len(box.all())))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--script", required=True, type=Path)
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--sum-mode", default="compensated", choices=["compensated", "window"])
    a = ap.parse_args()

    if a.sum_mode != "compensated":
        from pynecore.core import rolling_sum
        if not hasattr(rolling_sum, "set_sum_mode"):
            print("PRISTINE: --sum-mode window needs the fork")
            return 2
        rolling_sum.set_sum_mode(a.sum_mode)

    events, syminfo = pickle.loads(a.data.read_bytes())
    from pynecore.core.script_runner import ScriptRunner, LIVE_TRANSITION
    # The pickled stream carries a field-equal copy of the sentinel; the runner
    # recognises LIVE_TRANSITION by identity, so put the module's own object back.
    events = [LIVE_TRANSITION if e == LIVE_TRANSITION else e for e in events]
    try:
        runner = ScriptRunner(script_path=a.script, ohlcv_iter=iter(events), syminfo=syminfo,
                              live=a.live, lossless_prices=True, lossless_volume=True)
        rows = [_row(c, p) for c, p in runner.run_iter()]
    except Exception as e:
        print(f"PRISTINE FAIL {a.script.stem}: {type(e).__name__}")
        return 1
    a.out.write_bytes(pickle.dumps(rows))
    print(f"PRISTINE OK {a.script.stem} {len(rows)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
