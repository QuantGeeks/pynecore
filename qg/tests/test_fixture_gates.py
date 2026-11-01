"""golden, e1_gate, drift and perf on generated series in Plan 1's layout (no fixture, no symbol)."""
import gzip, json, math, os, re, subprocess, sys
from pathlib import Path
from pynecore.qg_gates import common

HDR = "time,open,high,low,close,Volume,sma40\n"


def __test_helper_write(fx: Path, stem: str, seed: int, n: int = 2000, scale: float = 1.0) -> None:
    bars = common.synthetic_bars(seed, n)
    hl2 = [(b.high + b.low) / 2 for b in bars]
    lines = []
    for i, b in enumerate(bars):
        v = "" if i < 39 else repr(sum(hl2[i - 39:i + 1]) / 40 * scale)
        lines.append(f"{b.timestamp // 1000},{b.open!r},{b.high!r},{b.low!r},{b.close!r},{b.volume!r},{v}\n")
    (fx / f"{stem}.csv.gz").write_bytes(gzip.compress((HDR + "".join(lines)).encode(), mtime=0))
    (fx / f"{stem}.manifest.json").write_text(json.dumps({"file": f"{stem}.csv.gz", "kind": "script"}))


def __test_helper_root(tmp_path: Path, further_scale: float = 1.0) -> Path:
    fx = tmp_path / "fixtures" / "tradingview"
    fx.mkdir(parents=True)
    __test_helper_write(fx, "ref", 11)
    __test_helper_write(fx, "more_a", 12)
    __test_helper_write(fx, "more_b", 13, scale=further_scale)
    d = tmp_path / "standard" / "sma40"
    d.mkdir(parents=True)
    (d / "sma40.py").write_text((Path(common.__file__).parent / "scripts" / "e1_sma40.py").read_text())
    (d / "manifest.toml").write_text("")
    return tmp_path


def __test_helper_gate(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", "-m", *args], capture_output=True, text=True,
                          env={**os.environ, "PYNE_SAVE_SCRIPT_TOML": "0", **(env or {})})


def __test_compare_columns__():
    tv = [None, 1.0, 2.0, 3.0, None, 5.0]
    ours = [math.nan, 1.0, 2.0 * (1 + 1e-12), 3.0001, 4.0, 5.0]
    assert common.compare_columns(tv, ours, warmup=1) == (2, 3, 5)


def __test_e1_gate_passes_and_counts_agreement__(tmp_path):
    r = __test_helper_root(tmp_path)
    p = __test_helper_gate("pynecore.qg_gates.e1_gate", "--root", str(r), "--reference", "ref",
                           "--further", "more_*", "--expect-window", "1961")
    assert p.returncode == 0, p.stdout + p.stderr
    assert re.search(r"^E1 ref: compensated exact (\d+)/1961 window exact 1961/1961$", p.stdout, re.M)
    assert p.stdout.strip().splitlines()[-1] == "E1 GATE (§9.2): PASSED"
    q = __test_helper_gate("pynecore.qg_gates.e1_gate", "--root", str(__test_helper_root(tmp_path / "b", 1 + 1e-6)),
                           "--reference", "ref", "--further", "more_*", "--expect-window", "1961")
    assert q.stdout.strip().splitlines()[-1] == "E1 GATE (§9.2): 1 of 2 further exports agree; window mode stays off by default"


def __test_e1_gate_refuses_a_failed_reproduction__(tmp_path):
    p = __test_helper_gate("pynecore.qg_gates.e1_gate", "--root", str(__test_helper_root(tmp_path)), "--reference", "ref",
                           "--further", "more_*", "--expect-window", "1960")
    assert p.returncode == 1
    assert re.match(r"^E1 REPRODUCTION FAIL ref: compensated \d+ window 1961$", p.stdout.strip().splitlines()[-1])


def __test_golden_pass_and_shift_fail__(tmp_path):
    r = __test_helper_root(tmp_path)
    for shift, code, last in ((0, 0, "GOLDEN PASS 1 columns"), (1, 1, "GOLDEN FAIL 1 of 1 columns")):
        spec = tmp_path / f"golden{shift}.json"
        spec.write_text(json.dumps([{"script": "standard/sma40", "stem": "ref",
                                     "columns": [{"tv_index": 6, "plot": "sma40", "shift": shift}]}]))
        p = __test_helper_gate("pynecore.qg_gates.golden", "--root", str(r), "--spec", str(spec))
        assert (p.returncode, p.stdout.strip().splitlines()[-1]) == (code, last), p.stdout


def __test_drift_identical_and_mode_control__():
    py = sys.executable
    p = __test_helper_gate("pynecore.qg_gates.drift", "--baseline-python", py, "--candidate-python", py, "--require-identical")
    assert (p.returncode, p.stdout.strip().splitlines()[-1]) == (0, "DRIFT 6.10.10+qg.2 vs 6.10.10+qg.2: 0/7 jobs differ []")
    q = __test_helper_gate("pynecore.qg_gates.drift", "--baseline-python", py, "--candidate-python", py,
                           "--candidate-env", "PYNE_SUM_MODE=window", "--require-identical")
    assert q.returncode == 1
    assert q.stdout.strip().splitlines()[-1] == "DRIFT 6.10.10+qg.2 vs 6.10.10+qg.2: 4/7 jobs differ [gate_ta@1, gate_ta@2, gate_ta@3, gate_ta@4]"


def __test_perf_budget_and_injection__():
    # The property under test is the INJECTION (600 us/bar fails every script), not the absolute
    # budget: qg-ci's shared runner is sometimes slow enough to fail 25.5 us/bar unchanged
    # (2026-11-01: run 41292493241 failed 1 script, the next run passed the same code). The
    # uninjected run must print a well-formed budget line; the injected run must fail both.
    py = sys.executable
    args = ("pynecore.qg_gates.perf", "--python", py)
    base = __test_helper_gate(*args).stdout.strip().splitlines()[-1]
    assert re.fullmatch(r"PERF BUDGET (PASS|FAIL [12] scripts)", base), base
    q = __test_helper_gate(*args, env={"QG_PERF_INJECT_US": "600"})
    assert (q.returncode, q.stdout.strip().splitlines()[-1]) == (1, "PERF BUDGET FAIL 2 scripts")


def __test_catalogue_skips_the_shared_form__(tmp_path, capsys):
    """ X1: a directory with <id>_security.py, or whose <id>.py imports
    indicator_service, is skipped with one line: the shared form runs only
    inside the service """
    r = __test_helper_root(tmp_path)
    for sid, body in (("senti", '"""\n@pyne\n"""\n'), ("levels", "import indicator_service\n")):
        d = r / "standard" / sid
        d.mkdir(parents=True)
        (d / f"{sid}.py").write_text(body)
        (d / "manifest.toml").write_text("")
    (r / "standard" / "senti" / "senti_security.py").write_text("# the shared form\n")
    capsys.readouterr()
    jobs = common.catalogue_jobs(r)
    assert not [j.id for j in jobs if j.id.startswith(("standard/senti@", "standard/levels@"))]
    out = capsys.readouterr().out
    assert "QG-GATES: skipped standard/senti: shared form\n" in out
    assert "QG-GATES: skipped standard/levels: shared form\n" in out
    assert [j.id for j in jobs if j.id.startswith("standard/sma40@")]  # the control: others run


def __test_load_tv_export_names_volume_and_drops_empty_rows__(tmp_path):
    """ X2: Volume is read by header name (here at index 8), and rows with empty
    OHLC — an Ichimoku export's forward rows — are dropped """
    import gzip as _gzip
    f = tmp_path / "late_volume.csv.gz"
    head = "time,open,high,low,close,anchor,signal,vwap,Volume\n"  # plots at 6-7, Volume at 8
    good = [(1700000000 + 60 * i, 1 + i, 2 + i, 0.5 + i, 1.5 + i, 30.0 + i, 20.0 + i, 10.0 + i,
             100.0 + i) for i in range(4)]
    rows = [",".join(repr(x) for x in row) for row in good]
    rows.append(f"{1700000240},,,,," + "6.6" + ",8.8,9.9,7.7")  # forward row: OHLC empty
    f.write_bytes(_gzip.compress((head + "\n".join(rows) + "\n").encode(), mtime=0))
    bars, headers, cols = common.load_tv_export(f)
    assert [b.volume for b in bars] == [100.0, 101.0, 102.0, 103.0]  # by NAME, not index 5
    assert len(bars) == 4                                                            # the empty row dropped
    assert headers == ["signal", "vwap", "Volume"]          # the columns from index 6 on, raw order
    assert cols[0] == [20.0, 21.0, 22.0, 23.0]              # every column dropped the empty row
    assert cols[1] == [10.0, 11.0, 12.0, 13.0]
    assert cols[2] == [100.0, 101.0, 102.0, 103.0]          # the late Volume stays addressable at raw 8
    assert not any(9.9 in c or 7.7 in c for c in cols)      # the dropped row's cells are gone


def __test_fixture_syminfo_derives_the_session__(tmp_path):
    """ X3: the fixture manifest's session and tv_symbol derive the SymInfo; the
    default stays the 24/7 instrument session """
    from datetime import time as dtime
    base = common.fixture_syminfo({})
    ext = common.fixture_syminfo({"session": "extended", "tv_symbol": "AMEX:SPY"})
    reg = common.fixture_syminfo({"session": "regular"})
    assert ext.prefix == "AMEX" and ext.ticker == "SPY"
    assert (ext.opening_hours[0].start, ext.opening_hours[0].end) == (dtime(4, 0), dtime(20, 0))
    assert (reg.opening_hours[0].start, reg.opening_hours[0].end) == (dtime(9, 30), dtime(16, 0))
    assert len(reg.opening_hours) == 5                                    # Mon-Fri, not the default 7 days
    assert (base.opening_hours[0].start, len(base.opening_hours)) == (dtime(0, 0), 7)
    jobs = common.catalogue_jobs(__test_helper_root(tmp_path))            # the control: jobs carry it
    assert all(j.syminfo is not None for j in jobs)


def __test_golden_offset_twentyfive__(tmp_path):
    """ X4: shift is minus the plot offset — the export's row i holds the value
    the engine computes at bar i+25; shift 25 passes, 24 and the wrong sign fail """
    import gzip as _gzip
    r = __test_helper_root(tmp_path)
    fx = r / "fixtures" / "tradingview"
    bars = common.synthetic_bars(21, 2000)
    hl2 = [(b.high + b.low) / 2 for b in bars]
    eng = [None if i < 39 else sum(hl2[i - 39:i + 1]) / 40 for i in range(len(bars))]
    lines = [f"{b.timestamp // 1000},{b.open!r},{b.high!r},{b.low!r},{b.close!r},{b.volume!r},"
             f"{'' if (i < 14 or i + 25 >= len(eng) or eng[i + 25] is None) else repr(eng[i + 25])}\n"
             for i, b in enumerate(bars)]
    (fx / "lag.csv.gz").write_bytes(_gzip.compress((HDR + "".join(lines)).encode(), mtime=0))
    (fx / "lag.manifest.json").write_text(json.dumps({"file": "lag.csv.gz", "kind": "script"}))
    for shift, code, last in ((25, 0, "GOLDEN PASS 1 columns"),
                              (24, 1, "GOLDEN FAIL 1 of 1 columns"),
                              (-25, 1, "GOLDEN FAIL 1 of 1 columns")):
        spec = tmp_path / f"lag{shift}.json"
        spec.write_text(json.dumps([{"script": "standard/sma40", "stem": "lag",
                                     "columns": [{"tv_index": 6, "plot": "sma40", "shift": shift}]}]))
        p = __test_helper_gate("pynecore.qg_gates.golden", "--root", str(r), "--spec", str(spec))
        assert (p.returncode, p.stdout.strip().splitlines()[-1]) == (code, last), (shift, p.stdout)


def __test_fixture_syminfo_runs_on_eastern_time__(tmp_path):
    """ X5: under fixture_syminfo({"session": "regular"}) the engine's session
    clock is Eastern — session.isfirstbar fires on exactly the 09:30 ET bars;
    under UTC the same session contains none of them """
    script = tmp_path / "isfirstbar_probe.py"
    script.write_text('"""\n@pyne\n"""\n'
                      "from pynecore.lib import script, session, plot\n\n\n"
                      '@script.indicator("isfirstbar probe")\n'
                      'def main():\n    plot(session.isfirstbar, "first")\n')
    bars, px, rnd = [], 500.0, __import__("random").Random(31)
    day = 1779802200  # 09:30 ET
    while len(bars) < 800:  # three RTH sessions of 1-minute bars
        for k in range(390):
            o = round(px, 2)
            c = round(o + rnd.uniform(-0.6, 0.6), 2)
            bars.append(common.OHLCV((day + 60 * k) * 1000, o,
                                     round(max(o, c) + rnd.uniform(0, 0.3), 2),
                                     round(min(o, c) - rnd.uniform(0, 0.3), 2), c,
                                     float(rnd.randint(50000, 500000))))
            px = c
            if len(bars) == 800:
                break
        day += 86400
    si = common.fixture_syminfo({"session": "regular"})
    rows = common._run_swapped(script, bars, syminfo=si)
    flagged = [c.timestamp for c, p in rows if p.get("first")]
    assert flagged == [1779802200000, 1779888600000, 1779975000000]
    import dataclasses
    utc = dataclasses.replace(si, timezone="UTC")  # the negative control: no bar in session
    rows = common._run_swapped(script, bars, syminfo=utc)
    assert not [c.timestamp for c, p in rows if p.get("first")]


def __test_empty_volume_cells_are_zero__(tmp_path):
    """ X6: an empty Volume cell is 0.0 in load_tv_export and in _fixture_bars
    (the SPX and index feeds carry an all-empty Volume column; float("") raises) """
    import gzip as _gzip
    f = tmp_path / "no_volume.csv.gz"
    rows = "".join(f"{1700000000 + 60 * i},1,2,0.5,1.5,\n" for i in range(3))
    f.write_bytes(_gzip.compress(("time,open,high,low,close,Volume\n" + rows).encode(), mtime=0))
    bars, _headers, _cols = common.load_tv_export(f)
    assert [b.volume for b in bars] == [0.0, 0.0, 0.0]
    root = tmp_path / "root"
    fx = root / "fixtures" / "tradingview"
    d = root / "standard" / "sma40"
    fx.mkdir(parents=True)
    d.mkdir(parents=True)
    (fx / "only.csv.gz").write_bytes(f.read_bytes())
    (fx / "only.manifest.json").write_text(json.dumps({"file": "only.csv.gz", "kind": "script"}))
    (d / "sma40.py").write_text((Path(common.__file__).parent / "scripts" / "e1_sma40.py").read_text())
    (d / "manifest.toml").write_text("")
    jobs = common.catalogue_jobs(root)  # the control: no ValueError, jobs come back
    assert [j.id for j in jobs] == ["standard/sma40@only"]
    assert [b.volume for b in jobs[0].bars] == [0.0, 0.0, 0.0]


def __test_fresh_state_restores_the_session_lists__():
    """ gate 2 on the real catalogue (2026-11-01): a regular-session run left its lists on lib.syminfo """
    from pynecore.core import runner_state as rs
    from pynecore.lib import syminfo as lib_syminfo
    job = next(j for j in common.layer_a_jobs() if j.id == "gate_ta@4")
    s = rs.new_runner_state()
    for _ in rs.create_runner(s, script_path=job.script, ohlcv_iter=iter(job.bars[:300]), syminfo=job.syminfo,
                              lossless_prices=True, lossless_volume=True).run_iter():
        pass
    assert len(lib_syminfo.opening_hours) == 5           # the run installed Mon-Fri
    rs.discard(s)
    rs.activate(rs.new_runner_state())
    assert lib_syminfo.opening_hours == [] and lib_syminfo.session_starts == [] and lib_syminfo.session_ends == []
    assert lib_syminfo._size_round_factor == 1.0
