"""pynecore.qg_gates.common: Layer A from the package, Plan 1's layout for the catalogue (synthetic files only)."""
import gzip, json, subprocess, sys
from pathlib import Path
from pynecore.qg_gates import common


def __test_helper_root(tmp_path: Path) -> Path:
    for d, body in (("standard/alpha", ""), ("standard/beta", "# request.security\n")):
        (tmp_path / d).mkdir(parents=True)
        (tmp_path / d / f"{Path(d).name}.py").write_text('"""\n@pyne\n"""\n' + body)
        (tmp_path / d / "manifest.toml").write_text("")
    fx = tmp_path / "fixtures" / "tradingview"
    fx.mkdir(parents=True)
    rows = "".join(f"{1700000000 + 60 * i},1,2,0.5,1.5,10\n" for i in range(700))
    for k in range(4):
        (fx / f"x{k}.csv.gz").write_bytes(gzip.compress(("time,open,high,low,close,Volume\n" + rows).encode(), mtime=0))
        (fx / f"x{k}.manifest.json").write_text(json.dumps({"file": f"x{k}.csv.gz", "kind": "script"}))
    return tmp_path


def __test_layer_a_comes_from_the_package__():
    jobs = common.layer_a_jobs()
    assert [j.id for j in jobs] == ["gate_ta@1", "gate_ta@2", "gate_ta@3", "gate_ta@4", "gate_draw@1", "gate_draw@2", "gate_draw@3"]
    assert {j.script.parent for j in jobs} == {Path(common.__file__).parent / "scripts"}
    assert len(jobs[0].bars) == 600


def __test_catalogue_reads_plan_1_layout__(tmp_path, capsys):
    jobs = common.catalogue_jobs(__test_helper_root(tmp_path))
    assert [j.id for j in jobs] == ["standard/alpha@x0", "standard/alpha@x1", "standard/alpha@x2"]
    assert capsys.readouterr().out == "QG-GATES: skipped (request.security, spec §4.7): standard/beta\n"
    assert len(jobs[0].bars) == 600 and jobs[0].bars[1].timestamp == 1700000060000


def __test_missing_fixtures_exit_2__(tmp_path):
    p = subprocess.run([sys.executable, "-I", "-m", "pynecore.qg_gates.gate1_pristine", "--root", str(tmp_path)],
                       capture_output=True, text=True)
    assert p.returncode == 2
    assert p.stdout.strip().splitlines()[-1] == f"QG-GATES: {tmp_path} has no fixtures/tradingview/"


def __test_fingerprint_is_pycache_independent__(tmp_path):
    """ typing aliases are leaves: the fingerprint is identical cold and warm
    (ruling 2026-10-31: pre-adapt, a cold venv recorded the alias as a leaf and a
    warm one expanded it into six children) """
    import json
    import pynecore
    import shutil
    import subprocess
    code = ("import json\n"
            # the full deterministic module set, exactly as gate4 imports it
            "import pynecore.core.runner_state\n"
            "from pynecore.qg_gates import fingerprint as FP\n"
            "fp = FP.fingerprint()\n"
            # the transformers registry is compile-time cache, ignored everywhere
            "print(json.dumps({k: v for k, v in fp.items() if not k.startswith('pynecore.transformers')}))\n")
    env = dict(__import__("os").environ, PYNE_SAVE_SCRIPT_TOML="0")
    pkg = Path(pynecore.__file__).parent
    for d in pkg.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    cold = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True,
                          env=env)          # cold import, writes the bytecode
    warm = subprocess.run([sys.executable, "-I", "-B", "-c", code], capture_output=True, text=True,
                          env=env)          # warm import (cold's bytecode present), writes nothing
    assert cold.returncode == 0 and warm.returncode == 0, cold.stderr[-500:] + warm.stderr[-500:]
    fa, fb = json.loads(cold.stdout), json.loads(warm.stdout)
    assert [k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)] == []
