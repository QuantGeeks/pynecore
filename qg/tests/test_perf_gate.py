"""The perf gate measures like for like or refuses: base and head run under
interpreters whose build and compiled-natives state it fingerprints, and any
mismatch is a REFUSAL (exit 2) before a single timing — the wheel-vs-sdist and
homebrew-vs-uv confounds that once settled a red gate by ruling (ac0dced9,
reverted). Base and head then INTERLEAVE round-robin (order alternating by
round parity), and the budget is the MEDIAN OF PER-ROUND RATIOS head/base —
one noisy round cannot fail the gate, a real slowdown still does. The stub
pythons below make the gate's subprocess plumbing testable without timing:
they answer the fingerprint probe with a fixed identity and every timed run
with a fixed µs/bar, logging the run order."""
import sys
from pathlib import Path

from pynecore.qg_gates import perf

# (fingerprint probe) -> one JSON line; (timed run) -> one µs/bar line, logged.
# $1=-I $2=-c $3=CODE — the invocation _median_us/_fingerprint use.  FIRST adds
# a round-0 noise injection (the first STUB_FIRST_N compensated runs time
# STUB_FIRST_US) to the head stub ONLY — the base must not carry it, or the
# noise lands on both sides of the ratio and proves nothing.
_STUB = r'''#!/usr/bin/env bash
code="$3"
case "$code" in
  *find_spec*)
    cat <<EOF
{"implementation": "cpython", "natives": %(natives)s, "platform": "stub-arm64", "version": %(version)s}
EOF
    ;;
  *run_iter*)
    us="${STUB_US:-%(us)s}"
%(first)s    echo "$(basename "$0") ${PYNE_SUM_MODE:-compensated}" >> "${STUB_LOG:?}"
    echo "$us"
    ;;
  *) echo "stub python: unexpected -c payload" >&2; exit 64 ;;
esac
'''
_FIRST = r'''    if [ -n "${STUB_FIRST_US:-}" ] && [ "${PYNE_SUM_MODE:-}" != "window" ]; then
      f="${STUB_LOG}.count"
      n="$(cat "$f" 2>/dev/null || echo 0)"
      echo "$((n + 1))" > "$f"
      [ "$n" -lt "${STUB_FIRST_N:-1}" ] && us="$STUB_FIRST_US"
    fi
'''
_SAME_NATIVES = '${STUB_NATIVES:-[]}'


def _stub_venv(tmp_path: Path, name: str, *, us: str = "9.0",
               natives: str = _SAME_NATIVES, version: str = '"3.12.2 (stub)"',
               first: bool = False) -> Path:
    """A stub interpreter with a fixed fingerprint (natives/version) and a fixed
    µs/bar per timed run; ``first`` arms the round-0 noise injection."""
    p = tmp_path / name
    p.write_text(_STUB % {"natives": natives, "version": version, "us": us,
                          "first": _FIRST if first else ""})
    p.chmod(0o755)
    return p


def _like_pair(tmp_path: Path) -> tuple[Path, Path]:
    return _stub_venv(tmp_path, "head"), _stub_venv(tmp_path, "base", us="8.0")


def _run_gate(monkeypatch, capsys, head: Path, base: Path | None, runs: int = 2) -> tuple:
    argv = ["perf", "--python", str(head), "--runs", str(runs)]
    if base is not None:
        argv += ["--baseline-python", str(base)]
    monkeypatch.setattr(sys, "argv", argv)
    code = perf.main()
    return code, capsys.readouterr().out


def __test_a_refuses_an_interpreter_build_mismatch_before_any_timing__(tmp_path, monkeypatch, capsys):
    head = _stub_venv(tmp_path, "head", us="9.0")  # would PASS: 9/8 < 1.25 — must not matter
    base = _stub_venv(tmp_path, "base", us="8.0",
                      version='"3.12.3 (homebrew stub)"')  # a different CPython build string
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "log"))
    monkeypatch.setattr(sys, "argv", ["perf", "--python", str(head), "--baseline-python", str(base)])
    code = perf.main()
    out = capsys.readouterr().out
    assert code == 2
    assert "PERF REFUSE" in out and "interpreter build differs" in out
    # refused BEFORE any timing: the log has no run lines at all
    assert not (tmp_path / "log").exists() or (tmp_path / "log").read_text() == ""


def __test_b_refuses_a_natives_state_mismatch__(tmp_path, monkeypatch, capsys):
    # the head venv carries the compiled natives (a wheel install), the base
    # does not (a git/sdist install): the confound that fooled a local A/B once
    head = _stub_venv(tmp_path, "head",
                      natives='["_native_color", "_native_math", "_native_rolling_sum"]')
    base = _stub_venv(tmp_path, "base", us="8.0")
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "log"))
    monkeypatch.setattr(sys, "argv", ["perf", "--python", str(head), "--baseline-python", str(base)])
    code = perf.main()
    out = capsys.readouterr().out
    assert code == 2
    assert "PERF REFUSE" in out and "natives" in out


def __test_c_like_for_like_interleaves_and_passes__(tmp_path, monkeypatch, capsys):
    head, base = _like_pair(tmp_path)
    log = tmp_path / "log"
    monkeypatch.setenv("STUB_LOG", str(log))
    code, out = _run_gate(monkeypatch, capsys, head, base, runs=3)  # 9/8 = 1.12 < 1.25
    assert code == 0 and "PERF BUDGET PASS" in out
    # INTERLEAVED: within a round each script runs head then base (even rounds)
    # or base then head (odd rounds) — never all of one side first (the old
    # gate ran every baseline run before any head run)
    who = [tuple(l.split()) for l in log.read_text().splitlines()]
    per_script_round = 3  # head-compensated, head-window, base — or base first
    assert who[:per_script_round] == [("head", "compensated"), ("head", "window"),
                                      ("base", "compensated")], "round 0 must run head before base"
    assert who[per_script_round * 2][0] == "base", "round 1 (odd) must flip: base first"
    head_at = [i for i, (w, _) in enumerate(who) if w == "head"]
    base_at = [i for i, (w, _) in enumerate(who) if w == "base"]
    assert min(base_at) > min(head_at), "no base run may precede every head run"


def __test_d_the_median_of_per_round_ratios_absorbs_one_noisy_round__(tmp_path, monkeypatch, capsys):
    # the head's round-0 compensated runs time 40.0 (a 5.0 ratio — runner
    # noise): with 5 rounds the median ratio is still 1.125 and the gate PASSes
    head = _stub_venv(tmp_path, "head", first=True)
    base = _stub_venv(tmp_path, "base", us="8.0")
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "log"))
    monkeypatch.setenv("STUB_FIRST_US", "40.0")
    monkeypatch.setenv("STUB_FIRST_N", "2")  # both scripts' round-0 runs
    code, out = _run_gate(monkeypatch, capsys, head, base, runs=5)
    assert code == 0 and "PERF BUDGET PASS" in out
    assert "rounds 5.00/1.12/1.12/1.12/1.12" in out  # the noisy round is visible…
    assert "ratio 1.12" in out  # …and the median of ratios absorbs it


def __test_e_a_real_slowdown_still_fails__(tmp_path, monkeypatch, capsys):
    head, base = _stub_venv(tmp_path, "head", us="12.0"), _stub_venv(tmp_path, "base", us="8.0")
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "log"))
    code, out = _run_gate(monkeypatch, capsys, head, base, runs=3)  # 12/8 = 1.5 every round
    assert code == 1 and "PERF BUDGET FAIL" in out and "ratio 1.50" in out


def __test_f_the_fingerprint_probe_reports_the_real_interpreter__():
    fp = perf._fingerprint(sys.executable)
    assert fp["implementation"] == "cpython"
    assert fp["version"] == sys.version
    assert fp["platform"]
    assert isinstance(fp["natives"], list)


def __test_g_refuses_when_pynecore_is_not_importable_under_a_python__(tmp_path, monkeypatch, capsys):
    head, base = _stub_venv(tmp_path, "head", natives="null"), _stub_venv(tmp_path, "base", us="8.0")
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "log"))
    monkeypatch.setattr(sys, "argv", ["perf", "--python", str(head), "--baseline-python", str(base)])
    code = perf.main()
    out = capsys.readouterr().out
    assert code == 2
    assert "PERF REFUSE" in out and "not importable" in out


def __test_h_round_order_flips_by_parity__():
    assert perf._round_order(0) == ("head", "base")
    assert perf._round_order(1) == ("base", "head")
    assert perf._round_order(4) == ("head", "base")


def __test_i_without_a_baseline_the_absolute_budget_gates__(tmp_path, monkeypatch, capsys):
    head = _stub_venv(tmp_path, "head", us="30.0")  # > BUDGET 25.5
    monkeypatch.setenv("STUB_LOG", str(tmp_path / "log"))
    code, out = _run_gate(monkeypatch, capsys, head, None)
    assert code == 1 and "PERF BUDGET FAIL" in out and "30.0 us/bar" in out
