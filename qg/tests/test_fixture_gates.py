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
    assert (p.returncode, p.stdout.strip().splitlines()[-1]) == (0, "DRIFT 6.10.10+qg.1 vs 6.10.10+qg.1: 0/6 jobs differ []")
    q = __test_helper_gate("pynecore.qg_gates.drift", "--baseline-python", py, "--candidate-python", py,
                           "--candidate-env", "PYNE_SUM_MODE=window", "--require-identical")
    assert q.returncode == 1
    assert q.stdout.strip().splitlines()[-1] == "DRIFT 6.10.10+qg.1 vs 6.10.10+qg.1: 3/6 jobs differ [gate_ta@1, gate_ta@2, gate_ta@3]"


def __test_perf_budget_and_injection__():
    py = sys.executable
    args = ("pynecore.qg_gates.perf", "--python", py)
    assert __test_helper_gate(*args).stdout.strip().splitlines()[-1] == "PERF BUDGET PASS"
    q = __test_helper_gate(*args, env={"QG_PERF_INJECT_US": "600"})
    assert (q.returncode, q.stdout.strip().splitlines()[-1]) == (1, "PERF BUDGET FAIL 2 scripts")
