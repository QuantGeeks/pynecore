"""The journal drain's cost is proportional to what changed: a drain after a
bar (or a live tick) that touched no drawing re-serializes nothing, and a
drain after a change re-serializes exactly the changed drawing. The journal
wire itself is unchanged — the exactness/replay tests live in
``test_drawing_journal.py``. Synthetic bars."""
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from pynecore.core import viz
from pynecore.core.script_runner import ScriptRunner
from pynecore.qg_gates.common import default_syminfo, synthetic_bars

SCRIPT = Path(__file__).resolve().parent / "scripts" / "drawing_journal_cost.py"
LINEFILL = Path(__file__).resolve().parent / "scripts" / "drawing_journal_linefill.py"


@pytest.fixture
def line_serializer_calls() -> Iterator[list[int]]:
    """Count ``viz._line_dict`` calls (the vids it serialized)."""
    calls: list[int] = []
    real = viz._line_dict

    def spy(line):
        calls.append(line.vid)
        return real(line)

    viz._line_dict = spy
    try:
        yield calls
    finally:
        viz._line_dict = real


def _runner(script: Path, events: list) -> ScriptRunner:
    sys.modules.pop(script.stem, None)
    r = ScriptRunner(script_path=script, ohlcv_iter=iter(synthetic_bars(7, 5)),
                     syminfo=default_syminfo(), viz_journal=True)
    r.viz_events = events.extend
    return r


def __test_a_no_change_drain_reserializes_nothing__(line_serializer_calls):
    # bar 0 creates two lines (the close drain serializes both), bar 1 changes
    # one line's color (one serialization), and bars 2-4 change nothing: their
    # drains must not serialize a single line again
    events: list = []
    it = iter(_runner(SCRIPT, events).run_iter())
    next(it)  # bar 0
    next(it)  # bar 1
    assert len(line_serializer_calls) == 3  # two creates + one change
    n_after_change = len(events)  # bar 1's color change journals one update
    for _ in range(3):  # bars 2-4: quiet
        next(it)
    assert line_serializer_calls == line_serializer_calls[:3], (
        "bars 2-4 changed nothing, the drains must not re-serialize")
    assert len(events) == n_after_change, "and they must journal no events"


def __test_a_change_reserializes_exactly_the_changed_drawing__(line_serializer_calls):
    # bar 1 sets b's color: the drain re-serializes exactly b, and the event
    # is the same update the full diff would have produced
    events: list = []
    it = iter(_runner(SCRIPT, events).run_iter())
    next(it)  # bar 0: two creates
    creates = [e for e in events if e["op"] == "create"]
    changed_vid = creates[1]["id"]
    line_serializer_calls.clear()
    next(it)  # bar 1: one color change
    assert line_serializer_calls == [changed_vid], (
        "exactly the changed line, not both")
    updates = [e for e in events if e["op"] == "update"]
    assert len(updates) == 1 and updates[0]["id"] == changed_vid
    assert "color" in updates[0]["f"]


def __test_a_member_line_change_reserializes_the_linefill__():
    # a linefill serializes its member lines' state (line1_state/line2_state),
    # so a member's change must re-serialize the fill even though the fill
    # object's own fields did not move — skipping it would drift the journal
    # from the chart it stands for
    events: list = []
    it = iter(_runner(LINEFILL, events).run_iter())
    next(it)  # bar 0: two lines + a fill
    next(it)  # bar 1: a's color changes
    creates = [e for e in events if e["op"] == "create" and e["obj"] == "linefill"]
    assert len(creates) == 1
    fill_updates = [e for e in events if e["op"] == "update" and e["obj"] == "linefill"]
    assert len(fill_updates) == 1, "the fill's embedded line state changed"
    assert "line1_state" in fill_updates[0]["f"]
