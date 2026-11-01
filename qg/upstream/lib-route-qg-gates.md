# The lib-route registry scan versus the fork's qg_gates package (6.10.10)

**PyneCore version:** 6.10.10.

## The collision

`tests/t00_pynecore/ast/test_130_lib_route_registry.py` asserts that no `@pyne`
module exists outside `pynecore/lib`: the route registry covers `pynecore.lib`
only, and a transformed module anywhere else would need routes of its own. Our
fork ships `pynecore.qg_gates`, the §13.1 bit-identity gates, whose Layer A
scripts (`qg_gates/scripts/gate_ta.py`, `gate_draw.py`) are `@pyne` indicator
modules by design — they are the scripts the gates run, and they live inside the
package so an install of the fork at a tag carries them (the gates must run from
the installed package with the working directory outside the repository).

## Why the exclusion is safe (synthetic reasoning, no private data)

Nothing under `qg_gates` is ever imported through the module the registry serves:

- the gate scripts are executed by **file path** (`ScriptRunner(script_path=…)`)
  exactly like a member's script, never imported as `pynecore.qg_gates.scripts.*`
  by engine code;
- `qg_gates` itself contains no `lib` callees beyond what every script has; its
  other modules (`common`, `fingerprint`, the gates, `pristine`) are plain
  modules with no `@pyne` marker.

So the invariant's safety argument — only `@pyne` modules yield state-carrying
routes, and they all live under `lib` — is untouched: the fork's two `@pyne`
scripts are consumers of the transform, not providers of registry routes.

## The carried change

The fork's copy of the test excludes the `qg_gates` subtree from the scan (one
predicate), with a comment saying why. If upstream ever grows its own
out-of-lib `@pyne` story, this row drops at the rebase.
