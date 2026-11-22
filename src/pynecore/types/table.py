from typing import Optional, Dict, Tuple
from dataclasses import dataclass, field

from ..lib import (color as _color, position as _position, size as _size, text as _text, font as _font)
from .base import Drawing


@dataclass(slots=True)
class TableCell:
    """Represents a single cell in a table.

    A cell serializes as part of its table, and its writes ride the table's
    journal version: every field write bumps ``_owner._ver`` (the owning
    table adopts the cell when it stores it — see ``Table.get_cell``).
    """
    text: str = ""
    width: int | float = 0
    height: int | float = 0
    text_color: Optional[_color.Color] = None
    text_halign: Optional[_text.AlignEnum] = None
    text_valign: Optional[_text.AlignEnum] = None
    text_size: int | str = _size.normal
    bgcolor: Optional[_color.Color] = None
    tooltip: str = ""
    text_font_family: Optional[_font.FontFamilyEnum] = None
    text_formatting: Optional[_text.FormatEnum] = None

    # Merge information
    is_merged: bool = False
    merge_start_col: int = -1
    merge_start_row: int = -1
    merge_end_col: int = -1
    merge_end_row: int = -1

    # Stable id of the script call site that created the cell
    tag: int = -1

    # The table this cell lives in, set on adoption; a write marks it dirty
    _owner: 'Table' = field(default=None, init=False, repr=False, compare=False)

    def __setattr__(self, name: str, value) -> None:
        if name != '_owner':
            # ``_owner`` is init=False: it is unset during the dataclass
            # ``__init__`` (the cell is not adopted yet, nothing to bump)
            owner = getattr(self, '_owner', None)
            if owner is not None:
                object.__setattr__(owner, '_ver', owner._ver + 1)
        object.__setattr__(self, name, value)


@dataclass(slots=True, eq=False)
class Table(Drawing):
    # Required parameters
    position: _position.Position  # Position of the table
    columns: int  # Number of columns
    rows: int  # Number of rows

    # Optional parameters with defaults
    bgcolor: Optional[_color.Color] = None
    frame_color: Optional[_color.Color] = None
    frame_width: int = 0
    border_color: Optional[_color.Color] = None
    border_width: int = 0
    force_overlay: bool = False

    # Cell data storage - using (column, row) as key
    cells: Dict[Tuple[int, int], TableCell] = field(default_factory=dict)

    # Stable id of the script call site that created the drawing
    tag: int = -1

    vid: int = -1

    def get_cell(self, column: int, row: int) -> TableCell:
        """Get or create a cell at the specified position."""
        if (column, row) not in self.cells:
            self.cells[(column, row)] = TableCell()
            # A new cell changes the table's serialized state; adoption lets
            # the cell's own writes bump the table's version too
            object.__setattr__(self, '_ver', self._ver + 1)
        cell = self.cells[(column, row)]
        if cell._owner is not self:
            cell._owner = self
        return cell

    def set_cell(self, column: int, row: int, cell: TableCell) -> None:
        """Set a cell at the specified position."""
        self.cells[(column, row)] = cell
        cell._owner = self
        object.__setattr__(self, '_ver', self._ver + 1)

    def clear_cell(self, column: int, row: int) -> None:
        """Clear a cell at the specified position."""
        if (column, row) in self.cells:
            del self.cells[(column, row)]
            object.__setattr__(self, '_ver', self._ver + 1)

    def clear_cells(self, start_column: int, start_row: int, end_column: int, end_row: int) -> None:
        """Clear a range of cells."""
        for col in range(start_column, end_column + 1):
            for row in range(start_row, end_row + 1):
                self.clear_cell(col, row)

    def merge_cells(self, start_column: int, start_row: int, end_column: int, end_row: int) -> None:
        """Merge a range of cells."""
        # Create or get the main cell (top-left)
        main_cell = self.get_cell(start_column, start_row)

        # Mark cells in the range as merged
        for col in range(start_column, end_column + 1):
            for row in range(start_row, end_row + 1):
                cell = self.get_cell(col, row)
                cell.is_merged = True
                cell.merge_start_col = start_column
                cell.merge_start_row = start_row
                cell.merge_end_col = end_column
                cell.merge_end_row = end_row

        # The main cell retains its content, others are effectively hidden
        main_cell.is_merged = True
