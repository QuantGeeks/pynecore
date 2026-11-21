"""Every drawing carries the tag of the call site that created it: two call sites of the same
constructor get distinct tags, the same call site keeps its tag across bars, a copy is stamped
with the copy site's tag (not the source's), a cell created by a setter carries that setter's
tag, a later write to an existing cell keeps its creator's tag, and the tags are stable across
runs of the same script version. Synthetic bars."""
import json
import sys
from pathlib import Path

from pynecore.core import viz
from pynecore.core.script_runner import ScriptRunner
from pynecore.lib import box, label, line, linefill, polyline, table
from pynecore.qg_gates.common import default_syminfo, synthetic_bars

SCRIPT = Path(__file__).resolve().parent / "scripts" / "drawing_tags.py"

#: The script's creation call sites in source order: line.new, line.copy,
#: label.new, box.new, polyline.new, linefill.new, table.new, table.cell,
#: cell_set_text(B), then bar 1's line.new and cell_set_text(A2).
TAG_LINE_BASE, TAG_LINE_COPY, TAG_LABEL, TAG_BOX, TAG_POLYLINE, TAG_LINEFILL, TAG_TABLE, \
    TAG_CELL_A, TAG_CELL_B, TAG_LINE_BAR1, TAG_CELL_A2 = range(11)


def _run():
    sys.modules.pop(SCRIPT.stem, None)
    r = ScriptRunner(script_path=SCRIPT, ohlcv_iter=iter(synthetic_bars(3, 30)),
                     syminfo=default_syminfo())
    for _ in r.run_iter():
        pass


def __test_each_call_site_stamps_the_object_it_creates__():
    _run()
    base, bar1, dup = line.all()[0], line.all()[2], line.all()[1]
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


def __test_tags_are_stable_across_runs_of_the_same_script__():
    _run()
    first = (sorted(l.tag for l in line.all()), label.all()[0].tag, table.all()[0].tag,
             sorted(c.tag for c in table.all()[0].cells.values()))
    _run()
    second = (sorted(l.tag for l in line.all()), label.all()[0].tag, table.all()[0].tag,
              sorted(c.tag for c in table.all()[0].cells.values()))
    assert first == second
    # every tagged drawing has a distinct non-negative id per call site
    assert first[0] == [TAG_LINE_BASE, TAG_LINE_COPY, TAG_LINE_BAR1]


def __test_the_snapshot_serializes_the_tag_of_every_family__():
    _run()
    snap = json.loads(json.dumps(viz.drawings_snapshot()))
    assert snap["lines"][0]["tag"] == TAG_LINE_BASE
    assert snap["labels"][0]["tag"] == TAG_LABEL
    assert snap["boxes"][0]["tag"] == TAG_BOX
    assert snap["polylines"][0]["tag"] == TAG_POLYLINE
    assert snap["linefills"][0]["tag"] == TAG_LINEFILL
    tbl = snap["tables"][0]
    assert tbl["tag"] == TAG_TABLE
    by_text = {c["text"]: c["tag"] for c in tbl["cells"]}
    assert by_text == {"A2": TAG_CELL_A, "B": TAG_CELL_B}
