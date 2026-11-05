"""input.int hands the script a Python int (default and settings override), the arithmetic derived from it
stays int, and the drawings built from it hold and serialize integers: a width 2 is 2, a bar-index x 23 is
23 (never 2.0 / 23.0). Synthetic bars."""
import json
import sys
from pathlib import Path

from pynecore.core import viz
from pynecore.core.script_runner import ScriptRunner
from pynecore.lib import label, line
from pynecore.qg_gates.common import default_syminfo, synthetic_bars

SCRIPT = Path(__file__).resolve().parent / "scripts" / "int_input.py"


def _run(inputs=None):
    sys.modules.pop(SCRIPT.stem, None)
    r = ScriptRunner(script_path=SCRIPT, ohlcv_iter=iter(synthetic_bars(3, 30)), syminfo=default_syminfo(),
                     inputs=inputs)
    for _ in r.run_iter():
        pass
    snap = json.loads(json.dumps(viz.drawings_snapshot()))
    return snap, line.all()[0], label.all()[0]


def __test_input_int_default_and_derived_values_are_ints__():
    snap, ln, lb = _run()
    assert lb.text == "2|8|10", lb.text  # not "2.0|8.0|10.0"
    assert type(ln.width) is int and ln.width == 2
    assert type(ln.x1) is int and ln.x1 == 10 and type(ln.x2) is int and ln.x2 == 23
    assert type(lb.x) is int and lb.x == 23


def __test_input_int_from_the_settings_is_an_int__():
    _, ln, lb = _run({"width": 5, "offset": 4, "bars": 7})
    assert lb.text == "5|13|7", lb.text
    assert type(ln.width) is int and ln.width == 5


def __test_the_snapshot_spells_int_fields_as_integers__():
    snap, _, _ = _run()
    text = json.dumps(snap)
    li, la = snap["lines"][0], snap["labels"][0]
    assert (li["x1"], li["x2"], li["width"], la["x"]) == (10, 23, 2, 23)
    assert all(type(v) is int for v in (li["x1"], li["x2"], li["width"], la["x"])), text
    assert '"width": 2,' in text and '"x2": 23,' in text  # never 2.0 / 23.0
    # and the serializer converts a double that reaches it, whatever put it there
    from pynecore.core.viz import _int_field
    assert _int_field(40959.0) == 40959 and type(_int_field(40959.0)) is int
    assert _int_field(None) is None
