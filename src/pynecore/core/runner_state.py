"""
Per-runner module state for co-resident ScriptRunners (QuantGeeks fork, spec 4.2).

PyneCore keeps bar state and per-call-site ``ta`` state in module globals, so two
ScriptRunners stepping in one process corrupt each other (11 of 15 interleaved
pairs in our control; spec 1.5). This module hosts many runners by giving each
one its own view of those globals: :func:`activate` installs a state's values,
its own ``instance_state._shared_caches`` contents, its own root vectors and its
own ``sys.modules`` entry for the script, saving the outgoing state's current
values first. Between one ``activate`` and the next, only that state's runner
steps; under that rule every runner's per-bar plots and drawing counts equal a
pristine run of the same script, data and sum mode in its own process (proved,
``proof/upgrade/``).

Import this module before creating any runner: the baseline is captured at
import, and importing while a runner is live is refused, so the baseline can
never capture a runner's live state.

The tracked set is every lowercase, non-dunder, non-callable module global of
every ``pynecore.{lib,core,types}`` module except the SKIP prefixes (the CLI,
providers, broker, testing, pynesys, transformers — and this module), with the
proof's type-name exclusions. ALLCAPS names are excluded as constants; the one
that matters is repaired by :func:`_rebind_registries`:
``drawing_snapshot._REGISTRIES`` is a tuple of the *baseline* drawing registries
built at import, and it must be rebound to the live ones after every switch or a
``DrawingSnapshot`` saves and restores the empty originals and live drawings
pile up to the 500 cap (the proof's P7).
"""
import copy
import hashlib
import importlib
import sys
import types
from pathlib import Path
from typing import Any, Generator

import pynecore
from pynecore.core import instance_state, rolling_sum
from pynecore.core.script_runner import ScriptRunner, script_module_name

if instance_state._root_vectors:
    raise RuntimeError("pynecore.core.runner_state imported while a runner is live; "
                       "import it before creating runners")

#: Module prefixes whose globals are not runner state: the CLI, the providers,
#: the broker stack, the testing helpers, the pynesys extras, the transformers —
#: and this module itself (its own globals are the swap machinery, not state).
SKIP = ("pynecore.cli", "pynecore.providers", "pynecore.core.broker", "pynecore.testing",
        "pynecore.pynesys", "pynecore.transformers", "pynecore.core.runner_state")

_ROOT = Path(pynecore.__file__).parent
for _sub in ("lib", "core", "types"):
    for _f in sorted((_ROOT / _sub).rglob("*.py")):
        _n = ".".join(_f.relative_to(_ROOT.parent).with_suffix("").parts).removesuffix(".__init__")
        if not _n.startswith(SKIP):
            try:
                importlib.import_module(_n)
            except BaseException:
                pass

_NOT_STATE = (types.ModuleType, types.FunctionType, types.BuiltinFunctionType, type,
              types.MethodType)
_TYPE_EXCLUSIONS = ("Logger", "StreamHandler", "TypeVar", "_Feature", "ForkServerContext",
                    "SpawnContext", "Color", "UnionType")


def _tracked() -> list[tuple[types.ModuleType, str]]:
    """Every ``(module, attr)`` the swap saves and installs, in scan order."""
    out = []
    for name, mod in sorted(sys.modules.items()):
        if mod is None or not name.startswith("pynecore.") or name.startswith(SKIP):
            continue
        for k, v in vars(mod).items():
            if k.startswith("__") or k.isupper() or isinstance(v, _NOT_STATE):
                continue
            if type(v).__name__ in _TYPE_EXCLUSIONS:
                continue
            if callable(v) and not isinstance(v, (dict, list)):
                continue
            out.append((mod, k))
    return out


_TRACKED = _tracked()
#: The untouched values a fresh state starts from, captured once at import.
_BASELINE = {(m, k): getattr(m, k) for m, k in _TRACKED}
#: Dicts the runtime mutates in place: swapped by content, never rebound.
_CACHES = instance_state._shared_caches


def _fresh(v: Any) -> Any:
    """A new-state copy of a baseline value: containers (and drawing registries)
    are deep-copied; immutable values are shared as-is."""
    if isinstance(v, (dict, list, set)) or type(v).__name__ == "PlotMetaRegistry":
        return copy.deepcopy(v)
    return v


class RunnerState:
    """One runner's view of PyneCore's module globals (opaque; read ``sum_mode``)."""

    __slots__ = ("vals", "caches", "modules", "_sum_mode")

    def __init__(self, sum_mode: str) -> None:
        self.vals: dict[tuple[types.ModuleType, str], Any] = {
            key: _fresh(v) for key, v in _BASELINE.items()}
        # A fresh state runs no runner yet: no root vectors, empty shared caches,
        # no script module — and its own sum mode (spec 9.2 E1).
        self.vals[(rolling_sum, "_sum_mode")] = sum_mode
        self.caches: list[dict] = [{} for _ in _CACHES]
        self.modules: dict[str, types.ModuleType | None] = {}
        self._sum_mode = sum_mode

    @property
    def sum_mode(self) -> str:
        """The ``math.sum`` machine this state runs (``"compensated"`` or ``"window"``)."""
        return self._sum_mode


_current: RunnerState | None = None
#: The process's own globals and shared-cache contents, snapshotted immediately
#: before the first state is ever installed and reinstated when the current
#: state is discarded: afterwards the process behaves as on v6.10.10, with no
#: swap ever having happened (ruling 2026-10-31).
_pre_swap: dict[tuple[types.ModuleType, str], Any] | None = None
_pre_swap_caches: list[dict] | None = None


def _rebind_registries() -> None:
    """Rebind ``drawing_snapshot._REGISTRIES`` to the live drawing registries.

    ``_REGISTRIES`` is an ALLCAPS tuple built at import from the *baseline*
    registries, so the scanner skips it; after a switch the live registries are
    other objects, and without this rebind a ``DrawingSnapshot`` saves and
    restores the empty originals — live drawings then pile up to the 500 cap
    (the proof's P7).
    """
    from pynecore.core import drawing_snapshot as ds
    ds._REGISTRIES = tuple(sys.modules["pynecore.lib." + n]._registry
                           for n in ("line", "label", "box", "table", "polyline", "linefill"))


def activate(state: RunnerState) -> None:
    """Install ``state``'s values, caches, root vectors and script module.

    Saves the outgoing state's current values first (its globals, its cache
    contents, its script module as it now sits in ``sys.modules``), so a state
    left and returned to finds its own progress. A no-op if ``state`` is
    already current. Between one ``activate`` and the next, only ``state``'s
    runner may step — that rule is what keeps co-resident runners bit-exact.
    """
    global _current, _pre_swap, _pre_swap_caches
    if _current is state:
        return
    if _current is not None:
        _current.vals = {(m, k): getattr(m, k) for (m, k) in _current.vals}
        _current.caches = [dict(c) for c in _CACHES]
        for n in _current.modules:
            _current.modules[n] = sys.modules.get(n)
    else:
        # The first install in this process: snapshot its own globals first, so
        # discarding the current state can put them back (see :func:`discard`).
        if _pre_swap is None:
            _pre_swap = {(m, k): getattr(m, k) for (m, k) in _TRACKED}
            _pre_swap_caches = [dict(c) for c in _CACHES]
    for (m, k), v in state.vals.items():
        setattr(m, k, v)
    for c, saved in zip(_CACHES, state.caches):
        c.clear()
        c.update(saved)
    for n, mod in state.modules.items():
        if mod is not None:
            sys.modules[n] = mod
    _current = state
    _rebind_registries()


def active_state() -> RunnerState | None:
    """The state whose values the module globals currently hold, if any."""
    return _current


def new_runner_state(*, sum_mode: str = "compensated") -> RunnerState:
    """A fresh state: baseline values, empty caches, no script, its own sum mode.

    :param sum_mode: One of ``rolling_sum.SUM_MODES`` (spec 9.2 E1).
    :raises ValueError: On any other mode (Task 2's message).
    """
    if sum_mode not in rolling_sum.SUM_MODES:
        raise ValueError(f"sum mode must be one of {rolling_sum.SUM_MODES}, got {sum_mode!r}")
    return RunnerState(sum_mode)


def create_runner(state: RunnerState, **script_runner_kwargs: Any) -> ScriptRunner:
    """Create a runner under ``state`` and record its script module there.

    Activates ``state`` first, so the runner's import hook and machines are
    created on the state's globals. If ``ScriptRunner`` raises, the state is
    discarded (never left holding a half-created runner) and the exception
    propagates (the proof's F1c).

    ``script_path`` must be among the kwargs (it names the ``sys.modules`` entry
    recorded for the script).
    """
    activate(state)
    try:
        runner = ScriptRunner(**script_runner_kwargs)
    except BaseException:
        discard(state)
        raise
    state.modules[script_module_name(Path(script_runner_kwargs["script_path"]))] = \
        runner.script_module
    return runner


def discard(state: RunnerState, gen: Generator | None = None) -> None:
    """Evict a state: close its generator under its own state, then drop it.

    A suspended generator must be closed HERE, under its own state: its ``finally``
    block resets whichever module globals are current, so closing it under
    another state would corrupt that one (the proof's F1b). Safe after an
    exception mid-step — the globals may hold the dead runner's partial state,
    and the next :func:`activate` overwrites every tracked name, so the only
    thing to guarantee is that nobody saves that state into another context:
    the dropped state's slots are cleared here. Afterwards
    :func:`active_state` is ``None`` when ``state`` was current, and the tracked
    module globals hold the baseline again — the values snapshotted just before
    the first state was ever installed — so ``rolling_sum.get_sum_mode()``
    reads ``"compensated"`` and a later plain runner in the same process
    behaves as on v6.10.10 (ruling 2026-10-31: the whole-suite run caught a
    discarded window-mode state leaving ``_sum_mode = "window"`` behind).
    """
    global _current
    if gen is not None:
        activate(state)
        try:
            gen.close()
        except BaseException:
            pass
    if _current is state:
        _current = None
        if _pre_swap is not None:
            # Restore the process's own globals and cache contents: with the
            # current state gone, no state's values may stay installed.
            for (m, k), v in _pre_swap.items():
                setattr(m, k, v)
            for c, saved in zip(_CACHES, _pre_swap_caches):
                c.clear()
                c.update(saved)
            _rebind_registries()
    for n, mod in list(state.modules.items()):
        if sys.modules.get(n) is mod:
            sys.modules.pop(n, None)
    state.modules.clear()
    state.vals.clear()
    state.caches.clear()


def tracked_names() -> tuple[str, ...]:
    """The tracked globals as sorted ``"<module>:<attr>"`` names (spec 13.1)."""
    return tuple(sorted(f"{m.__name__}:{k}" for m, k in _TRACKED))


def swap_sha() -> str:
    """The sha256 hex digest of this module's source bytes (spec 13.1)."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
