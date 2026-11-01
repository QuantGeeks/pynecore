"""pynecore.qg_build: the manifest the worker asserts at start, and the one engine_ver formula."""
import json
import pytest
from pynecore import qg_build
from pynecore.core import runner_state


def __test_manifest_fields__():
    m = qg_build.build_manifest()
    assert m["distribution"] == "pynesys-pynecore" and m["version"] == qg_build.version() == "6.10.10+qg.3"
    assert m["swap_sha"] == runner_state.swap_sha() and m["tracked_names"] == 440
    assert set(m["native"]) <= {"_native_color", "_native_math", "_native_rolling_sum"}
    assert all(len(v) == 64 for v in m["native"].values())


def __test_assert_build_refuses_a_mismatch__(tmp_path):
    m = qg_build.build_manifest()
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(m)); bad.write_text(json.dumps(dict(m, swap_sha="0" * 64)))
    qg_build.assert_build(good)
    with pytest.raises(RuntimeError, match=r"^pynecore build mismatch: swap_sha: expected '0{64}', got '"):
        qg_build.assert_build(bad)


def __test_engine_ver_vectors__():
    assert qg_build.engine_ver(1, "compensated", version="6.10.10+qg.3", swap_sha="ab" * 32) == "6.10.10+qg.3/abababababab/compensated/svc1"
    assert qg_build.engine_ver(1, "window", version="6.10.10+qg.3", swap_sha="ab" * 32) == "6.10.10+qg.3/abababababab/window/svc1"
    assert qg_build.engine_ver(2, "compensated") == f"6.10.10+qg.3/{runner_state.swap_sha()[:12]}/compensated/svc2"
    with pytest.raises(ValueError):
        qg_build.engine_ver(1, "kahan")
