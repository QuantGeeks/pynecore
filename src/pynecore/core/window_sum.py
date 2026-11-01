"""
The window re-sum machine of ``math.sum`` (QuantGeeks fork, spec 9.2 E1).

TradingView's ``math.sum`` / ``ta.sma`` values equal a plain re-sum of the window on
every bar of a 1-minute export we measured (41,301 of 41,301 bars for a 40-bar SMA;
the compensated accumulator matched 428, a running sum 661), so the fork offers this
machine as an opt-in alternative to :class:`pynecore.core.rolling_sum.SumMachine`:
the plain oldest-first ``sum()`` of the last ``length`` non-na values, recomputed
each bar. ``lib._math_stateful.sum`` chooses it for a call site only while
``pynecore.core.rolling_sum.get_sum_mode() == "window"``; the default mode stays
``"compensated"``, upstream's machine, unchanged.

Like ``SumMachine`` the whole state is one object, so a rollback is the
``__pyne_snapshot__`` / ``__pyne_restore__`` pair: the token is the stored values
and the capacity, and a restore puts them back exactly.
"""
from typing import Any

from ..types.na import na_float

__all__ = ['WindowSumMachine', 'window_sum_step']


class WindowSumMachine:
    """
    The re-summed-window machine of one ``math.sum`` call site.

    The window is na-compacted exactly like ``SumMachine``'s: an na bar returns na
    and is not stored, so the sum always covers the last ``length`` non-na values.
    ``cap`` grows to the largest length the site has seen so a later, larger length
    still finds its history (a series ``length`` is legal in Pine), and the machine
    keeps only the last ``cap`` values.
    """

    __slots__ = ("vals", "cap")

    def __init__(self) -> None:
        self.vals: list[float] = []
        self.cap: int = 0

    def step(self, source: Any, length: Any) -> float:
        """
        One ``math.sum`` call: store ``source`` (unless it is na) and return the
        plain sum of the last ``length`` non-na values, oldest first, or na while
        fewer are stored.

        :param source: The source value of this bar
        :param length: Length of the sum
        :return: The sliding sum of the series
        """
        length = int(length)
        # Representation-agnostic na test, as ``SumMachine.step`` uses it: an na
        # source is either an NA object or a native nan, and neither is stored.
        if not (source == source):
            return na_float
        self.cap = max(self.cap, length)
        self.vals.append(float(source))
        if len(self.vals) > self.cap:
            del self.vals[:len(self.vals) - self.cap]
        if len(self.vals) < length:
            return na_float
        return sum(self.vals[-length:])

    def __pyne_snapshot__(self) -> tuple[tuple[float, ...], int]:
        """
        Rollback token of the current state.

        :return: The stored values (oldest first) and the capacity.
        """
        return (tuple(self.vals), self.cap)

    def __pyne_restore__(self, token: tuple[tuple[float, ...], int]) -> None:
        """
        Roll the machine back to a :meth:`__pyne_snapshot__` token.

        :param token: A token of this machine.
        """
        self.vals = list(token[0])
        self.cap = token[1]


#: One machine step as a plain function of the machine, like
#: :data:`pynecore.core.rolling_sum.rolling_sum_step`: a method call on a state
#: slot is a callee the slot transform cannot resolve, and it would bind it at an
#: anchored call site on every call.
window_sum_step = WindowSumMachine.step
