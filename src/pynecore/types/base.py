class IntEnum(int):
    """
    IntEnum class that auto-increments values.
    """

    def __init_subclass__(cls, start: int = 0, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._counter = start  # Each subclass gets its own counter

    def __new__(cls):
        # Create new object with the current counter value
        value = cls._counter
        cls._counter += 1
        # noinspection PyTypeChecker
        return super().__new__(cls, value)


class StrLiteral(str):
    """
    StrLiteral class to store string literals.
    """


# A drawing is a reference type whose identity belongs to a module registry: the
# variable holds a handle, and every ``*.set_*`` call mutates the registered object.
# A field-wise clone carries a DUPLICATE vid (``vid`` is a normal init=True field),
# sits in no registry, never reaches the chart and aliases the original in the viz
# stream, where a linefill serializes its lines by vid. Copying one is only
# expressible through the namespace ``copy()``, which assigns a fresh vid and
# registers the clone.
#
# Measured on TradingView: mutating a drawing through a container copy changes the
# ORIGINAL, for ``matrix.copy()`` and ``array.copy()`` alike — containers share
# their drawing references rather than cloning them.
class Drawing:
    """
    Base of the chart-object types: line, label, box, table, linefill and polyline.

    Every field write bumps the object's ``_ver``: the viz journal's drain
    serializes only the drawings whose version moved since the last emission,
    so its cost follows what changed. The writes all come from the lib's
    creation and setter functions — Pine cannot touch a drawing's fields
    directly — so the version cannot miss a mutation.

    The call-site ``tag`` is a SLOT, deliberately NOT a dataclass field: it is
    host metadata (a viewer's restyle key), not part of the drawing's value, so
    the generic identity forms — anything that walks ``dataclasses.fields`` —
    must not carry it into a snapshot, a hash or a diff. The viz journal emits
    it explicitly for the host that needs it.
    """

    __slots__ = ('_ver', 'tag')

    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls)
        object.__setattr__(obj, '_ver', 0)
        object.__setattr__(obj, 'tag', -1)
        return obj

    def __setattr__(self, name: str, value) -> None:
        if name != '_ver':
            object.__setattr__(self, '_ver', self._ver + 1)
        object.__setattr__(self, name, value)

    def __deepcopy__(self, memo: dict) -> 'Drawing':
        """
        Return the drawing itself: a chart object has no deep copy.

        :param memo: Deepcopy memo, unused
        :return: This same object
        """
        return self


# Monotonic id counter for drawing objects (line/label/box/table/polyline/linefill).
# Single-threaded runner, so a plain module-level integer needs no locking.
_vid_counter = 0


def next_vid() -> int:
    """Return the next monotonically increasing drawing-object id."""
    global _vid_counter
    _vid_counter += 1
    return _vid_counter


def reset_vid_counter() -> None:
    """Reset the drawing-object id counter (new run / new script)."""
    global _vid_counter
    _vid_counter = 0
