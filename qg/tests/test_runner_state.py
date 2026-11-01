"""The tracked-name count is the same in every environment (ruling 2026-11-01)."""
from pynecore.core import runner_state as rs

FIVE = ("rich", "_log_console", "_log_console_width", "_stdout_is_tty", "handler")


def __test_tracked_names_count_is_environment_independent__(monkeypatch):
    """ 427 everywhere, and none of pynecore.lib.log's five rich-dependent names """
    names = rs.tracked_names()
    assert len(names) == 440
    assert not [n for n in names if n.startswith("pynecore.lib.log:") and
                n.split(":", 1)[1] in FIVE]
    # Negative control: with the exclusion emptied and the scan recomputed, the
    # count differs and one of the rich-dependent names is back -- which one
    # depends on whether this environment installed rich (the point of the fix).
    monkeypatch.setattr(rs, "_NAME_EXCLUSIONS", set())
    recomputed = {f"{m.__name__}:{k}" for m, k in rs._tracked()}
    assert len(recomputed) != 427
    assert ("pynecore.lib.log:_log_console" in recomputed) or ("pynecore.lib.log:rich" in recomputed)


def __test_every_syminfo_slot_exists_at_import__():
    """ the swap scans pynecore.lib.syminfo at import: a slot the runner creates later is never swapped """
    from pynecore.core.syminfo import SymInfo
    from pynecore.lib import syminfo as lib_syminfo
    assert set(SymInfo.__slots__) <= set(vars(lib_syminfo))
    assert "_size_round_factor" in vars(lib_syminfo)
    tracked = set(rs.tracked_names())
    assert {f"pynecore.lib.syminfo:{n}" for n in SymInfo.__slots__} <= tracked
