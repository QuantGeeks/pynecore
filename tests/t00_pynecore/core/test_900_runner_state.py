"""Per-runner state (QuantGeeks fork; spec 4.2): co-resident runners equal pristine per-process runs."""
import os, pickle, random, subprocess, sys
from pathlib import Path
import pytest
from pynecore.core import runner_state as rs
from pynecore.core import drawing_snapshot
from pynecore.core.script_runner import LIVE_TRANSITION
from pynecore.types.ohlcv import OHLCV
from pynecore.lib import label, line, box

D = Path(__file__).parent / "data" / "runner_state"
TA, DRAW, RAISE, PRISTINE = D / "rs_ta.py", D / "rs_draw.py", D / "rs_raise.py", D / "pristine_run.py"
ENV = dict(os.environ, PYNE_SAVE_SCRIPT_TOML="0")


def _bars(seed, n=600):
    rnd, out, px = random.Random(seed), [], 500.0
    for i in range(n):
        o = round(px, 2); c = round(o + rnd.uniform(-0.6, 0.6), 2)
        out.append(OHLCV(1779802200000 + 60000 * i, o, round(max(o, c) + rnd.uniform(0, 0.3), 2),
                         round(min(o, c) - rnd.uniform(0, 0.3), 2), c, float(rnd.randint(50000, 500000))))
        px = c
    return out


def _live(seed, hist=300, live=60, ticks=3):
    bars = _bars(seed, hist + live); ev = bars[:hist] + [LIVE_TRANSITION]
    for b in bars[hist:]:
        for k in range(1, ticks + 1):
            px = round(b.open + (b.close - b.open) * k / (ticks + 1), 2)
            ev.append(OHLCV(b.timestamp, b.open, max(b.open, px), min(b.open, px), px, b.volume * k / (ticks + 1), is_closed=False))
        ev.append(b)
    return ev


def _row(c, p):
    return (c.timestamp, tuple(sorted((k, repr(v)) for k, v in p.items())), (len(label.all()), len(line.all()), len(box.all())))


def _pristine(tmp_path, script, events, syminfo, live, mode="compensated"):
    ev, out = tmp_path / f"e{id(events)}.pkl", tmp_path / f"o{id(events)}{mode}{script.stem}.pkl"
    ev.write_bytes(pickle.dumps((events, syminfo)))
    p = subprocess.run([sys.executable, "-I", str(PRISTINE), str(script), str(ev), str(out), "1" if live else "0", mode],
                       capture_output=True, text=True, env=ENV)
    assert p.returncode == 0, p.stderr[-2000:]
    return pickle.loads(out.read_bytes())


def _interleave(jobs, syminfo, live, swap=True, modes=None):
    st, gens, rows = [], [], []
    for i, (script, events) in enumerate(jobs):
        s = rs.new_runner_state(sum_mode=modes[i] if modes else "compensated")
        r = rs.create_runner(s, script_path=script, ohlcv_iter=events, syminfo=syminfo, live=live,
                             lossless_prices=True, lossless_volume=True)
        st.append(s); gens.append(r.run_iter()); rows.append([])
    active = list(range(len(jobs)))
    while active:
        nxt = []
        for i in active:
            if swap:
                rs.activate(st[i])
            try:
                c, p = next(gens[i])
            except StopIteration:
                rs.discard(st[i]); continue
            except ValueError:
                rs.discard(st[i]); rows[i].append("raised"); continue
            rows[i].append(_row(c, p)); nxt.append(i)
        active = nxt
    return rows


JOBS = [(TA, 1), (TA, 2), (TA, 3), (DRAW, 1), (DRAW, 2), (DRAW, 3)]


def __test_interleaved_runners_match_pristine__(tmp_path, syminfo):
    """ Six runners round-robin in one process equal their pristine runs, plots and drawings """
    jobs = [(s, _bars(k)) for s, k in JOBS]
    for (s, ev), rows in zip(jobs, _interleave(jobs, syminfo, False)):
        assert rows == _pristine(tmp_path, s, ev, syminfo, False), s.name


def __test_live_runners_match_pristine__(tmp_path, syminfo):
    """ Live mode with intrabar ticks: plots and drawing counts per update equal pristine """
    jobs = [(s, _live(k)) for s, k in JOBS]
    for (s, ev), rows in zip(jobs, _interleave(jobs, syminfo, True)):
        assert rows == _pristine(tmp_path, s, ev, syminfo, True), s.name
    rs.activate(rs.new_runner_state())
    assert drawing_snapshot._REGISTRIES[1] is sys.modules["pynecore.lib.label"]._registry


def __test_no_swap_control_corrupts__(tmp_path, syminfo):
    """ Negative control: the same interleave without activate() corrupts at least one runner """
    jobs = [(s, _bars(k)) for s, k in JOBS]
    got = _interleave(jobs, syminfo, False, swap=False)
    assert [s for (s, ev), r in zip(jobs, got) if r != _pristine(tmp_path, s, ev, syminfo, False)]


def __test_registry_rebind_control__(tmp_path, syminfo, monkeypatch):
    """ Negative control: without the _REGISTRIES rebind, live drawings differ from pristine """
    monkeypatch.setattr(rs, "_rebind_registries", lambda: None)
    jobs = [(DRAW, _live(k)) for k in (1, 2, 3)]
    got = _interleave(jobs, syminfo, True)
    assert [k for k, ((s, ev), r) in enumerate(zip(jobs, got)) if r != _pristine(tmp_path, s, ev, syminfo, True)]


def __test_failures_leave_neighbours_exact__(tmp_path, syminfo):
    """ A runner that raises mid-run, and one whose creation raises, are discarded; neighbours stay exact """
    s_bad = rs.new_runner_state()
    with pytest.raises(Exception):
        rs.create_runner(s_bad, script_path=D / "no_such_script.py", ohlcv_iter=_bars(9), syminfo=syminfo)
    assert rs.active_state() is None
    jobs = [(TA, _bars(1)), (RAISE, _bars(2)), (TA, _bars(3))]
    got = _interleave(jobs, syminfo, False)
    assert got[1][-1] == "raised" and len(got[1]) == 251
    assert got[0] == _pristine(tmp_path, TA, jobs[0][1], syminfo, False)
    assert got[2] == _pristine(tmp_path, TA, jobs[2][1], syminfo, False)


def __test_discard_closes_under_own_state__(tmp_path, syminfo):
    """ Evicting a suspended runner closes it under its own state; a bare close corrupts the neighbour """
    for proper in (True, False):
        a, b = rs.new_runner_state(), rs.new_runner_state()
        kw = dict(syminfo=syminfo, lossless_prices=True, lossless_volume=True)
        ga = rs.create_runner(a, script_path=TA, ohlcv_iter=_bars(1), **kw).run_iter()
        eb = _bars(2)
        gb = rs.create_runner(b, script_path=TA, ohlcv_iter=eb, **kw).run_iter()
        rows = []
        for _ in range(200):
            rs.activate(a); next(ga); rs.activate(b); rows.append(_row(*next(gb)))
        if proper:
            rs.discard(a, ga)
        else:
            ga.close()
        rs.activate(b)
        rows += [_row(c, p) for c, p in gb]
        same = rows == _pristine(tmp_path, TA, eb, syminfo, False)
        assert same is proper
        rs.discard(b)


def __test_sum_mode_is_per_runner__(tmp_path, syminfo):
    """ Two co-resident runners, one per mode, each equal their own pristine run """
    jobs = [(TA, _bars(4)), (TA, _bars(4))]
    got = _interleave(jobs, syminfo, False, modes=["compensated", "window"])
    assert got[0] == _pristine(tmp_path, TA, jobs[0][1], syminfo, False, "compensated")
    assert got[1] == _pristine(tmp_path, TA, jobs[1][1], syminfo, False, "window")
    assert got[0] != got[1]


def __test_inventory_sha_and_import_guard__(tmp_path, syminfo):
    """ The tracked set holds the mode and excludes itself; importing mid-run is refused """
    n = rs.tracked_names()
    assert "pynecore.core.rolling_sum:_sum_mode" in n and "pynecore.core.instance_state:_root_vectors" in n
    assert not [x for x in n if x.startswith("pynecore.core.runner_state:")] and n == tuple(sorted(n))
    assert len(rs.swap_sha()) == 64
    ev = tmp_path / "g.pkl"; ev.write_bytes(pickle.dumps((_bars(1), syminfo)))
    code = ("import pickle,sys\nfrom pathlib import Path\nfrom pynecore.core.script_runner import ScriptRunner\n"
            "e,s=pickle.loads(Path(sys.argv[1]).read_bytes())\n"
            "g=ScriptRunner(script_path=Path(sys.argv[2]),ohlcv_iter=e,syminfo=s).run_iter();next(g)\n"
            "import pynecore.core.runner_state\n")
    p = subprocess.run([sys.executable, "-I", "-c", code, str(ev), str(TA)], capture_output=True, text=True, env=ENV)
    assert p.returncode == 1
    assert "RuntimeError: pynecore.core.runner_state imported while a runner is live; import it before creating runners" in p.stderr


def __test_discarding_the_current_state_restores_the_baseline__(tmp_path, syminfo):
    """ Discarding the current state restores the baseline the module snapshotted
    before its first install, so a later plain runner behaves as on v6.10.10
    (ruling 2026-10-31) """
    from pynecore.core import rolling_sum
    from pynecore.core.script_runner import ScriptRunner
    s = rs.new_runner_state(sum_mode="window")
    rs.activate(s)
    assert rolling_sum.get_sum_mode() == "window"
    rs.discard(s)
    assert rs.active_state() is None
    assert rolling_sum.get_sum_mode() == "compensated"
    events = _bars(7)
    rows = [_row(c, p) for c, p in ScriptRunner(script_path=TA, ohlcv_iter=events, syminfo=syminfo,
                                                lossless_prices=True, lossless_volume=True).run_iter()]
    assert rows == _pristine(tmp_path, TA, events, syminfo, False)
