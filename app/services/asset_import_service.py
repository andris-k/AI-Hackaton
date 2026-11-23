"""Reading fixed assets from a CSV file.

The file is checked in full before anything is saved: ``parse_assets_csv``
returns every row with its errors and warnings, plus the categories and
locations that would be created. Saving is done by ``db.import_fixed_assets``
in one transaction, and only when no row has an error.

Accepted input, so that files saved from Excel work as they are:

* UTF-8, with or without a byte order mark ("CSV UTF-8" in Excel);
* comma, semicolon or tab separated;
* headers in any case, with spaces or underscores ("Initial value", "initial_value");
* numbers with a decimal point or comma, and spaces between thousands ("1 234,56");
* dates as YYYY-MM-DD or DD.MM.YYYY.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_TEXT_LEN = 100

# Canonical column -> accepted header spellings (after normalising).
_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "asset", "asset_name"),
    "category": ("category", "category_name"),
    "location": ("location", "location_name"),
    "quantity": ("quantity", "qty"),
    "initial_value": ("initial_value", "value", "initialvalue"),
    "responsible_person": ("responsible_person", "responsible", "responsibleperson"),
    "registration_date": ("registration_date", "registered", "registrationdate", "date"),
}
REQUIRED_COLUMNS = ("name", "category", "initial_value", "responsible_person", "registration_date")
OPTIONAL_COLUMNS = ("location", "quantity")
TEMPLATE_HEADER = ("name", "category", "location", "quantity", "initial_value", "responsible_person", "registration_date")
TEMPLATE_ROWS = (
    ("Dell Latitude 7440", "IT equipment", "Head office", "1", "1249.00", "Anna Ozola", "2026-01-15"),
    ("Office chair", "Furniture", "Warehouse A", "12", "89.90", "Jānis Bērziņš", "2025-09-01"),
)


class ImportFileError(ValueError):
    """The file as a whole cannot be read (encoding, size, missing columns)."""


@dataclass
class ImportRow:
    line: int
    name: str = ""
    category: str = ""
    location: str = ""
    quantity: int = 1
    initial_value: float = 0.0
    responsible_person: str = ""
    registration_date: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImportPreview:
    rows: list[ImportRow]
    new_categories: list[str]
    new_locations: list[str]
    ignored_columns: list[str]

    @property
    def error_count(self) -> int:
        return sum(1 for row in self.rows if row.errors)

    @property
    def warning_count(self) -> int:
        return sum(1 for row in self.rows if row.warnings)

    @property
    def can_import(self) -> bool:
        return bool(self.rows) and self.error_count == 0


def template_csv() -> str:
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(TEMPLATE_HEADER)
    writer.writerows(TEMPLATE_ROWS)
    return output.getvalue()


def _normalise_header(text: str) -> str:
    return re.sub(r"[\s\-]+", "_", text.strip().lower())


def _decode(data: bytes) -> str:
    if len(data) > MAX_FILE_BYTES:
        raise ImportFileError(f"The file is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB. Split it into smaller files.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ImportFileError(
            "The file is not in UTF-8. In Excel, use File › Save As › \"CSV UTF-8 (Comma delimited)\" and upload that file."
        ) from None


def _dialect(text: str) -> type[csv.Dialect] | csv.Dialect:
    sample = text[:20000]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.excel


def parse_number(text: str) -> float:
    """'1 234,56', '1,234.56', '1234.56' and '1234,56' are all 1234.56."""
    cleaned = re.sub(r"[\s  ']", "", text)
    if "," in cleaned and "." in cleaned:
        # The separator that comes last is the decimal one.
        thousands = "," if cleaned.rfind(".") > cleaned.rfind(",") else "."
        cleaned = cleaned.replace(thousands, "")
    cleaned = cleaned.replace(",", ".")
    return float(cleaned)


def parse_date(text: str) -> str:
    """YYYY-MM-DD or DD.MM.YYYY, returned as YYYY-MM-DD."""
    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text.strip(), pattern).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(text)


def _match_columns(header: list[str]) -> tuple[dict[str, int], list[str]]:
    positions: dict[str, int] = {}
    ignored: list[str] = []
    for index, raw in enumerate(header):
        normalised = _normalise_header(raw)
        column = next((name for name, aliases in _COLUMN_ALIASES.items() if normalised in aliases), None)
        if column is None or column in positions:
            if raw.strip():
                ignored.append(raw.strip())
            continue
        positions[column] = index
    missing = [column for column in REQUIRED_COLUMNS if column not in positions]
    if missing:
        raise ImportFileError(
            "Missing columns: " + ", ".join(missing) + ". The first row must name the columns, as in the template."
        )
    return positions, ignored


def _text(row: ImportRow, value: str, label: str, required: bool) -> str:
    value = value.strip()
    if required and not value:
        row.errors.append(f"{label} is required.")
    elif len(value) > MAX_TEXT_LEN:
        row.errors.append(f"{label} must be {MAX_TEXT_LEN} characters or less.")
    return value


def parse_assets_csv(
    data: bytes,
    *,
    existing_categories: Iterable[str],
    existing_locations: Iterable[str],
    existing_asset_names: Iterable[str],
) -> ImportPreview:
    """Read and check every row. Raises ImportFileError if the file can't be read at all."""
    text = _decode(data)
    reader = csv.reader(io.StringIO(text, newline=""), _dialect(text))
    try:
        header = next(reader)
    except StopIteration:
        raise ImportFileError("The file is empty.") from None
    positions, ignored = _match_columns(header)

    categories = {name.strip().lower() for name in existing_categories}
    locations = {name.strip().lower() for name in existing_locations}
    asset_names = {name.strip().lower() for name in existing_asset_names}
    new_categories: dict[str, str] = {}
    new_locations: dict[str, str] = {}
    seen_in_file: dict[tuple[str, str], int] = {}
    rows: list[ImportRow] = []

    for values in reader:
        if not any(value.strip() for value in values):
            continue
        if len(rows) >= MAX_ROWS:
            raise ImportFileError(f"The file has more than {MAX_ROWS} assets. Split it into smaller files.")
        row = ImportRow(line=reader.line_num)

        def cell(column: str) -> str:
            index = positions.get(column)
            return values[index] if index is not None and index < len(values) else ""

        row.name = _text(row, cell("name"), "Name", required=True)
        row.category = _text(row, cell("category"), "Category", required=True)
        row.location = _text(row, cell("location"), "Location", required=False)
        row.responsible_person = _text(row, cell("responsible_person"), "Responsible person", required=True)

        quantity_text = cell("quantity").strip()
        if quantity_text:
            try:
                quantity = parse_number(quantity_text)
                if quantity != int(quantity) or quantity < 0:
                    raise ValueError
                row.quantity = int(quantity)
            except ValueError:
                row.errors.append(f"Quantity must be a whole number, 0 or more (got \"{quantity_text}\").")

        value_text = cell("initial_value").strip()
        if not value_text:
            row.errors.append("Initial value is required.")
        else:
            try:
                row.initial_value = parse_number(value_text)
                if row.initial_value < 0:
                    row.errors.append("Initial value cannot be negative.")
            except ValueError:
                row.errors.append(f"Initial value must be a number (got \"{value_text}\").")

        date_text = cell("registration_date").strip()
        if not date_text:
            row.errors.append("Registration date is required.")
        else:
            try:
                row.registration_date = parse_date(date_text)
            except ValueError:
                row.errors.append(f"Registration date must be YYYY-MM-DD or DD.MM.YYYY (got \"{date_text}\").")

        if row.category and row.category.lower() not in categories:
            new_categories.setdefault(row.category.lower(), row.category)
        if row.location and row.location.lower() not in locations:
            new_locations.setdefault(row.location.lower(), row.location)

        if row.name:
            if row.name.lower() in asset_names:
                row.warnings.append("An asset with this name is already registered. It will be added again.")
            key = (row.name.lower(), row.category.lower())
            if key in seen_in_file:
                row.warnings.append(f"Same name and category as line {seen_in_file[key]}.")
            else:
                seen_in_file[key] = row.line
        rows.append(row)

    return ImportPreview(
        rows=rows,
        new_categories=sorted(new_categories.values(), key=str.casefold),
        new_locations=sorted(new_locations.values(), key=str.casefold),
        ignored_columns=ignored,
    )
