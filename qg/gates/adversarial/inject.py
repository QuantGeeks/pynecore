#!/usr/bin/env python3
"""Inject the adversarial hook into a venv's installed pynecore (fork CI only).

Copies ``_adv.py`` (kept verbatim from the proof) into ``<dir>/pynecore/core/``
and rewrites the single ``return change(source, length)`` in
``<dir>/pynecore/lib/ta.py`` — the body of ``ta.momentum`` — to the hook
``return _adv.hook(change(source, length), int(bar_index), length)``.  Env
``ADV=A..E`` selects the bug: A a class-attribute counter, B a closure-captured
dict, C a mutable dict inside a module-level tuple, D an ALLCAPS module dict,
E a class attribute never read.  Run twice on the same venv is refused (the
first pass rewrote the only match).
"""
import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = "return change(source, length)"
NEW = ("from ..core import _adv\n"
       "    return _adv.hook(change(source, length), int(bar_index), length)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-packages", required=True, type=Path)
    a = ap.parse_args()

    sp = a.site_packages
    shutil.copyfile(HERE / "_adv.py", sp / "pynecore" / "core" / "_adv.py")
    ta = sp / "pynecore" / "lib" / "ta.py"
    src = ta.read_text()
    k = src.count(OLD)
    if k != 1:
        print(f"INJECT: expected 1 match, found {k}")
        return 1
    ta.write_text(src.replace(OLD, NEW))
    return 0


if __name__ == "__main__":
    sys.exit(main())
