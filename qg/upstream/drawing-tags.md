# Design: engine call-site tags on every drawing object

**PyneCore version:** 6.10.10+qg.9 (tags), 6.10.10+qg.10 (method-form copy,
per-module tag ranges).

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

`qg/tests/test_drawing_tags.py`: a script with twelve creation sites (one per
family, a `.copy()` in both syntaxes, a `table.cell`, a `cell_set_*` that
creates its cell, a second site of the same constructor on a later bar) —
every object reports the tag of the site that created it, the copy its own
site's tag (not the source's) in both syntaxes, a cell keeps its creator's tag
on later writes, an `array.copy` through the same stamped dispatch keeps
working, the script module and an imported library module never share a
number, and two fresh runs produce identical tag sets (`first == second`). The
snapshot serializes the tag of every family. Byte-identity of computed output
is the drift gate's job (FORK.md): the tag is stamped by a lowering pass that
only appends a keyword argument, and the golden rows are bit-identical.

## The change

A `DrawingTags` lowering step (after `CallInline`, before `FunctionIsolation`,
so an inlined wrapper's copies are numbered like the sites they became and the
keyword rides along the anchored call sites) appends `tag=<n>` to every
drawing-creation call — `lib.{line,label,box,polyline,linefill,table}.{new}`,
the `.copy()` forms (the `line.copy(x)` call and the compiled-Pine
`method_call('copy', x)` dispatch alike: both are the copy site, so both carry
its tag; the dispatch drops the keyword for receivers that are not drawings,
because array/matrix/map share the method name), `table.cell` and the
`table.cell_set_*` setters (a setter that first creates the cell stamps it).
Tags are engine-only: no script input, no computed value change.

Each module numbers its sites from `tag_base(module_name)` — a stable hash of
the module's name — so the tags of a script and of the libraries it imports
never collide however each counts its own call sites (qg.10; in qg.9 every
module counted from 0 and a script's site 0 could share a number with its
library's site 0). A rename is a script-version change: the module's tags move
with it.

## The stability caveat

The numbers are assigned in pre-order over the tree AFTER `CallInline`, so
moving a creation call into or out of a wrapper that gets inlined — or adding
a creation call above another site — renumbers every later site of that
module. Tags are comparable only within one script version; a host keying a
restyle on them pins the version with the script.

## The open question

Whether TradingView exposes an equivalent internal id (it restyles per
viewer, so something like it exists there); nothing public to align with, so
the tag numbering is ours and stable only per script version.
