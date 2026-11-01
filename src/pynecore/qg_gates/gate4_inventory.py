"""Gate 4 — the static state inventory (spec 13.1, gate 4; fork CI only).

``inventory.py`` kept: at import (``pynecore.core.runner_state`` imports all
lib/core/types modules like the real host does), every place pynecore code can
hold state, keyed by path with container indices and values dropped, the
``pynecore.transformers`` paths ignored.  ``--write`` records the inventory;
``--check`` compares against a recorded one — a path the engine grows or loses
is a review, not a silent pass.  Updating ``qg/gates/inventory.json`` in a PR
is the person's review (spec 13.1).
"""
import argparse
import json
import re
import sys
from pathlib import Path


def _inventory() -> list[str]:
    import pynecore.core.runner_state  # noqa: F401 -- imports all lib/core/types modules
    from pynecore.qg_gates import fingerprint as FP
    fp = FP.fingerprint()
    norm = lambda p: re.sub(r"<len>$", "", re.sub(r"\[[^\]]*\]", "[]", p))
    return sorted({norm(p) for p in fp if not p.startswith("pynecore.transformers")})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", type=Path)
    ap.add_argument("--check", type=Path)
    a = ap.parse_args()
    if bool(a.write) == bool(a.check):
        ap.error("exactly one of --write or --check is required")

    inv = _inventory()
    if a.write:
        a.write.write_text(json.dumps(inv, indent=0) + "\n")
        print(f"GATE4 wrote {len(inv)} paths")
        return 0

    old = json.loads(a.check.read_text())
    old_set, inv_set = set(old), set(inv)
    added = [p for p in inv if p not in old_set]
    removed = [p for p in old if p not in inv_set]
    if added or removed:
        print(f"GATE4 INVENTORY CHANGED: +{len(added)} -{len(removed)}")
        for p in added:
            print(f"  + {p}")
        for p in removed:
            print(f"  - {p}")
        return 1
    print(f"GATE4 inventory unchanged ({len(inv)} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
