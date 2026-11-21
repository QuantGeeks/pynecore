# Design: engine call-site tags on every drawing object

**PyneCore version:** 6.10.10.

## The problem

A host that renders a script's drawings for several viewers wants to restyle
them per viewer (color, width, font) without putting color or style inputs in
the computation key — different styles would then be different computations.
What identifies "the trend line drawn by this call site" is the **call site
itself**, and nothing on the drawing object carries it: the vid is per object
instance (fresh on every run and on every `copy`), and the object's fields are
the script's own style choices.

## Minimal reproduction (synthetic data only)

Two call sites of the same constructor produce no distinguishable origin:

```python
@script.indicator("tags", "tg", overlay=True)
def main():
    if bar_index == 0:
        a: Persistent[Line] = line.new(0, 100.0, 5, 110.0)
        b: Persistent[Line] = line.new(0, 100.0, 5, 110.0)  # a second site
```

Both lines serialize identically in `viz.drawings_snapshot()` apart from their
vids, and the vids are reassigned on the next run — a host cannot key a
per-viewer style on anything stable.

## Observed vs expected

- Observed: no stable per-call-site key on any drawing family, table cells
  included; two runs of the same script produce unrelated vids.
- Expected: every drawing (line, label, box, polyline, linefill, table, table
  cell) carries a stable `tag` naming the creating call site — the same
  integer for the same script version on every run, distinct per site, without
  changing any computed value.

## Our evidence (fork tests, synthetic data only)

`qg/tests/test_drawing_tags.py`: a script with eleven creation sites (one per
family, a `.copy()`, a `table.cell`, a `cell_set_*` that creates its cell, a
second site of the same constructor on a later bar) — every object reports the
tag of the site that created it, the copy its own site's tag (not the
source's), a cell keeps its creator's tag on later writes, and two fresh runs
produce identical tag sets (`first == second`). The snapshot serializes the
tag of every family. Byte-identity of computed output is the drift gate's job
(FORK.md): the tag is stamped by a lowering pass that only appends a keyword
argument, and the golden rows are bit-identical.

## The change

A `DrawingTags` lowering step (after `CallInline`, before `FunctionIsolation`,
so an inlined wrapper's copies are numbered like the sites they became and the
keyword rides along the anchored call sites) appends `tag=<n>` to every
drawing-creation call — `lib.{line,label,box,polyline,linefill,table}.{new}`,
the `.copy()` forms, `table.cell` and the `table.cell_set_*` setters (a setter
that first creates the cell stamps it; `method_call('copy', …)` is excluded
because array/matrix/map share that method name). The counter is per module,
pre-order source order. Tags are engine-only: no script input, no computed
value change.

## The open question

Whether TradingView exposes an equivalent internal id (it restyles per
viewer, so something like it exists there); nothing public to align with, so
the tag numbering is ours and stable only per script version.
