"""The tracked-name count is the same in every environment (ruling 2026-11-01)."""
from pynecore.core import runner_state as rs

FIVE = ("rich", "_log_console", "_log_console_width", "_stdout_is_tty", "handler")


def __test_tracked_names_count_is_environment_independent__(monkeypatch):
    """ 443 everywhere — no rich-dependent names, no native-twin import bindings """
    names = rs.tracked_names()
    assert len(names) == 443
    assert not [n for n in names if n.startswith("pynecore.lib.log:") and
                n.split(":", 1)[1] in FIVE]
    # The compiled rolling-sum twin imports only where it is built; its import
    # binding must not move the count between build environments
    assert "pynecore.core._native_rolling_sum:_na_float" not in names
    # Negative control: rescan with the exclusions emptied. WHICH excluded
    # names the live scan can see depends on the invocation -- the twin only
    # once something imported it, lib.log's console names only after a first
    # log call, and its ``rich`` only where PYNE_NO_COLOR_LOG left it None
    # (the upstream tests/conftest sets it) -- and lazy caches cut the other
    # way (plot/request ``_lib`` start as tracked ``None``s and drop out of
    # the rescan once a suite run resolves them, which once made a rescan
    # count of 443 look like a pin violation when it was only ordering). So
    # the invariant is the exact set difference, never a count: the rescan's
    # gains over the frozen set are precisely the excluded names visible to
    # it, and nothing else appears that the freeze missed.
    excluded = {f"{m}:{k}" for m, k in rs._NAME_EXCLUSIONS}
    monkeypatch.setattr(rs, "_NAME_EXCLUSIONS", set())
    without = {f"{m.__name__}:{k}" for m, k in rs._tracked()}
    assert without - set(names) == excluded & without


def __test_every_syminfo_slot_exists_at_import__():
    """ the swap scans pynecore.lib.syminfo at import: a slot the runner creates later is never swapped """
    from pynecore.core.syminfo import SymInfo
    from pynecore.lib import syminfo as lib_syminfo
    assert set(SymInfo.__slots__) <= set(vars(lib_syminfo))
    assert "_size_round_factor" in vars(lib_syminfo)
    tracked = set(rs.tracked_names())
    assert {f"pynecore.lib.syminfo:{n}" for n in SymInfo.__slots__} <= tracked
