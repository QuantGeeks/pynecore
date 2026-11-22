from __future__ import annotations
from typing import Any, TypeVar, Generic, Iterator, Callable, cast, overload

from types import ModuleType

from ..types.na import NA, na_float

__all__ = ['SeriesImpl', 'BufferGrowthNeeded', 'inline_series']

T = TypeVar('T')


class BufferGrowthNeeded(RuntimeError):
    """A historical read a larger buffer could serve — the runner restarts.

    TradingView (the RE10143 page, "The requested historical offset is beyond
    the historical buffer's limit"): the declaration, ``max_bars_back()`` and
    the engine default set a buffer's INITIAL size, and "if the script
    requests data from beyond an initial buffer's limit while executing
    across other historical bars, the system increases that buffer's size and
    restarts the script. This process repeats as necessary until the system
    reaches the restart limit". After the script loads the system "does not
    continue to resize historical buffers", so a realtime read beyond the
    limit is the error itself.

    :attr:`needed` is the offset that must stay addressable (the runner's
    learned floor rises to it before the restart), :attr:`limit` the limit
    that failed. The message is TradingView's RE10143 text, so a growth that
    cannot be served surfaces as that error unchanged.
    """

    def __init__(self, needed: int, limit: int):
        super().__init__(f"The requested historical offset ({needed}) is beyond "
                         f"the historical buffer's limit ({limit})")
        self.needed = needed
        self.limit = limit


def _realtime() -> bool:
    """Whether the executing bar is a realtime bar (no buffer growth there)."""
    bs = getattr(SeriesImpl._lib, 'barstate', None)
    return bool(getattr(bs, 'isrealtime', False))

# Interned na sentinel of untyped series (element type unknown at transform
# time). The ``not (x == x)`` guards treat it and the native nan as the same na.
# The cast is needed because the NA stub's __new__ deliberately types as T (so
# ``NA(X)`` flows anywhere an ``X`` is expected), which here would be a TypeVar.
_NA_UNTYPED: NA = cast(NA, NA(T))


class SeriesImpl(Generic[T]):
    """
    A dynamic circular buffer that behaves similarly to Pine Script's "Series".
    Every docstring and comment is in English, as requested.

    Note: max_bars_back means the maximum number of older bars that can be indexed.
    Therefore, the actual buffer capacity is (max_bars_back + 1).
    """

    __slots__ = ('_buffer',
                 '_max_bars_back', '_max_bars_back_set',
                 '_capacity', '_write_pos', '_size',
                 '_last_bar_index', '_na', '_compacted', '_as_float',
                 '_hard_cap', '_overflowed')

    # MEASURED (probes m601/m602, BINANCE:BTCUSDT 30m): TradingView serves 5000 bars of
    # history for EVERY series — builtin, user-defined and ``ta.*`` output alike, under
    # both constant and dynamic subscripts — without the script declaring anything. A
    # smaller default silently returns na for deeper reads instead of the value TV shows.
    DEFAULT_MAX_BARS_BACK = 5000  # This can be set globally by indicator or strategy commands
    MAXIMUM_MAX_BARS_BACK = 5000  # This is the maximum allowed value
    # TradingView's Limitations page: "some built-in series like open, high, low, close
    # and time have larger historical buffers that can reference up to 10,000 bars" —
    # the ceiling a growth request on those series may reach.
    DEEP_BUFFER_MAX_BARS_BACK = 10000

    _lib: ModuleType = None  # Placeholder for the lib module

    @classmethod
    def default_max_bars_back(cls, explicit: int | None = None,
                              hard_cap: int | None = None) -> int:
        """The buffer limit a new series starts with.

        Resolution order: the series' own explicit value (a per-variable
        declaration), the script's ``indicator`` / ``strategy`` declaration
        (``max_bars_back=`` sizes every series), the host's engine default
        (``new_runner_state(max_bars_back_default=...)``, bounding series
        memory for hosts whose scripts index shallowly), and finally the
        measured TradingView default above. Whatever the chain resolves to is
        only the INITIAL size (TradingView, RE10143): a read the runner grew
        the buffers for (``lib._max_bars_back_learned``) floors it, clamped by
        ``hard_cap`` — 5000 for a general series, 10000 for the
        open/high/low/close/time builtins.

        :param explicit: The series' explicitly declared limit, if any
        :param hard_cap: The ceiling this series' buffer may grow to
        :raises ValueError: If the script declaration exceeds the maximum
        """
        if explicit:
            return explicit
        lib = cls._lib
        if lib is None:
            from .. import lib
            cls._lib = lib
        # getattr, not attribute access: the module-level inline series is
        # constructed while ``pynecore.lib`` is still initializing (a circular
        # import through types), when neither attribute exists yet — the class
        # default is the right answer there anyway.
        script = getattr(lib, "_script", None)
        declared = script.max_bars_back if script is not None else 0
        if declared:
            if declared > cls.MAXIMUM_MAX_BARS_BACK:
                raise ValueError(
                    f"The max_bars_back cannot exceed {cls.MAXIMUM_MAX_BARS_BACK}!")
            resolved = declared
        else:
            default = getattr(lib, "_max_bars_back_default", 0)
            resolved = default if default else cls.DEFAULT_MAX_BARS_BACK
        # The floor a growth restart learned: the series constructed after it
        # must keep the history that triggered the growth, or the replay hits
        # the same request again. Still an INITIAL size in TradingView's
        # terms — a runtime ``max_bars_back`` call can shrink below it again.
        learned = getattr(lib, "_max_bars_back_learned", 0)
        if learned > resolved:
            resolved = learned
        cap = hard_cap if hard_cap is not None else cls.MAXIMUM_MAX_BARS_BACK
        if resolved > cap:
            resolved = cap
        return resolved

    # noinspection PyMissingConstructor
    def __init__(self, max_bars_back: int | None = None, na_value: T | None = None,
                 compacted: bool = False, as_float: bool = False,
                 hard_cap: int | None = None):
        """
        :param max_bars_back: Optional initial capacity for historical lookback.
                              If not provided, :meth:`default_max_bars_back`
                              resolves the script declaration / engine default.
                              The actual buffer capacity will be (max_bars_back + 1).
        :param na_value: The na sentinel returned for out-of-range reads.
                         Numeric (float and int) series pass the native nan
                         here so a warmup / out-of-history read behaves exactly
                         like every other numeric na; untyped series keep the
                         interned NA object.
        :param compacted: History counts stored values instead of bars: a bar with
                          no :meth:`add` is simply absent rather than repeating the
                          previous value. Set for the rolling windows of the
                          ``@pyne lib`` machines (``math.sum``, the ``ta.*``
                          averages), which drop na bars on purpose so ``src[k]`` is
                          the k-th most recent non-na value — the window
                          TradingView's native builtins keep.
        :param as_float: Store every value as a native float. Set for ``Series[int]``:
                         a Pine int is a double at runtime, so an int series must
                         not hand back the Python int a literal or a counter put
                         in; a non-number (an na object) is stored as the nan.
        :param hard_cap: The ceiling this series' buffer may grow to through a
                         restart (5000 in general; the open/high/low/close/time
                         builtins pass :attr:`DEEP_BUFFER_MAX_BARS_BACK`).
        """
        # Importing the lib module here to avoid circular imports
        if not SeriesImpl._lib:
            from .. import lib
            SeriesImpl._lib = lib

        self._na: T | NA[T] = _NA_UNTYPED if na_value is None else na_value
        self._compacted = compacted
        self._as_float = as_float
        self._hard_cap = hard_cap if hard_cap is not None else self.MAXIMUM_MAX_BARS_BACK

        self._max_bars_back = self.default_max_bars_back(max_bars_back, self._hard_cap)
        self._max_bars_back_set = max_bars_back or 0
        # Internal capacity is max_bars_back + 1 (for current candle + historical bars)
        self._capacity = self._max_bars_back + 1
        # Whether the ring has overwritten the oldest value at least once: the
        # history below the buffer is gone, so a read past the stored size can
        # never be filled by waiting — it needs a bigger buffer from bar 0 (a
        # growth restart), never a silent na. Survives a resize, which keeps
        # only what the old capacity still held.
        self._overflowed = False

        # Grown by append until it reaches ``_capacity``, then written circularly.
        # Allocating the full capacity up front would cost every series the deepest
        # lookback TradingView allows no matter how few bars the run actually has;
        # while the buffer is filling ``_write_pos == _size == len(_buffer)``, so the
        # append lands exactly where the indexed store into a pre-allocated list did.
        self._buffer: list[T | NA[T]] = []

        # The next logical write position in a circular manner.
        self._write_pos = 0

        # The current number of valid elements in the buffer (<= self._capacity).
        self._size = 0

        # The last bar index that was accessed
        self._last_bar_index = -1

    @property
    def max_bars_back(self) -> int:
        """
        Returns the current max_bars_back, i.e. how many historical bars can be indexed.
        """
        return self._max_bars_back

    @max_bars_back.setter
    def max_bars_back(self, new_max_bars_back: int) -> None:
        """
        Resizes the circular buffer capacity to (new_value + 1).
        - If increased, old items are preserved (up to the old _size), and
          the buffer is linearized.
        - If decreased, only the most recent 'new_value + 1' items are kept.

        :param new_max_bars_back: The new 'max_bars_back' value.
        :raises ValueError: If new_value <= 0.
        """
        if new_max_bars_back <= 0:
            raise ValueError("The max_bars_back must be a positive integer!")
        if new_max_bars_back > self._hard_cap:
            raise ValueError(f"The max_bars_back cannot exceed {self._hard_cap}!")

        if new_max_bars_back == self._max_bars_back:
            return  # No change

        old_size = self._size
        old_write_pos = self._write_pos

        new_capacity = new_max_bars_back + 1
        if new_capacity > old_size == old_write_pos:
            # The buffer is not yet full, and the write position is at the end.
            # We can just modify the max_bars_back and capacity, and extend the buffer
            self._max_bars_back = new_max_bars_back
            self._max_bars_back_set = new_max_bars_back
            self._capacity = new_capacity
            return

        old_buffer = self._buffer
        old_capacity = self._capacity

        # Number of items to keep: either all old items or new_capacity, whichever is smaller.
        items_to_keep = min(old_size, new_capacity)

        # Only the kept items are materialised; the rest of the capacity is filled by
        # later appends, exactly as on a freshly constructed buffer.
        new_buffer: list[T | NA[T]] = cast('list[T | NA[T]]', [None] * items_to_keep)

        if items_to_keep > 0 and old_buffer:
            # The newest item is at (old_write_pos - 1) in a circular manner.
            # We'll copy the most recent 'items_to_keep' from the old buffer in linear order.
            start_idx = (old_write_pos - items_to_keep) % old_capacity

            for i in range(items_to_keep):
                src_idx = (start_idx + i) % old_capacity
                new_buffer[i] = old_buffer[src_idx]

        # Update references
        self._buffer = new_buffer
        self._max_bars_back = new_max_bars_back
        self._max_bars_back_set = new_max_bars_back
        self._capacity = new_capacity
        self._size = items_to_keep
        self._write_pos = items_to_keep  # The next free slot is after the last copied item

    def add(self, value: T | NA[T]) -> T | NA[T]:
        """
        Adds a new candle (data point) to the buffer.
        - If the buffer is not yet at full capacity (size < capacity), it appends the new value.
        - Otherwise, it overwrites the oldest data in a circular manner.
        :param value: The new data to be added.
        :return: The same value that was added (for chaining or inline usage).
        """
        if self._as_float:
            value = float(value) if value == value else na_float  # type: ignore[assignment]

        # Read the module attribute once: this runs for every series assignment
        # on every bar, and the three reads it replaces cannot see a different
        # value anyway — nothing between them advances the bar.
        bar_index = SeriesImpl._lib.bar_index

        # Set data instead of adding a new one if the bar index is the same
        last_bar_index = self._last_bar_index
        if last_bar_index == bar_index:
            return self.set(value)

        # A series that lives inside a conditionally evaluated branch (a stateful
        # function called from one arm of a ternary, a body that only some bars
        # enter) is not updated on the bars the branch is skipped. TradingView
        # still advances such a history by one slot per BAR and repeats the last
        # value it did see, so ``x[k]`` keeps counting bars rather than calls
        # (measured: BINANCE:BTCUSDT 30m, a fractal test called only when its
        # sibling test is false matches the forward-filled model on every one of
        # 23949 bars, while the compacted model misses 769). ``_size`` gates the
        # fill: before the first value there is nothing to repeat, and the reads
        # are na there either way.
        missed = bar_index - last_bar_index - 1
        if missed > 0 and self._size > 0 and not self._compacted:
            fill = self._buffer[self._write_pos - 1]
            # Filling more than the whole buffer would only overwrite itself
            for _ in range(int(missed) if missed < self._capacity else self._capacity):
                self._push(fill)

        # _push, inlined verbatim: this is THE per-bar write of every series in
        # the script, and its call frame costs more than the body. Kept a literal
        # copy so a drift between the two is visible at a glance — a wrap one of
        # them makes and the other does not corrupts a full buffer silently.
        if self._size < self._capacity:
            self._buffer.append(value)
            self._size += 1
            self._write_pos += 1
        else:
            pos = self._write_pos
            if pos >= self._capacity:
                pos = 0
                self._write_pos = 1
            else:
                self._write_pos += 1
            self._buffer[pos] = value
            self._overflowed = True

        # Store the last bar index to prevent adding more than one value per bar
        self._last_bar_index = bar_index

        return value

    def _push(self, value: T | NA[T]) -> None:
        """
        Append one value to the circular buffer, growing it until it is full and
        overwriting the oldest entry afterwards.
        """
        if self._size < self._capacity:
            # The buffer is not yet full - grow it by one slot
            self._buffer.append(value)
            self._size += 1
            self._write_pos += 1
        else:
            # The buffer is full: overwrite in circular fashion
            pos = self._write_pos
            if pos >= self._capacity:
                pos = 0
                self._write_pos = 1
            else:
                self._write_pos += 1
            self._buffer[pos] = value
            self._overflowed = True

    def set(self, value: T | NA[T]) -> T | NA[T]:
        """
        Overwrites the most recently added (current) candle value.
        If there is no data yet, returns na.
        :param value: The new value for the current candle.
        :return: The value that was set, or na if buffer is empty.
        """
        if self._size == 0:
            return self._na
        if self._as_float:
            value = float(value) if value == value else na_float  # type: ignore[assignment]

        pos = self._write_pos - 1
        if pos < 0:
            pos += self._capacity
        self._buffer[pos] = value
        return value

    def _snapshot(self) -> tuple[list[T | NA[T]], int, int, int, int, int, int, bool]:
        """Capture the full buffer state for a rollback baseline.

        Used by the live ``request.security_lower_tf`` LTF baseline to roll a
        series back when a reordered feed forces a replay that re-runs an
        *earlier* ``bar_index`` after a later one already ran (see
        :class:`~pynecore.core.live_ltf_collector.LiveLtfCollector`). A cursor-only
        snapshot is not enough: at capacity a stray :meth:`add` overwrites the
        oldest element circularly, which the cursor alone cannot reconstruct — so
        the buffer contents are copied too. Cheap at live cadence (one copy per
        confirmed intrabar), never used on the warmup forward-only path.

        :return: An opaque tuple consumed only by :meth:`_restore`.
        """
        return (self._buffer.copy(), self._size, self._write_pos, self._last_bar_index,
                self._max_bars_back, self._max_bars_back_set, self._capacity,
                self._overflowed)

    def _restore(self, snapshot: tuple[list[T | NA[T]], int, int, int, int, int, int, bool]) -> None:
        """Restore the buffer state captured by :meth:`_snapshot` (in place).

        The same snapshot may be restored repeatedly (one save, many replay
        re-runs), so the saved buffer is copied back rather than aliased.

        :param snapshot: A value returned by :meth:`_snapshot`.
        """
        (buffer, self._size, self._write_pos, self._last_bar_index,
         self._max_bars_back, self._max_bars_back_set, self._capacity,
         self._overflowed) = snapshot
        self._buffer = buffer.copy()

    def _restore_bar(self, snapshot: tuple[list[T | NA[T]], int, int, int, int, int, int, bool]) -> None:
        """Same-bar rollback to a :meth:`_snapshot` baseline, O(changed slots).

        The loop-site rollback (``instance_state.__loop_state__``) restores a
        builtin machine's windows once per loop ITERATION and the child-subtree
        rollback (``instance_state._restore_vector``) once per discarded
        re-execution (a calc_on_order_fills fill, a live intra-bar tick, a
        ``request.security`` child's developing re-tick), so the full-copy
        :meth:`_restore` would dominate the whole run. Between the bar-start
        snapshot and a same-bar restore the buffer can only have changed in a
        few recognizable ways: nothing structural (at most the newest slot was
        SET-rewritten), appended tail elements (filling-mode adds, gap fills),
        or the single ring overwrite of an at-capacity add. Each is undone in
        place; any shape this cannot prove (a capacity restructure, a
        stale-gap advance that wrapped into an overwrite) falls back to the
        full restore — the snapshot carries the whole buffer precisely so the
        fallback is always available.

        :param snapshot: A value returned by :meth:`_snapshot`.
        """
        buffer, size, write_pos, last_bar, mbb, mbb_set, cap, overflowed = snapshot
        if self._capacity == cap and self._max_bars_back == mbb \
                and self._max_bars_back_set == mbb_set:
            own = self._buffer
            # Every push comes from an :meth:`add` that advanced the bar (a
            # same-bar add degrades to a set, and the gap fill pushes at most one
            # element per skipped bar), so the bars elapsed since the snapshot
            # bound the number of pushes. Without that bound the cursors alone
            # cannot tell one ring overwrite from a full lap of them: after
            # exactly ``cap`` pushes ``_write_pos`` is back where it started.
            bars = self._last_bar_index - last_bar
            if bars == 0 and self._size == size and self._write_pos == write_pos \
                    and len(own) == len(buffer):
                if size:  # only the newest slot could have been rewritten
                    pos = write_pos - 1
                    own[pos] = buffer[pos]
                return
            if size < cap and bars <= cap - size and self._size == len(own) \
                    and size < self._size <= cap and self._write_pos == self._size:
                del own[size:]  # appended tail (adds and gap fills)
                if size:  # a set before the first push rewrote the newest slot
                    own[size - 1] = buffer[size - 1]
                self._size, self._write_pos, self._last_bar_index = size, write_pos, last_bar
                self._overflowed = overflowed  # the tail never wrapped
                return
            if bars == 1 and size == cap and self._size == cap \
                    and self._write_pos == write_pos % cap + 1:
                pos = write_pos % cap  # the single at-capacity ring overwrite
                own[pos] = buffer[pos]
                pos = write_pos - 1  # and a set that preceded it
                own[pos] = buffer[pos]
                self._write_pos, self._last_bar_index = write_pos, last_bar
                self._overflowed = overflowed  # undo the overwrite's flag
                return
        self._restore(snapshot)

    @overload
    def __getitem__(self, key: int) -> T | NA[T]:
        ...

    @overload
    def __getitem__(self, key: slice) -> ReadOnlySeriesView[T]:
        ...

    def __getitem__(self, key: Any) -> T | NA[T] | ReadOnlySeriesView[T]:
        """
        Get item(s) using Pine indexing with slice support.

        Pine semantics: subscripting with `na` returns the current bar's value
        (offset 0) — TradingView's history-referencing operator treats an `na`
        offset as 0. An offset beyond the buffer's limit raises TradingView's
        runtime error (RE10143) instead of silently returning a wrong value: a
        read that deep can never be served, whatever the bar count. An
        out-of-range offset within the limit (negative = forward of the current
        bar, positive >= size = before available history) returns `na` rather
        than raising. A fractional offset is truncated: the subscript is a
        consumer slot of a Pine int, which is a double at runtime.

        :param key: Number offset, NA, or slice
        :return: Single value for a number offset, ReadOnlySeriesView for slice
        :raises TypeError: If key is not a number, NA, or slice
        :raises RuntimeError: If the offset is beyond the buffer's limit
        """
        # One conversion is the whole hot loop: a Pine int offset is a float as
        # often as a Python int (loop counters, bar_index arithmetic), and
        # ``int()`` takes both in one C call where an isinstance chain would
        # walk two or three checks and a recursive call for the float form.
        try:
            offset = int(key)
        except (TypeError, ValueError):
            if isinstance(key, slice):
                return self._slice(key)
            # Pine: series[na] -> series[0] (an na offset is treated as the
            # current bar); the NA object and a nan both land here
            if isinstance(key, NA) or key != key:
                offset = 0
            else:
                raise TypeError("Series indices must be numbers or slices")  # noqa
        # Beyond the buffer's limit TradingView's runtime is what answers, and
        # HOW depends on the bar (RE10143's manual): on a historical bar the
        # runtime grows the buffer and restarts the script — a growth request
        # the runner serves, up to this series' hard cap; on a realtime bar
        # (and past the cap) it is the RE10143 error itself, never a silent na.
        if offset > self._max_bars_back:
            if offset <= self._hard_cap and not _realtime():
                raise BufferGrowthNeeded(offset, self._max_bars_back)
            raise RuntimeError(
                f"The requested historical offset ({offset}) is beyond the "
                f"historical buffer's limit ({self._max_bars_back})")
        # Pine: out-of-range subscript -> na (covers both negative and
        # positive past-end indices) — EXCEPT when the ring has already
        # discarded the history the read needs: the value is unknowable at
        # this buffer size (a resize kept only what the old capacity held), so
        # it grows (historical) or errors (realtime) instead of a silent na.
        if offset < 0:
            return self._na
        if offset >= self._size:
            if self._overflowed:
                if not _realtime():
                    raise BufferGrowthNeeded(offset, self._max_bars_back)
                raise RuntimeError(
                    f"The requested historical offset ({offset}) is beyond the "
                    f"historical buffer's limit ({self._max_bars_back})")
            return self._na
        pos = self._write_pos - 1 - offset
        if pos < 0:
            pos += self._capacity
        return self._buffer[pos]

    def _slice(self, key: slice) -> ReadOnlySeriesView[T]:
        """The read-only view a slice subscript hands back."""
        # Handle slice notation
        start = 0 if key.start is None else key.start
        stop = self._size if key.stop is None else key.stop

        if start < 0 or stop < 0:
            raise IndexError("Negative indices not supported in slice!")

        if key.step is not None and key.step != 1:
            raise ValueError("Step value not supported in slice!")

        if stop > self._size:
            # The window consumers' slices are guarded to stay within the
            # stored history while the buffer never wrapped; past that point
            # the ring has discarded what the walk needs, which is a growth
            # request (historical) or the RE10143 error — the raw IndexError
            # below stays the invariant for a genuinely unguarded slice.
            if self._overflowed:
                if not _realtime():
                    raise BufferGrowthNeeded(stop, self._max_bars_back)
                raise RuntimeError(
                    f"The requested historical offset ({stop}) is beyond the "
                    f"historical buffer's limit ({self._max_bars_back})")
            raise IndexError("Slice stop index out of range!")

        # Ensure start <= stop
        if start > stop:
            start = stop

        # Unsubscripted on purpose: the subscripted form routes construction
        # through ``typing._GenericAlias.__call__``, which costs ~290ns per
        # slice and buys nothing here -- it can only attach ``__orig_class__``,
        # which a ``__slots__`` class rejects anyway. ``T`` still binds from
        # the ``buffer`` argument, so the inferred type is unchanged.
        return ReadOnlySeriesView(
            self._buffer,
            self._capacity,
            self._write_pos,
            self._size,
            start,
            stop
        )

    def __len__(self) -> int:
        """
        Returns the number of valid data points in the buffer (<= capacity).
        """
        return self._size

    def __iter__(self) -> Iterator[T | NA[T]]:
        """
        Iterate valid items from newest to oldest (Pine index order).

        Without an explicit __iter__, ``iter(series)`` would fall back to the
        sequence protocol, and since ``__getitem__`` returns na for every
        out-of-range index (never IndexError), that iteration never terminates.
        """
        for i in range(self._size):
            pos = self._write_pos - 1 - i
            if pos < 0:
                pos += self._capacity
            yield self._buffer[pos]


class ReadOnlySeriesView(Generic[T]):
    """
    A read-only view for a circular buffer slice that follows Pine-like indexing.
    Supports positive slice notation [start:stop] where start and stop refer to
    bar indices from the most recent bar.
    """
    __slots__ = ('_buffer', '_capacity', '_write_pos', '_size', '_start', '_stop')

    def __init__(self, buffer: list[T | NA[T]], capacity: int, write_pos: int, size: int,
                 start: int, stop: int) -> None:
        """
        Initialize the view.

        :param buffer: The source buffer
        :param capacity: The capacity of the buffer
        :param write_pos: The current write position
        :param size: The number of valid items
        :param start: Start index (inclusive)
        :param stop: Stop index (exclusive)
        """
        self._buffer = buffer
        self._capacity = capacity
        self._write_pos = write_pos
        self._size = size
        self._start = start
        self._stop = min(stop, size)

    def __getitem__(self, idx: int | float) -> T | NA[T]:
        """Get item using Pine indexing (a fractional offset is truncated)"""
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            raise TypeError("Only number indexing is supported") from None  # noqa
        if idx < 0:
            raise IndexError("Negative indices not supported")
        if idx >= len(self):
            raise IndexError("Index out of range")

        actual_idx = idx + self._start
        pos = self._write_pos - 1 - actual_idx
        if pos < 0:
            pos += self._capacity
        return self._buffer[pos]

    def __len__(self) -> int:
        """Get length of the view"""
        return self._stop - self._start

    def __iter__(self) -> Iterator[T | NA[T]]:
        """Iterate through items from newest to oldest"""
        for i in range(self._start, self._stop):
            pos = self._write_pos - 1 - i
            if pos < 0:
                pos += self._capacity
            yield self._buffer[pos]

    @property
    def oldest(self) -> list[T | NA[T]]:
        """
        The viewed values as a plain list ordered oldest to newest.

        :return: The values of the view, oldest first
        """
        # Hot-loop helper: window consumers (``ta.wma``, ``ta.linreg``) walk the
        # whole slice on every bar, where per-element ``__getitem__`` calls are
        # the dominant cost; handing the window over as at most two native list
        # slices removes that overhead entirely.
        # A property rather than a method because the window consumers reach it
        # through an isolated call site: a ``<slice>.method()`` callee is a fresh
        # bound object every bar, so the transformer's anchor guard never hits --
        # every bar pays a rebind, and the emitted form constructs the view object
        # a second time just to re-check identity. (The call stays outside that
        # guard, so the list below was built once either way.) An attribute read
        # carries no call site at all.
        # Slice with an explicit upper bound everywhere: the wrap branches index
        # relative to ``_capacity``, which the still-growing buffer has not reached
        # yet — they are only taken once it has, and an open-ended slice would tie
        # the result to the physical length instead of the logical one.
        cap = self._capacity
        lo = self._write_pos - self._stop
        hi = self._write_pos - self._start
        if lo >= 0:
            return self._buffer[lo:hi]
        if hi <= 0:
            return self._buffer[lo + cap:hi + cap]
        return self._buffer[lo + cap:cap] + self._buffer[:hi]

    def __repr__(self) -> str:
        """Get string representation"""
        return f"ReadOnlySeriesView({list(self)})"


def _inline_series_instance(_pin: str | None = None,
                            _vector: tuple | None = None) -> Callable[..., Any]:
    """One ``inline_series`` instance: a closure over its own series buffer.

    The slot transform routes ``inline_series`` call sites on the uniform
    path, so ``__bind_any__`` anchors one of these per call site (and one per
    iteration at loop sites) through the ``__pyne_bind__`` factory — that is
    what keeps two ``expr[n]`` rewrites in one scope independent (issue #61).

    :param _pin: The call site's overload pin, part of the factory protocol.
        There is one implementation here, so there is nothing to select.
    :param _vector: The call site's instance vector, part of the factory
        protocol. The buffer is the whole instance, so there is nothing to configure.
    :return: The bound instance with the public ``inline_series`` signature.
    """
    series: SeriesImpl = SeriesImpl()

    def bound(value: T, idx: int) -> T:
        series.add(value)
        # The read is typed with the na the plain-T view drops; pyright needs the cast
        # noinspection PyUnnecessaryCast
        return cast(T, series[idx])

    # The whole instance state is this one buffer, and it lives in a closure
    # cell that the generic child-slot walker cannot reach. Publishing it lets
    # ``RootChildSnapshot`` roll the buffer back instead of dropping the
    # instance: a dropped ``inline_series`` re-binds EMPTY, so every ``expr[n]``
    # with n >= 1 reads na for the rest of the run.
    setattr(bound, '__pyne_series__', series)
    return bound


_inline_series_shared: SeriesImpl = SeriesImpl()


def inline_series(value: T, idx: int) -> T:
    """
    Inline series creation
    It is mainly for compiled codes

    Calling it directly (no anchor — non-transformed code) uses one shared
    module-lifetime buffer, the same semantics the legacy module-global
    series gave such calls; anchored call sites get independent buffers from
    ``__pyne_bind__``.

    :param value: The value to store
    :param idx: The index, 0 is the last, 1 is the second last and so on
    :return:
    """
    _inline_series_shared.add(value)
    # See the bound instance above: pyright needs the cast
    # noinspection PyUnnecessaryCast
    return cast(T, _inline_series_shared[idx])


setattr(inline_series, '__pyne_bind__', _inline_series_instance)
