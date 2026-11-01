# `lib.syminfo` mirrors every `SymInfo` slot at import (6.10.10-qg.1)

**PyneCore version:** 6.10.10 (measured on the fork's `6.10.10-qg.1` release;
upstream's layout is the same).

## The defect (measured, synthetic reasoning; no fixture data here)

`pynecore.lib.syminfo` declares `opening_hours`, `session_starts`,
`session_ends`, `extended_hours`, `avg_spread`, `taker_fee`, `maker_fee` and
`_size_round_factor` as annotations WITHOUT values, and does not declare
`session_schedules`, `session_corrections`,
`extended_session_corrections`, `regular_hours`,
`regular_session_corrections` at all — 12 of the 50 `SymInfo.__slots__` are
absent from the module at import (measured 2026-11-01). The module attributes
only come into existence when `script_runner._set_lib_syminfo_properties`
`setattr`s them as the first runner starts.

The consequence for any host that keeps several runners in one process by
swapping module state: the swap's tracked-set scan reads `lib.syminfo` at
import, so those twelve attributes are never saved or restored — the last
runner's session lists stay installed, and a co-resident runner reads another
runner's `opening_hours` (session membership, `session.isfirstbar`) and
`_size_round_factor` (the `mincontract` rounding). The fork's own gate suite
missed it because every Layer A job ran the 24/7 default SymInfo, whose values
equal the baseline; the real catalogue's first gate-2 run (2026-11-01) failed
with 43 changed paths, all `pynecore.lib.syminfo:opening_hours`,
`:session_starts`, `:session_ends`.

## The fix

Every name in `SymInfo.__slots__` exists on `lib.syminfo` at import with its
field's default (`[]` lists, `{}` dicts, `None` for the provider-optionals,
`_size_round_factor = 1.0`); the runner still injects the per-run values on
top. The tracked count moves from 427 to 440 (the 12 slots plus
`_size_round_factor`), and Layer A gains a job under a Mon–Fri 09:30–16:00
`America/New_York` session so the gates exercise a non-default SymInfo from
now on.

Not filed (sev, 2026-10-31): nothing is pushed upstream.
