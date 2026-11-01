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
    """One gate job: a script, the bars it runs on, a stable id, and (for
    fixture bars) the SymInfo the fixture's manifest derives."""

    id: str
    script: Path
    bars: list[OHLCV]
    syminfo: object = None


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


def write_data(path: Path, events: list[OHLCV], syminfo=None) -> None:
    """Pickle ``(events, syminfo)`` for :mod:`pynecore.qg_gates.pristine`."""
    Path(path).write_bytes(pickle.dumps((events, syminfo or default_syminfo())))


def layer_a_jobs() -> list[Job]:
    """Layer A: this package's two scripts on synthetic seeds 1–3."""
    scripts = Path(__file__).resolve().parent / "scripts"
    return ([Job(f"gate_ta@{s}", scripts / "gate_ta.py", synthetic_bars(s)) for s in (1, 2, 3)] +
            [Job(f"gate_ta@4", scripts / "gate_ta.py", synthetic_bars(4),
                 fixture_syminfo({"session": "regular", "tv_symbol": "AMEX:SPY"}))] +
            [Job(f"gate_draw@{s}", scripts / "gate_draw.py", synthetic_bars(s)) for s in (1, 2, 3)])


BASE_HEADERS = ("time", "open", "high", "low", "close", "Volume")


def _fixture_bars(csv: Path, n: int = 600) -> list[OHLCV]:
    import csv as _csv
    import gzip
    out: list[OHLCV] = []
    with gzip.open(csv, "rt", newline="") as f:
        for rec in _csv.DictReader(f):
            vol = 0.0 if rec["Volume"] == "" else float(rec["Volume"])  # Plan 5 Task 1's rule
            out.append(OHLCV(int(rec["time"]) * 1000, float(rec["open"]), float(rec["high"]),
                             float(rec["low"]), float(rec["close"]), vol))
            if len(out) == n:
                break
    return out


def fixture_syminfo(manifest: dict):
    """The SymInfo a fixture runs with: the 24/7 default, with the session and
    tv_symbol the fixture's manifest declares (an extended export must run with
    the extended session — the default SymInfo mismatches VWAP ext by ~16k
    values per plot; ruling 2026-11-01, Plan 5 review X3).

    ``session``: ``regular`` (Mon-Fri 09:30-16:00), ``extended`` (Mon-Fri
    04:00-20:00) or ``instrument``/absent (the 24/7 default).  ``tv_symbol``
    ``PREFIX:SYMBOL`` sets prefix and ticker.  The derived SymInfo always runs
    on ``America/New_York``: the engine evaluates ``opening_hours`` in
    ``syminfo.timezone``, and under the default's ``UTC`` a 09:30-16:00 session
    contains no SPY bar (``session.isfirstbar`` fires on no bar, ``islastbar``
    at 11:55 ET; ruling 2026-11-01, Plan 5 review X5).
    """
    from datetime import time as dtime
    from pynecore.core.syminfo import SymInfoInterval, SymInfoSession
    si = default_syminfo()
    si.timezone = "America/New_York"
    session = (manifest or {}).get("session")
    if session in ("regular", "extended"):
        start, end = (dtime(9, 30), dtime(16, 0)) if session == "regular" else (dtime(4, 0), dtime(20, 0))
        si.opening_hours = [SymInfoInterval(day=d, start=start, end=end) for d in range(5)]
        si.session_starts = [SymInfoSession(day=d, time=start) for d in range(5)]
        si.session_ends = [SymInfoSession(day=d, time=end) for d in range(5)]
    symbol = (manifest or {}).get("tv_symbol")
    if symbol:
        prefix, _sep, ticker = symbol.rpartition(":")
        if prefix:
            si.prefix, si.ticker = prefix, ticker
        else:
            si.ticker = symbol
    return si


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
            if (d / f"{d.name}_security.py").is_file() or "indicator_service" in script.read_text():
                # the shared form runs only inside the service (Senti today,
                # Plan 5's session_levels later); ruling 2026-11-01, X1
                print(f"QG-GATES: skipped {dir_name}/{d.name}: shared form")
                continue
            scripts.append((f"{dir_name}/{d.name}", script))
    fixtures: list[tuple[str, Path, dict]] = []
    for m in sorted(fx.glob("*.manifest.json")):
        meta = json.loads(m.read_text())
        if meta.get("kind") in ("script", "feed"):
            fixtures.append((m.name[:-len(".manifest.json")], m.parent / meta["file"], meta))
        if len(fixtures) == 3:
            break
    return [Job(f"{fid}@{stem}", script, _fixture_bars(csv), fixture_syminfo(meta))
            for fid, script in scripts for stem, csv, meta in fixtures]


def _start(job: Job, events):
    """Create one runner under its own state and return ``(state, run_iter)``."""
    from pynecore.core import runner_state as rs
    s = rs.new_runner_state()
    r = rs.create_runner(s, script_path=job.script, ohlcv_iter=iter(events),
                         syminfo=job.syminfo or default_syminfo(),
                         lossless_prices=True, lossless_volume=True)
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


def load_tv_export(path: Path) -> tuple[list[OHLCV], list[str], list[list[float | None]]]:
    """A TradingView "Download chart data" export: the bars (ms timestamps), the
    plot-column titles from index 6 on, and each column's values (``None`` = the
    empty cell) — ``cmp.load_tv`` reduced to the fork's fixed layout.  The six
    bar fields are read BY HEADER NAME — the VWAP exports carry ``Volume`` at
    index 8, Supertrend at 7; never column 5 — and rows whose open/high/low/
    close are empty (an Ichimoku export's forward rows) are dropped before the
    bars and the columns are built (ruling 2026-11-01, Plan 5 review X2)."""
    import csv as _csv
    import gzip
    p = Path(path)
    with (gzip.open if p.name.endswith(".gz") else open)(p, "rt", newline="") as f:
        rows = list(_csv.reader(f))
    head, data = rows[0], rows[1:]
    at = {name: head.index(name) for name in BASE_HEADERS if name in head}

    def _num(cell: str) -> float | None:
        return None if cell == "" else float(cell)

    keep = [r for r in data if all(r[at[f]] != "" for f in ("open", "high", "low", "close"))]
    bars = [OHLCV(int(r[at["time"]]) * 1000, float(r[at["open"]]), float(r[at["high"]]),
                  float(r[at["low"]]), float(r[at["close"]]),
                  0.0 if r[at["Volume"]] == "" else float(r[at["Volume"]]))
            for r in keep]  # an empty Volume cell is 0.0 (Plan 5 Task 1's rule)
    headers = head[6:]
    cols = [[None if r[6 + i] == "" else float(r[6 + i]) for r in keep]
            for i in range(len(headers))]
    return bars, headers, cols


def compare_columns(tv: list[float | None], ours: list[float], warmup: int) -> tuple[int, int, int]:
    """``cmp.stats`` kept, reduced to ``(exact, rel9, n)`` over the bars from
    ``warmup`` on where either side has a value: exact is float64 equality,
    rel9 is ``d <= 1e-9 * max(|a|, |b|)`` or ``d <= 1e-12``, and one na against
    one value fails both (a nan on our side is na)."""
    exact = rel9 = n = 0
    for i in range(warmup, min(len(tv), len(ours))):
        a, b = tv[i], ours[i]
        if isinstance(b, float) and b != b:
            b = None
        if a is None and b is None:
            continue
        n += 1
        if a is None or b is None:
            continue
        if a == b:
            exact += 1
            rel9 += 1
        elif abs(a - b) <= 1e-9 * max(abs(a), abs(b)) or abs(a - b) <= 1e-12:
            rel9 += 1
    return exact, rel9, n


def _run_swapped(script: Path, bars, inputs: dict | None = None, sum_mode: str = "compensated",
                 syminfo=None) -> list[tuple]:
    """Run one script once under its own state (the gates' pattern): fresh state,
    per-state script import, one row per bar, baseline restored on discard."""
    from pynecore.core import runner_state as rs
    s = rs.new_runner_state(sum_mode=sum_mode)
    kwargs = dict(script_path=script, ohlcv_iter=iter(bars),
                  syminfo=syminfo or default_syminfo(),
                  lossless_prices=True, lossless_volume=True)
    if inputs:
        kwargs["inputs"] = inputs
    g = rs.create_runner(s, **kwargs).run_iter()
    rs.activate(s)
    rows = [(c, dict(p)) for c, p in g]
    rs.discard(s)
    return rows
