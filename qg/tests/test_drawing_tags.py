"""Every drawing carries the tag of the call site that created it: two call sites of the same
constructor get distinct tags, the same call site keeps its tag across bars, a copy is stamped
with the copy site's tag (not the source's, the method form ``x.copy()`` included), a cell
created by a setter carries that setter's tag, a later write to an existing cell keeps its
creator's tag, the tags are unique across modules (a script and the library it imports never
share a number), and the tags are stable across runs of the same script version. Synthetic
bars."""
import json
import sys
from pathlib import Path

from pynecore.core import viz
from pynecore.core.script_runner import ScriptRunner
from pynecore.lib import box, label, line, linefill, polyline, table
from pynecore.qg_gates.common import default_syminfo, synthetic_bars
from pynecore.transformers.drawing_tags import tag_base

SCRIPTS = Path(__file__).resolve().parent / "scripts"
SCRIPT = SCRIPTS / "drawing_tags.py"

#: The script's module base plus the creation call sites in source order:
#: line.new, line.copy, label.new, box.new, polyline.new, linefill.new,
#: table.new, table.cell, cell_set_text(B), then bar 1's line.new,
#: cell_set_text(A2) and the method-form copy.
BASE = tag_base("drawing_tags")
TAG_LINE_BASE, TAG_LINE_COPY, TAG_LABEL, TAG_BOX, TAG_POLYLINE, TAG_LINEFILL, TAG_TABLE, \
    TAG_CELL_A, TAG_CELL_B, TAG_LINE_BAR1, TAG_CELL_A2, TAG_LINE_MCOPY = range(BASE, BASE + 12)


def _run():
    sys.modules.pop(SCRIPT.stem, None)
    r = ScriptRunner(script_path=SCRIPT, ohlcv_iter=iter(synthetic_bars(3, 30)),
                     syminfo=default_syminfo())
    for _ in r.run_iter():
        pass


def __test_each_call_site_stamps_the_object_it_creates__():
    _run()
    base, dup, bar1 = line.all()[0], line.all()[1], line.all()[2]
    assert base.tag == TAG_LINE_BASE and dup.tag == TAG_LINE_COPY
    # the copy is stamped with ITS call site's tag, never the source's
    assert dup.tag != base.tag
    assert label.all()[0].tag == TAG_LABEL
    assert box.all()[0].tag == TAG_BOX
    assert polyline.all()[0].tag == TAG_POLYLINE
    assert linefill.all()[0].tag == TAG_LINEFILL
    tbl = table.all()[0]
    assert tbl.tag == TAG_TABLE
    cell_a = tbl.cells[(0, 0)]
    cell_b = tbl.cells[(1, 1)]
    # table.cell created cell A; cell B's first touch is the setter call site
    assert cell_a.tag == TAG_CELL_A and cell_b.tag == TAG_CELL_B
    # bar 1's line.new is a second call site of the same constructor
    assert bar1.tag == TAG_LINE_BAR1
    # A2 was written through another cell_set_text site; the cell kept its creator's tag
    assert cell_a.tag == TAG_CELL_A and cell_a.text == "A2"


def __test_the_method_form_of_copy_gets_its_own_site_tag__():
    _run()
    base, dup, bar1, mth = line.all()
    # ``second.copy()`` is stamped like ``line.copy(second)``: its own call
    # site's tag, never -1 and never the source's
    assert mth.tag == TAG_LINE_MCOPY
    assert mth.tag not in (base.tag, dup.tag, bar1.tag)


def __test_a_non_drawing_copy_never_sees_the_stamp__():
    # ``a.copy()`` on an array rides the same stamped method_call dispatch;
    # array.copy cannot take the tag and the copy itself must keep working
    sys.modules.pop("drawing_tags_arrcopy", None)
    r = ScriptRunner(script_path=SCRIPTS / "drawing_tags_arrcopy.py",
                     ohlcv_iter=iter(synthetic_bars(3, 5)), syminfo=default_syminfo())
    out = [dict(p) for _c, p in r.run_iter()]
    assert out[0]["n"] == 2.0 and out[0]["first"] == 1.5


def __test_tags_are_stable_across_runs_of_the_same_script__():
    _run()
    first = (sorted(l.tag for l in line.all()), label.all()[0].tag, table.all()[0].tag,
             sorted(c.tag for c in table.all()[0].cells.values()))
    _run()
    second = (sorted(l.tag for l in line.all()), label.all()[0].tag, table.all()[0].tag,
              sorted(c.tag for c in table.all()[0].cells.values()))
    assert first == second
    # every tagged drawing has a distinct id per call site
    assert first[0] == sorted((TAG_LINE_BASE, TAG_LINE_COPY, TAG_LINE_BAR1, TAG_LINE_MCOPY))


def __test_tags_are_unique_across_modules__():
    # the script and the library it imports each count their sites from their
    # own module's base: a host keying a restyle on a tag never sees the two
    # modules share a number
    from pynecore.core import script as script_core
    for stem in ("drawing_tags_modules", "drawing_tags_lib"):
        sys.modules.pop(stem, None)
    # A pyne library the runner imports registers process-globally; leaving it
    # registered makes every LATER runner in this process execute the stale
    # lib's main too (a test_097 export-count probe caught exactly that)
    saved_libraries = list(script_core._registered_libraries)
    try:
        r = ScriptRunner(script_path=SCRIPTS / "drawing_tags_modules.py",
                         ohlcv_iter=iter(synthetic_bars(3, 5)), syminfo=default_syminfo())
        for _ in r.run_iter():
            pass
    finally:
        for stem in ("drawing_tags_modules", "drawing_tags_lib"):
            sys.modules.pop(stem, None)
        script_core._registered_libraries[:] = saved_libraries
    from_lib, own = line.all()[-2:]
    assert from_lib.tag == tag_base("drawing_tags_lib")
    assert own.tag == tag_base("drawing_tags_modules")
    assert from_lib.tag != own.tag


def __test_the_snapshot_excludes_the_tag_of_every_family__():
    """The snapshot is the VALUE form compared across spellings of one script;
    the tag is host metadata (which file's call site made the object) and two
    spellings tag the same drawing differently — a private-CI identity run
    (old port vs speedup, same counts) failed on exactly that."""
    _run()
    snap = json.loads(json.dumps(viz.drawings_snapshot()))
    for family in ("lines", "labels", "boxes", "polylines", "linefills", "tables"):
        for obj in snap[family]:
            assert "tag" not in obj, (family, obj)
    for cell in snap["tables"][0]["cells"]:
        assert "tag" not in cell, cell
    # ... while the objects themselves still carry their tag for the journal
    assert line.all()[0].tag == TAG_LINE_BASE
