"""The call-site tag is HOST metadata (a viewer's restyle key), never part of a drawing's
VALUE: it must stay out of every value/identity comparison, whose generic form walks the
dataclass fields (a private-CI twin snapshot failed exactly there — two script versions with
identical creation lines, one extra earlier site, compared equal on every field but the tag,
``('tag', 5)`` vs ``('tag', 4)``). By design the tag is therefore NOT a field of any drawing
type: ``fields()`` cannot carry it into a snapshot, an identity hash or a diff, while the
viz journal still emits it explicitly for the host. Two script versions whose shared call
sites renumber must field-snapshot identically. Synthetic bars."""
import sys
from dataclasses import fields
from pathlib import Path

from pynecore.core.script_runner import ScriptRunner
from pynecore.lib import box, chart, color, label, line, linefill, polyline, position, table
from pynecore.qg_gates.common import default_syminfo, synthetic_bars

SCRIPTS = Path(__file__).resolve().parent / "scripts"
A, B = SCRIPTS / "tagval_a.py", SCRIPTS / "tagval_b.py"


def _field_snapshot():
    """The generic identity form: every drawing of every kind as its field
    tuples (``vid`` skipped — a per-run id), in registry order, a linefill's
    endpoints as their index in the line registry — the way a value
    comparison with no knowledge of tags would build it."""
    lines = list(line._registry)
    index = {id(x): i for i, x in enumerate(lines)}

    def row(obj) -> tuple:
        return tuple((f.name, getattr(obj, f.name))
                     for f in fields(obj) if f.name != "vid")

    def lf_row(obj) -> tuple:
        return tuple((f.name, index.get(id(getattr(obj, f.name)), -1)
                      if f.name in ("line1", "line2") else getattr(obj, f.name))
                     for f in fields(obj) if f.name != "vid")

    return {
        "lines": [row(x) for x in lines],
        "labels": [row(x) for x in label._registry],
        "boxes": [row(x) for x in box._registry],
        "linefills": [lf_row(x) for x in linefill._registry],
    }


def _tags():
    """Every live drawing's tag, in the snapshot's order."""
    return {
        "lines": [x.tag for x in line._registry],
        "labels": [x.tag for x in label._registry],
        "boxes": [x.tag for x in box._registry],
        "linefills": [x.tag for x in linefill._registry],
    }


def _run(path):
    sys.modules.pop(path.stem, None)
    r = ScriptRunner(script_path=path, ohlcv_iter=iter(synthetic_bars(2, 10)),
                     syminfo=default_syminfo())
    for _ in r.run_iter():
        pass
    return _field_snapshot(), _tags()


def __test_no_drawing_type_exposes_the_tag_as_a_field__():
    """One object of every kind, created with an explicit tag: the tag rides
    the object (the viz journal reads it) but ``fields()`` must not list it."""
    ln = line.new(0, 1.0, 2, 3.0, tag=7)
    lb = label.new(0, 1.0, "x", tag=7)
    bx = box.new(0, 1.0, 2, 3.0, tag=7)
    pl = polyline.new([chart.point.from_index(0, 1.0)], tag=7)
    lf = linefill.new(ln, line.new(0, 1.0, 2, 3.0), color.new(color.blue, 80), tag=7)
    tbl = table.new(position.top_right, 1, 1, tag=7)
    table.cell(tbl, 0, 0, "c", tag=7)
    cell = tbl.cells[(0, 0)]
    for name, obj in (("line", ln), ("label", lb), ("box", bx), ("polyline", pl),
                      ("linefill", lf), ("table", tbl), ("table cell", cell)):
        names = {f.name for f in fields(obj)}
        assert "tag" not in names, f"{name} exposes the call-site tag as a field: {names}"
        assert obj.tag == 7, f"{name} lost its tag"


def __test_two_script_versions_with_renumbered_tags_snapshot_identically__():
    """The twin shape: A and B create the same drawings at the same source
    lines; B carries one EXTRA creation site above them, so every later tag of
    the module shifts — the field-walked snapshots must still be identical,
    with the renumbering demonstrably real (the tags differ)."""
    snap_a, tags_a = _run(A)
    snap_b, tags_b = _run(B)
    assert tags_a != tags_b, (
        f"the two versions stamped the same tags — the renumbering the test "
        f"needs did not happen: {tags_a}")
    assert snap_a == snap_b, (
        "the field snapshot differs between two script versions whose shared "
        "call sites renumber")
    assert len(snap_a["lines"]) == len(snap_b["lines"]) == 2
