# Design: an exact drawing change journal

**PyneCore version:** 6.10.10.

## The problem

The viz journal (`viz_journal=True`) emitted, for an update, the **full**
serialized state of the drawing and, for a delete, nothing but the id — and it
only drained at bar close, so a live forming bar's re-runs (each tick's
discarded run rolled back, the bar re-executed) were invisible: a host
draining the journal could not know the drawing set at any tick, only at bar
closes. A host that renders drawings per update needs the journal to be
**exact**: applying it from an empty set reproduces the full drawing set at
every point.

## Minimal reproduction (synthetic data only)

A live runner whose forming bar re-points a line and re-creates a label each
tick (`qg/tests/scripts/drawing_journal_live.py`):

```python
@script.indicator("Journal live ticks", "jlv", overlay=True)
def main():
    if bar_index == 0:
        ln: Persistent[Line] = line.new(0, 0.0, 0, close)
    line.set_xy2(ln, bar_index, close)
    label.new(bar_index, close, "tick")   # a fresh label per run
```

Feed two closed bars, then a forming bar with two intra-bar updates and its
close. Before the change the journal carries no event between the bar-open
run and the close — the tick states (a line that moved twice, a label
replaced twice by rollback + re-run) never appear; an update event, had there
been one, would have carried the whole serialized object with no way to see
which fields moved.

## Observed vs expected

- Observed: one drain per closed bar; updates carry the full `s` state;
  no `tag`; a delete carries nothing but the id.
- Expected: the journal drains after **every executed intra-bar tick** too
  (the rollback then appears as the diff from the last emission — deletes and
  field reversions closing the loop back to the bar-open state), an update
  carries `f` — only the changed fields and their new values — and every
  event carries the drawing's call-site tag. Replaying from an empty set
  (create applies `s`, update applies `f`, delete drops the id) reproduces
  the full drawing set at every drained point.

## Our evidence (fork tests, synthetic data only)

`qg/tests/test_drawing_journal.py` replays every drained batch onto an empty
set and asserts the replay equals the live `viz._all_drawings()` at that
point, over two real scripts:

- `drawing_journal_evict.py` (8 bars, `max_lines_count=3`,
  `max_labels_count=2`): 16 creates and 5 + 6 FIFO evictions; every
  replay == live set at every bar.
- `drawing_journal_live.py` (forming bar with two ticks + close): the forming
  bar drains 3 batches; its first line update is `{x2, y2}` (new bar) and the
  tick-to-tick ones are single-field `{y2}`; each tick's label create/delete
  share the id and the tag.

Upstream's wire-format pins (`tests/t01_lib/t11_viz/test_007_journal.py`:
one create / three updates / one delete, create carries `s.id`, delete no
`s`, per-bar batches) pass unchanged.

## The change

`viz.journal_diff` computes per-field diffs (`f`) and stamps `tag` on every
event (a delete reads it from the shadow). `ScriptRunner._drain_viz_journal`
is the single drain point, called at bar close (from `_write_viz_bar`) and
after every executed intra-bar tick run in the live loop.

## The open question

None — the semantics are additive to the journal stream (a reader that
ignored `f`/`tag` still reconstructs a correct bar-close view from `s`
fields, since the update fields fully determine the state).
