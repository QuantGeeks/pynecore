# `ta.pivot_point_levels`: the outer levels (6.10.10-qg.8)

**PyneCore version:** 6.10.10 (measured on the fork's `6.10.10-qg.7`).

## The problem (synthetic)

`ta.pivot_point_levels(type, anchor)` returns an 11-element array `[P, R1, S1, R2, S2, R3, S3, R4, S4, R5, S5]`.
Upstream filled P..R3/S3 for Traditional, Classic and Woodie and left the rest na, and left Camarilla's R5/S5 na.
Period high 15, low 8, close 13 (range 7, P = 12), Traditional: R4 was na, expected 27.

## The change

Every level each type defines, with TradingView's documented formulas (H, L, C the previous period's;
Woodie's open the current period's):

| Type | Levels added / changed |
|---|---|
| Traditional | R4 = 3P + (H - 3L), S4 = 3P - (3H - L), R5 = 4P + (H - 4L), S5 = 4P - (4H - L) |
| Classic | its own formulas: R_n/S_n = P ± n(H - L) for n = 2, 3 (R3/S3 were Traditional's), plus R4/S4 = P ± 3(H - L) |
| Woodie | R4 = R3 + (H - L), S4 = S3 - (H - L) |
| Camarilla | R5 = H / L * C, S5 = C - (R5 - C) (na when L is 0) |

Levels a type does not define stay na: Fibonacci 4/5, Classic and Woodie 5, DM 3..5 (TradingView's "Pivot points
standard" script shows level 4 for every type but DM and Fibonacci, level 5 for Traditional and Camarilla only).

**Behavior change:** Classic R3/S3 were Traditional's values (`2P + (H - 2L)`) and are now `P ± 2(H - L)`.

## Tests

`qg/tests/test_pivot_levels.py`: hand-computed values for all six types over two periods, `developing=True`,
and na for the undefined levels. Existing `test_235_pivot_point_levels` (TradingView-measured Traditional,
Fibonacci, DM, Camarilla R4, Woodie P) is unchanged and green.

## Not settled

The formulas are TradingView's published ones; the reference tool exposes the function's contract and the
built-in script's level visibility, not the arithmetic, so R4/S4/R5/S5 and Classic R3/S3 are unmeasured against a
TradingView export. Not filed (sev, 2026-10-31): nothing is pushed upstream.
