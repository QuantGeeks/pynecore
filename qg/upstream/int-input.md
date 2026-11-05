# `input.int` and drawing coordinates are Python ints (6.10.10-qg.8)

**PyneCore version:** 6.10.10 (measured on `6.10.10-qg.7`).

## The problem

`input.int(2)` came back as `2.0` (`pine_int` is `float`: a Pine int is a double at runtime), so a line width, an
x offset and every bar-index coordinate derived from one were doubles, and so were `line.new` / `label.new` /
`box.new` x values (`bar_coord` cast through `pine_int`): `Line(x1=10.0, ..., width=2.0)`. A consumer reading the
drawing objects saw `2.0` and `40959.0`; TradingView keeps them integers. (`core/viz.py` already wrote integral
doubles of int fields as ints; the objects themselves did not hold ints.)

## The change

`input.int` (default and settings value; the generic `input(int)` face too) returns `int(value)`, na for a
non-finite value; arithmetic derived from it is Python int arithmetic. `lib._drawing.bar_coord` returns `int`.
Other int-typed values (`bar_index`, `time`, `year()`...) stay doubles; not in scope.

## Tests

`qg/tests/test_int_input.py`: default and settings values print `2|8|10` (not `2.0|8.0|10.0`), line width and x
are `int`, label x is `int`, the snapshot spells them as integers.

Not filed (sev, 2026-10-31): nothing is pushed upstream.
