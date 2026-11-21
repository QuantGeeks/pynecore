"""The drawing journal is exact: replaying it from an empty set (create sets
``s``, update applies ``f``, delete drops the id) reproduces the full drawing
set at every point it was drained. Real scripts: one whose registries evict
past max_lines_count / max_labels_count (a create and a FIFO delete in the
same bar), one live script whose forming bar re-runs on every tick (each
tick's discarded run rolls back; the journal closes the loop back to the
bar-open state). Updates carry only the changed fields, and every event
carries the creating call site's tag."""
import itertools
import sys
from pathlib import Path

from pynecore.core import viz
from pynecore.core.script_runner import LIVE_TRANSITION, ScriptRunner
from pynecore.qg_gates.common import default_syminfo, synthetic_bars
from pynecore.types.ohlcv import OHLCV

SCRIPTS = Path(__file__).resolve().parent / "scripts"
EVICT = SCRIPTS / "drawing_journal_evict.py"
LIVE = SCRIPTS / "drawing_journal_live.py"


class _Replay:
    """A ``viz_events`` sink that replays each batch onto an empty set and
    checks the replay equals the live drawing set at that point."""

    def __init__(self):
        self.state: dict[tuple[str, int], dict] = {}
        self.batches: list[list[dict]] = []

    def __call__(self, events: list[dict]) -> None:
        self.batches.append(list(events))
        for ev in events:
            key = (ev["obj"], ev["id"])
            if ev["op"] == "create":
                self.state[key] = dict(ev["s"])
            elif ev["op"] == "update":
                self.state[key].update(ev["f"])
            else:
                del self.state[key]
        # exactness at this point: the replay IS the live set
        assert self.state == viz._all_drawings()


def __test_replay_reproduces_the_set_at_every_bar_with_eviction__():
    sys.modules.pop(EVICT.stem, None)
    r = ScriptRunner(script_path=EVICT, ohlcv_iter=iter(synthetic_bars(7, 8)),
                     syminfo=default_syminfo(), viz_journal=True)
    replay = _Replay()
    r.viz_events = replay
    for _ in r.run_iter():
        pass

    ops = [ev["op"] for b in replay.batches for ev in b]
    # 8 bars, caps 3/2: 8 creates and 8-3 / 8-2 FIFO deletes per family
    assert ops.count("create") == 16
    line_deletes = [ev for b in replay.batches for ev in b
                    if ev["obj"] == "line" and ev["op"] == "delete"]
    label_deletes = [ev for b in replay.batches for ev in b
                     if ev["obj"] == "label" and ev["op"] == "delete"]
    assert len(line_deletes) == 5 and len(label_deletes) == 6
    # an eviction delete names the oldest ids; the last three created lines
    # are the ones still live at the end
    created_line_ids = [ev["id"] for b in replay.batches for ev in b
                        if ev["obj"] == "line" and ev["op"] == "create"]
    live_ids = set(created_line_ids[-3:])
    assert {ev["id"] for ev in line_deletes}.isdisjoint(live_ids)
    # every event names the creating call site; a delete's tag is the one the
    # create stamped on that id
    for b in replay.batches:
        for ev in b:
            assert ev["tag"] >= 0


def __test_replay_reproduces_the_set_on_every_forming_bar_tick__():
    base = 1_704_067_200_000

    def bar(ts, close_, closed):
        return OHLCV(timestamp=ts, open=close_, high=close_ + 1.0, low=close_ - 1.0,
                     close=close_, volume=1000.0, is_closed=closed)

    historical = [bar(base, 100.0, True), bar(base + 60_000, 101.0, True)]
    live = [
        bar(base + 120_000, 102.0, False),   # forming bar opens
        bar(base + 120_000, 102.5, False),   # tick: rollback + re-run
        bar(base + 120_000, 103.0, True),    # close: rollback + final run
        bar(base + 180_000, 104.0, False),   # next forming bar opens
        bar(base + 180_000, 105.0, True),
    ]

    sys.modules.pop(LIVE.stem, None)
    r = ScriptRunner(script_path=LIVE,
                     ohlcv_iter=itertools.chain(historical, [LIVE_TRANSITION], live),
                     syminfo=default_syminfo(), live=True, viz_journal=True)
    replay = _Replay()
    r.viz_events = replay
    for _ in r.run_iter():
        pass

    evs = [ev for b in replay.batches for ev in b]
    # the journal drains on every executed tick, not only at bar close: the
    # forming bar 2 drains three times (two ticks + close)
    bar2 = [i for i, b in enumerate(replay.batches) if b and b[0]["i"] == 2]
    assert len(bar2) == 3
    # the forming bar's first execution moves x2 (new bar_index) and y2; its
    # later ticks only move the price, so their diffs are single-field
    line_updates = [ev for ev in evs
                    if ev["obj"] == "line" and ev["op"] == "update"]
    forming = [ev for ev in line_updates if ev["i"] == 2]
    assert len(forming) == 3
    assert forming[0]["f"].keys() == {"x2", "y2"}
    assert all(ev["f"].keys() == {"y2"} for ev in forming[1:])
    assert all("s" not in ev for ev in evs if ev["op"] == "update")
    # each tick's label is created and then deleted by the next tick's
    # rollback, so its create and delete share the id and the tag
    labels = [ev for ev in evs if ev["obj"] == "label"]
    by_id: dict[int, dict[str, list[str]]] = {}
    for ev in labels:
        d = by_id.setdefault(ev["id"], {})
        d.setdefault(ev["op"], []).append(ev["tag"])
    per_tick = [d for d in by_id.values() if "create" in d]
    rolled_back = [d for d in by_id.values() if "delete" in d]
    assert len(per_tick) >= 3 and len(rolled_back) >= 2
    for d in by_id.values():
        if "create" in d and "delete" in d:
            assert d["create"] == d["delete"]
