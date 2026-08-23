from __future__ import annotations

import re
from typing import TypeVar


_FORMULA_PREFIX_RE = re.compile(r"^[\s\x00-\x1f\x7f-\x9f]*[=+@-]")
T = TypeVar("T")


def is_formula_like_text(value: object) -> bool:
    """Return whether spreadsheet software could treat *value* as a formula."""

    return isinstance(value, str) and bool(_FORMULA_PREFIX_RE.match(value))


def csv_literal(value: T) -> T | str:
    """Neutralize formula-like CSV text while preserving its visible content."""

    if is_formula_like_text(value):
        return f"'{value}"
    return value


def csv_safe_dataframe(frame):
    """Return a copy suitable for CSV files that people may open in Excel."""

    return frame.apply(lambda column: column.map(csv_literal))


def force_openpyxl_literal(cell) -> None:
    """Force a formula-like openpyxl cell to be stored as literal text."""

    if is_formula_like_text(cell.value):
        value = cell.value
        cell.value = value
        cell.data_type = "s"


def set_openpyxl_literal_cell(worksheet, row: int, column: int, value: object):
    """Write a cell and prevent untrusted text from becoming a formula."""

    cell = worksheet.cell(row=row, column=column, value=value)
    force_openpyxl_literal(cell)
    return cell


def secure_openpyxl_worksheet(worksheet, *, min_row: int = 1) -> None:
    """Force formula-like values in an exported worksheet to literal strings."""

    for row in worksheet.iter_rows(min_row=min_row):
        for cell in row:
            force_openpyxl_literal(cell)
