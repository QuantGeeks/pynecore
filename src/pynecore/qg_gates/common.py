"""Shared machinery of the §13.1 gates: jobs, data, rows and the interleave runner.

The proof's ``gatelib.py`` with the fork's adapters: jobs are (id, script, bars)
instead of (label, script, symbol), the data is synthetic bars or Plan 1's
fixtures (never a production symbol), and a row is Task 3's ``_row`` — bit
identity through ``repr``, not a rounding.
"""
import pickle
import random
from pathlib import Path
from typing import NamedTuple

from pynecore.types.ohlcv import OHLCV
from pynecore.lib import label, line, box


class Job(NamedTuple):
    """One gate job: a script, the bars it runs on, and a stable id."""

    id: str
    script: Path
    bars: list[OHLCV]


def synthetic_bars(seed: int, n: int = 600) -> list[OHLCV]:
    """``n`` deterministic bars (Task 3's ``_bars``): a random walk on a 60 s grid."""
    rnd, out, px = random.Random(seed), [], 500.0
    for i in range(n):
        o = round(px, 2)
        c = round(o + rnd.uniform(-0.6, 0.6), 2)
        h = round(max(o, c) + rnd.uniform(0, 0.3), 2)
        l = round(min(o, c) - rnd.uniform(0, 0.3), 2)
        out.append(OHLCV(1779802200000 + 60000 * i, o, h, l, c, float(rnd.randint(50000, 500000))))
        px = c
    return out


def live_events(bars: list[OHLCV], hist: int = 300, live: int = 60, ticks: int = 3) -> list[OHLCV]:
    """Task 3's ``_live`` on given bars: history, the sentinel, intrabar ticks, closes."""
    from pynecore.core.script_runner import LIVE_TRANSITION
    taken = bars[:hist + live]
    ev = taken[:hist] + [LIVE_TRANSITION]
    for b in taken[hist:]:
        for k in range(1, ticks + 1):
            px = round(b.open + (b.close - b.open) * k / (ticks + 1), 2)
            ev.append(OHLCV(b.timestamp, b.open, max(b.open, px), min(b.open, px), px,
                            b.volume * k / (ticks + 1), is_closed=False))
        ev.append(b)
    return ev


def row(candle, plot) -> tuple:
    """One per-bar comparison row: timestamp, the plots by ``repr`` (bit identity),
    and the drawing counts (Task 3's ``_row``)."""
    return (candle.timestamp, tuple(sorted((k, repr(v)) for k, v in plot.items())),
            (len(label.all()), len(line.all()), len(box.all())))


def default_syminfo():
    """The values of upstream's ``tests/conftest.py`` ``syminfo`` fixture (24/7 crypto)."""
    from datetime import time as dtime
    from pynecore.core.syminfo import SymInfo, SymInfoInterval, SymInfoSession
    return SymInfo(
        prefix="PYTEST", description="Pytest Symbol", ticker="TEST", currency="USD",
        period="5", type="crypto", mintick=0.00001000, pricescale=100000, minmove=1,
        pointvalue=1, mincontract=0.0001, timezone="UTC", volumetype="base",
        taker_fee=0.1, maker_fee=0.1,
        opening_hours=[SymInfoInterval(day=i, start=dtime(0, 0), end=dtime(23, 59, 59)) for i in range(7)],
        session_starts=[SymInfoSession(day=i, time=dtime(0, 0)) for i in range(7)],
        session_ends=[SymInfoSession(day=i, time=dtime(23, 59, 59)) for i in range(7)],
    )


def write_data(path: Path, events: list[OHLCV]) -> None:
    """Pickle ``(events, syminfo)`` for :mod:`pynecore.qg_gates.pristine`."""
    Path(path).write_bytes(pickle.dumps((events, default_syminfo())))


def layer_a_jobs() -> list[Job]:
    """Layer A: this package's two scripts on synthetic seeds 1–3."""
    scripts = Path(__file__).resolve().parent / "scripts"
    return ([Job(f"gate_ta@{s}", scripts / "gate_ta.py", synthetic_bars(s)) for s in (1, 2, 3)] +
            [Job(f"gate_draw@{s}", scripts / "gate_draw.py", synthetic_bars(s)) for s in (1, 2, 3)])


def _fixture_bars(csv: Path, n: int = 600) -> list[OHLCV]:
    import csv as _csv
    import gzip
    out: list[OHLCV] = []
    with gzip.open(csv, "rt", newline="") as f:
        reader = _csv.DictReader(f)
        for rec in reader:
            out.append(OHLCV(int(rec["time"]) * 1000, float(rec["open"]), float(rec["high"]),
                             float(rec["low"]), float(rec["close"]), float(rec["Volume"])))
            if len(out) == n:
                break
    return out


def catalogue_jobs(root: Path) -> list[Job]:
    """Plan 1's layout: ``standard/<id>/<id>.py`` and ``house/<id>/<id>.py`` beside a
    ``manifest.toml``, each without ``request.security``, crossed with the first
    three ``fixtures/tradingview/*.manifest.json`` of kind ``script`` or ``feed``.

    Private-CI only: this reads whatever root it is given and never names it.
    """
    import json
    root = Path(root)
    fx = root / "fixtures" / "tradingview"
    if not fx.is_dir():
        print(f"QG-GATES: {root} has no fixtures/tradingview/")
        raise SystemExit(2)
    scripts: list[tuple[str, Path]] = []
    for dir_name in ("standard", "house"):
        base = root / dir_name
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            script = d / f"{d.name}.py"
            if not script.is_file():
                continue
            if "request.security" in script.read_text():
                print(f"QG-GATES: skipped (request.security, spec §4.7): {dir_name}/{d.name}")
                continue
            scripts.append((f"{dir_name}/{d.name}", script))
    fixtures: list[tuple[str, Path]] = []
    for m in sorted(fx.glob("*.manifest.json")):
        meta = json.loads(m.read_text())
        if meta.get("kind") in ("script", "feed"):
            fixtures.append((m.name[:-len(".manifest.json")], m.parent / meta["file"]))
        if len(fixtures) == 3:
            break
    return [Job(f"{fid}@{stem}", script, _fixture_bars(csv))
            for fid, script in scripts for stem, csv in fixtures]


def _start(job: Job, events):
    """Create one runner under its own state and return ``(state, run_iter)``."""
    from pynecore.core import runner_state as rs
    s = rs.new_runner_state()
    r = rs.create_runner(s, script_path=job.script, ohlcv_iter=iter(events),
                         syminfo=default_syminfo(), lossless_prices=True, lossless_volume=True)
    return s, r.run_iter()


def _events(job: Job, live: bool) -> list[OHLCV]:
    return live_events(job.bars) if live else job.bars


def interleave(jobs: list[Job], control: bool = False, order: str = "rr", seed: int = 0,
               live: bool = False):
    """``gatelib.interleave`` kept: a solo reference per job, then the same jobs
    round-robin in one process (``activate`` before each step, unless ``control``),
    one row per bar.  Returns ``(solo, together)`` dicts of rows by job id; a job
    whose solo run raised maps to ``None``.
    """
    from pynecore.core import runner_state as rs
    solo: dict[str, list | None] = {}
    ok: list[Job] = []
    for job in jobs:
        try:
            s, g = _start(job, _events(job, live))
            solo[job.id] = [row(c, p) for c, p in g]
            rs.discard(s)
            ok.append(job)
        except Exception as e:  # a job that cannot run solo is a mismatch, not a skip
            print(f"SOLO FAIL {job.id}: {type(e).__name__}: {str(e)[:200]}")
            solo[job.id] = None
    st, gens, together = [], [], {}
    for job in ok:
        s, g = _start(job, _events(job, live))
        st.append(s)
        gens.append(g)
        together[job.id] = []
    rnd = random.Random(seed)
    active = list(range(len(ok)))
    while active:
        if order == "random":
            rnd.shuffle(active)
        nxt = []
        for i in active:
            if not control:
                rs.activate(st[i])
            try:
                c, p = next(gens[i])
            except StopIteration:
                rs.discard(st[i])
                continue
            together[ok[i].id].append(row(c, p))
            nxt.append(i)
        active = nxt
    return solo, together


def mismatching(jobs: list[Job], solo, together) -> list[str]:
    """The job ids whose solo reference is missing or whose co-resident rows differ."""
    bad = []
    for job in jobs:
        a, b = solo.get(job.id), together.get(job.id)
        if a is None or a != b:
            bad.append(job.id)
    return bad
