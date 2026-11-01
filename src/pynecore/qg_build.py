"""The build manifest the service's worker asserts at start, and ``engine_ver``.

The contract Plan 4 consumes (spec 13.1 item 1, 4.6): ``python -m
pynecore.qg_build`` prints the manifest as JSON with sorted keys and indent 2 —
redirected to a file it is the expected manifest the service's image ships, and
the worker calls :func:`assert_build` on it at start, so a wheel or interpreter
that is not the one the values were produced for refuses to run.  The one
``engine_ver`` formula (spec 4.6: the engine version plus the adapter version;
the swap's sha and the sum mode join it because either changes values) is
``f"{version}/{swap_sha[:12]}/{sum_mode}/svc{adapter_version}"``.
"""
import hashlib
import json
import platform
import sys
from importlib import import_module
from pathlib import Path

#: The extensions whose compiled twin may be installed; each importable one's
#: loaded file is hashed into the manifest.
NATIVE_EXTENSIONS = ("_native_color", "_native_math", "_native_rolling_sum")


def _dist_version() -> str:
    import importlib.metadata as metadata
    return metadata.version("pynesys-pynecore")


def version() -> str:
    """The installed ``pynesys-pynecore`` distribution version (spec 4.9's PEP
    440 fork form, e.g. ``6.10.10+qg.1``)."""
    return _dist_version()


def build_manifest() -> dict:
    """Everything a build is: distribution, version, the swap module's sha and
    tracked-name count, each importable native extension's file sha, and the
    interpreter's version and machine."""
    from pynecore.core import runner_state
    native = {}
    for name in NATIVE_EXTENSIONS:
        try:
            mod = import_module(f"pynecore.core.{name}")
        except ImportError:
            continue
        native[name] = hashlib.sha256(Path(mod.__file__).read_bytes()).hexdigest()
    return {
        "distribution": "pynesys-pynecore",
        "version": _dist_version(),
        "swap_sha": runner_state.swap_sha(),
        "tracked_names": len(runner_state.tracked_names()),
        "native": native,
        "python": platform.python_version(),
        "machine": platform.machine(),
    }


def assert_build(expected_manifest_path: Path) -> None:
    """Refuse to run unless the manifest matches the expected one, key by key
    in sorted order (the worker's start check, spec 13.1 item 1).

    :param expected_manifest_path: a ``python -m pynecore.qg_build`` redirect.
    :raises RuntimeError: naming the first mismatching key.
    """
    expected = json.loads(Path(expected_manifest_path).read_text())
    got = build_manifest()
    for key in sorted(expected):
        if got.get(key) != expected[key]:
            raise RuntimeError(f"pynecore build mismatch: {key}: expected {expected[key]!r}, "
                               f"got {got.get(key)!r}")


def engine_ver(adapter_version: int, sum_mode: str, *, version: str | None = None,
               swap_sha: str | None = None) -> str:
    """The one engine version string (spec 4.6): the engine version plus the
    adapter version, with the swap's sha and the sum mode joined because either
    changes values — ``<version>/<swap_sha[:12]>/<sum_mode>/svc<adapter>``.

    :param adapter_version: the service's adapter version (``svc<N>``).
    :param sum_mode: one of ``rolling_sum.SUM_MODES`` (spec 9.2, E1).
    :param version: override for the distribution version (tests).
    :param swap_sha: override for the swap sha (tests).
    :raises ValueError: on a sum mode that is not ``rolling_sum.SUM_MODES``.
    """
    from pynecore.core import rolling_sum, runner_state
    if sum_mode not in rolling_sum.SUM_MODES:
        raise ValueError(f"sum mode must be one of {rolling_sum.SUM_MODES}, got {sum_mode!r}")
    sha = swap_sha if swap_sha is not None else runner_state.swap_sha()
    return (f"{version if version is not None else _dist_version()}/"
            f"{sha[:12]}/{sum_mode}/svc{adapter_version}")


if __name__ == "__main__":
    print(json.dumps(build_manifest(), sort_keys=True, indent=2))
    sys.exit(0)
