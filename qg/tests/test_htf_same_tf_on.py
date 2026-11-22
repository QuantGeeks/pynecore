"""A cross-symbol SAME-timeframe ``lookahead_on`` context runs its history as ONE closed
batch round, exactly like ``lookahead_off`` always could: on history both pair the same
bar — the other symbol's bar whose close is the chart bar's own close — so the blanket
ON exclusion of ``batch_eligible`` cost the batch transport (MEASURED on the house twin:
20.2 s -> 10.9 s) without a semantic difference to protect. The batch must arm for the ON
contexts, its rows must equal the per-bar run's, and a LIVE run's historical prefix —
which never arms a batch — must equal the batch run too: that is the transition proof,
the values live takes over from are the ones the batch produced. Synthetic data only."""
import json
import sys
import tempfile
from pathlib import Path

from pynecore.core import security as sec_mod
from pynecore.core.ohlcv import OHLCVWriter
from pynecore.core.script_runner import LIVE_TRANSITION, ScriptRunner
from pynecore.qg_gates.common import default_syminfo, live_events
from pynecore.types.ohlcv import OHLCV

SCRIPT = Path(__file__).resolve().parent / "scripts" / "htf_same_tf_on.py"
T0, STEP, N = 1_735_689_600_000, 300_000, 576  # 2025-01-01 UTC, two 24/7 days of 5m bars
HIST = 480


def _chart_bars():
    return [OHLCV(T0 + i * STEP, round(100.0 + (i % 23) * 0.25, 2),
                  round(100.6 + (i % 23) * 0.25, 2), round(99.4 + (i % 23) * 0.25, 2),
                  round(100.2 + (i % 23) * 0.25, 2), 1.0 + i % 7) for i in range(N)]


def _other_bars():
    """The other symbol's 5m bars: same grid, prices a visible distance away."""
    return [OHLCV(T0 + i * STEP, round(50.0 + (i % 19) * 0.1, 2),
                  round(50.4 + (i % 19) * 0.1, 2), round(49.6 + (i % 19) * 0.1, 2),
                  round(50.1 + (i % 19) * 0.1, 2), 2.0 + i % 5) for i in range(N)]


def _syminfo(prefix, ticker):
    si = default_syminfo()
    si.prefix, si.ticker = prefix, ticker
    return si


def _run(events, batch, planned, live=False):
    """One run; ``planned`` collects (sec_id, planned?) per batch consultation."""
    sys.modules.pop(SCRIPT.stem, None)
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as td:
        feed = Path(td) / "OTHER.ohlcv"
        with OHLCVWriter(feed, "5") as w:
            for b in _other_bars():
                w.write(b)
        _syminfo("AMEX", "OTHER").save_toml(feed.with_suffix(".toml"))
        extra = {}
        if batch:
            extra = dict(last_bar_index=N - 1, last_bar_time=T0 + (N - 1) * STEP)
        r = ScriptRunner(script_path=SCRIPT, ohlcv_iter=iter(events),
                         syminfo=_syminfo("PYTEST", "TEST"),
                         security_data={"AMEX:OTHER:5": str(feed)}, live=live,
                         **extra)
        return [json.dumps(dict(pv), default=str, sort_keys=True)
                for _, pv in r.run_iter()]


def __test_a_same_timeframe_on_context_runs_its_history_as_one_batch_round__():
    planned = []
    orig = sec_mod.plan_historical_batch

    def _planning(state, last_chart_time):
        ok = orig(state, last_chart_time)
        planned.append((state.sec_id, ok))
        return ok

    sec_mod.plan_historical_batch = _planning
    try:
        per_bar = _run(_chart_bars(), batch=False, planned=None)
        batch_rows = _run(_chart_bars(), batch=True, planned=planned)
    finally:
        sec_mod.plan_historical_batch = orig
    assert len(planned) == 4, f"expected one consultation per context: {planned}"
    assert all(ok for _sid, ok in planned), (
        f"a same-timeframe context was refused its batch: {planned}")
    assert batch_rows == per_bar, (
        f"batch rows differ from the per-bar run at bars "
        f"{[i for i, (a, b) in enumerate(zip(batch_rows, per_bar)) if a != b][:8]}")


def __test_a_live_run_takes_over_from_the_values_the_batch_produced__():
    events = live_events(_chart_bars(), hist=HIST, live=N - HIST)
    batch_rows = _run(_chart_bars(), batch=True, planned=None)
    planned = []
    orig = sec_mod.plan_historical_batch

    def _planning(state, last_chart_time):
        planned.append(state.sec_id)
        return orig(state, last_chart_time)

    sec_mod.plan_historical_batch = _planning
    try:
        live_rows = _run(events, batch=False, planned=None, live=True)
    finally:
        sec_mod.plan_historical_batch = orig
    assert not planned, f"a live run armed a batch: {planned}"
    hist_rows = [r for r in live_rows][:HIST]
    assert hist_rows == batch_rows[:HIST], (
        "the live run's historical prefix differs from the batch run at bars "
        f"{[i for i, (a, b) in enumerate(zip(hist_rows, batch_rows)) if a != b][:8]}")
