"""An int derived from input.int is exact Python arithmetic; where it reaches a float sink (a plot, the viz
record) too large for a double it becomes inf, as the double the engine used before gave (no OverflowError)."""
import json
import math
import sys
from pathlib import Path

from pynecore.core.script_runner import ScriptRunner
from pynecore.qg_gates.common import default_syminfo, synthetic_bars

SCRIPT = Path(__file__).resolve().parent / "scripts" / "int_overflow.py"


def __test_a_bigint_reaching_a_float_sink_is_inf_not_a_crash__(tmp_path):
    sys.modules.pop(SCRIPT.stem, None)
    viz_path = tmp_path / "out.viz"
    r = ScriptRunner(script_path=SCRIPT, ohlcv_iter=iter(synthetic_bars(3, 3)), syminfo=default_syminfo(),
                     viz_path=viz_path)
    rows = [dict(p) for _, p in r.run_iter()]
    assert all(row["f"] == math.inf and row["g"] == -math.inf for row in rows), rows
    bars = [json.loads(line) for line in viz_path.read_text().splitlines() if '"t": "bar"' in line or '"t":"bar"' in line]
    assert bars, viz_path.read_text()[:300]
    assert all(b["v"]["f"] is None and b["v"]["g"] is None for b in bars), bars[0]  # non-finite is written as null
