"""ta.pivot_point_levels returns every level each type defines: Traditional P..R5/S5, Classic P..R4/S4,
Woodie P..R4/S4, Camarilla P..R5/S5 (the formulas of TradingView's documentation); the levels a type does not
define (Fibonacci 4/5, Classic and Woodie 5, DM 3..5) stay na. Synthetic bars, hand-computed values."""
import math
import sys
from pathlib import Path

import pytest

from pynecore.core.script_runner import ScriptRunner
from pynecore.qg_gates.common import default_syminfo
from pynecore.types.ohlcv import OHLCV

SCRIPT = Path(__file__).resolve().parent / "scripts" / "pivot_levels.py"
NAMES = ["P", "R1", "S1", "R2", "S2", "R3", "S3", "R4", "S4", "R5", "S5"]
NA = None

# Period 1 (bars 0-2): high 15, low 8, last close 13, first open 10, range 7.
# Period 2 opens at bar 3 (open 12, high 13, low 11, close 12.5).
_ROWS = [(10, 12, 9, 11), (11, 15, 10, 14), (14, 14, 8, 13), (12, 13, 11, 12.5), (12.5, 13.5, 12, 13), (13, 14, 12.5, 13.5)]

# Hand-computed from H=15, L=8, C=13 (P = 12), woodie from the period-2 open 12.
EXPECTED = {
    "traditional": [12, 16, 9, 19, 5, 23, 2, 27, -1, 31, -4],
    "fibonacci": [12, 12 + .382 * 7, 12 - .382 * 7, 12 + .618 * 7, 12 - .618 * 7, 19, 5, NA, NA, NA, NA],
    "woodie": [11.75, 15.5, 8.5, 18.75, 4.75, 22.5, 1.5, 29.5, -5.5, NA, NA],
    "classic": [12, 16, 9, 19, 5, 26, -2, 33, -9, NA, NA],
    "dm": [None] * 11,  # set below
    "camarilla": [12, 13 + 7 * 1.1 / 12, 13 - 7 * 1.1 / 12, 13 + 7 * 1.1 / 6, 13 - 7 * 1.1 / 6,
                  13 + 7 * 1.1 / 4, 13 - 7 * 1.1 / 4, 13 + 7 * 1.1 / 2, 13 - 7 * 1.1 / 2, 15 / 8 * 13, 13 - (15 / 8 * 13 - 13)],
}
# DeMark: close 13 > open 10 -> X = 2H + L + C = 51; P = X/4, R1 = X/2 - L, S1 = X/2 - H
EXPECTED["dm"] = [51 / 4, 51 / 2 - 8, 51 / 2 - 15] + [NA] * 8
# Developing Traditional at the anchor bar: the period so far is bar 3 alone (H 13, L 11, C 12.5).
_P = (13 + 11 + 12.5) / 3
DEV = [_P, 2 * _P - 11, 2 * _P - 13, _P + 2, _P - 2, 2 * _P + (13 - 22), 2 * _P - (26 - 11),
       3 * _P + (13 - 33), 3 * _P - (39 - 11), 4 * _P + (13 - 44), 4 * _P - (52 - 11)]


def _rows():
    sys.modules.pop(SCRIPT.stem, None)
    bars = [OHLCV(1779802200000 + 60000 * i, float(o), float(h), float(l), float(c), 1.0)
            for i, (o, h, l, c) in enumerate(_ROWS)]
    runner = ScriptRunner(script_path=SCRIPT, ohlcv_iter=iter(bars), syminfo=default_syminfo())
    return [dict(p) for _, p in runner.run_iter()]


def _isna(v):
    return v is None or (isinstance(v, float) and math.isnan(v)) or type(v).__name__ == "NA"


@pytest.mark.parametrize("kind", list(EXPECTED))
def __test_every_level_a_type_defines_and_na_for_the_rest__(kind):
    rows = _rows()
    # bar 3 opens period 2 and the levels hold through bar 5
    for bar in (3, 4, 5):
        for name, want in zip(NAMES, EXPECTED[kind]):
            got = rows[bar][f"{kind}_{name}"]
            if want is NA:
                assert _isna(got), (kind, name, bar, got)
            else:
                assert not _isna(got) and got == pytest.approx(want, abs=1e-9), (kind, name, bar, got, want)
    # nothing before the first completed period
    assert all(_isna(rows[2][f"{kind}_{n}"]) for n in NAMES)


def __test_developing_levels_include_the_outer_ones__():
    row = _rows()[3]
    for name, want in zip(NAMES, DEV):
        got = row[f"dev_{name}"]
        assert not _isna(got) and got == pytest.approx(want, abs=1e-9), (name, got, want)
