from __future__ import annotations

import csv
import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

META_HEADERS = ["Fisier", "Tabel", "Categorie", "Rand"]


def _safe_sheet_title(name: str, used: set[str]) -> str:
    base = (name or "Document")[:28].strip() or "Document"
    title = base
    i = 2
    while title in used:
        title = f"{base[:25]}_{i}"
        i += 1
    used.add(title)
    return title


def _collect_unique_columns(results: list[dict[str, Any]]) -> list[str]:
    """Coloane unice, in ordinea primei aparitii, peste toate tabelele/documentele."""
    seen: dict[str, None] = {}
    for doc in results:
        for table in doc.get("tables", []):
            for col in table.get("columns") or []:
                seen.setdefault(col, None)
    return list(seen.keys())


def _iter_wide_rows(results: list[dict[str, Any]], unique_columns: list[str]):
    """
    Randuri in format wide: coloanele de identificare (Fisier/Tabel/Categorie/Rand)
    + o coloana pentru FIECARE coloana unica intalnita in oricare tabel.
    Pe un rand provenit dintr-un tabel care nu are o anumita coloana, celula
    ramane goala - asa se vede clar din ce tabel/pagina vine fiecare valoare,
    fara sa se amestece coloane intre tabele diferite.
    """
    col_index = {col: i for i, col in enumerate(unique_columns)}
    for doc in results:
        filename = doc.get("filename", "")
        for table in doc.get("tables", []):
            title = table.get("title", "")
            category = table.get("category", "")
            columns = table.get("columns") or []
            for row_i, row in enumerate(table.get("rows", []), start=1):
                values = [""] * len(unique_columns)
                for col_name, value in zip(columns, row):
                    values[col_index[col_name]] = value
                yield [filename, title, category, row_i] + values


def build_xlsx(results: list[dict[str, Any]]) -> bytes:
    """
    results: lista de dict-uri {filename, tables: [{title, category, columns, rows}]}
    (formatul returnat de extraction.extract_tables_from_pdf)

    Produce un sheet PER DOCUMENT, fiecare in format wide:
    Tabel/Categorie/Rand + toate coloanele unice gasite in tabelele acelui
    document. Un rand are valori doar pe coloanele tabelului din care provine,
    restul raman goale.
    """
    wb = Workbook()
    wb.remove(wb.active)
    used_titles: set[str] = set()

    for doc in results:
        sheet_name = _safe_sheet_title(doc.get("filename", "Document"), used_titles)
        ws = wb.create_sheet(title=sheet_name)

        unique_columns = _collect_unique_columns([doc])
        headers = ["Tabel", "Categorie", "Rand"] + unique_columns
        for col_i, h in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_i, value=h)
            cell.font = Font(bold=True)

        col_index = {col: i for i, col in enumerate(unique_columns)}
        row_idx = 2
        for table in doc.get("tables", []):
            title = table.get("title", "")
            category = table.get("category", "")
            columns = table.get("columns") or []
            for row_i, row in enumerate(table.get("rows", []), start=1):
                values = [""] * len(unique_columns)
                for col_name, value in zip(columns, row):
                    values[col_index[col_name]] = value
                line = [title, category, row_i] + values
                for col_i, value in enumerate(line, start=1):
                    ws.cell(row=row_idx, column=col_i, value=value)
                row_idx += 1

        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 16
        ws.column_dimensions["C"].width = 8
        for i in range(len(unique_columns)):
            col_letter = get_column_letter(3 + i + 1)
            ws.column_dimensions[col_letter].width = 20
        ws.freeze_panes = "A2"

    if not wb.sheetnames:
        wb.create_sheet(title="Fara date")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_csv(results: list[dict[str, Any]]) -> bytes:
    """CSV nu suporta mai multe sheet-uri - exportam formatul wide (acelasi ca sheet-ul 'Date')."""
    unique_columns = _collect_unique_columns(results)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(META_HEADERS + unique_columns)
    for line in _iter_wide_rows(results, unique_columns):
        writer.writerow(line)

    return buf.getvalue().encode("utf-8-sig")  # BOM ca Excel sa deschida diacriticele corect
"""
from __future__ import annotations

import csv
import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

META_HEADERS = ["Fisier", "Tabel", "Categorie", "Rand"]


def _safe_sheet_title(name: str, used: set[str]) -> str:
    base = (name or "Document")[:28].strip() or "Document"
    title = base
    i = 2
    while title in used:
        title = f"{base[:25]}_{i}"
        i += 1
    used.add(title)
    return title


def _collect_unique_columns(results: list[dict[str, Any]]) -> list[str]:

    seen: dict[str, None] = {}
    for doc in results:
        for table in doc.get("tables", []):
            for col in table.get("columns") or []:
                seen.setdefault(col, None)
    return list(seen.keys())


def _iter_wide_rows(results: list[dict[str, Any]], unique_columns: list[str]):

    col_index = {col: i for i, col in enumerate(unique_columns)}
    for doc in results:
        filename = doc.get("filename", "")
        for table in doc.get("tables", []):
            title = table.get("title", "")
            category = table.get("category", "")
            columns = table.get("columns") or []
            for row_i, row in enumerate(table.get("rows", []), start=1):
                values = [""] * len(unique_columns)
                for col_name, value in zip(columns, row):
                    values[col_index[col_name]] = value
                yield [filename, title, category, row_i] + values


def build_xlsx(results: list[dict[str, Any]]) -> bytes:

    unique_columns = _collect_unique_columns(results)

    wb = Workbook()
    wb.remove(wb.active)

    # --- Sheet 1: wide, cu identificare sursa ---
    ws_wide = wb.create_sheet(title="Date")
    headers = META_HEADERS + unique_columns
    for col_i, h in enumerate(headers, start=1):
        cell = ws_wide.cell(row=1, column=col_i, value=h)
        cell.font = Font(bold=True)

    row_idx = 2
    for line in _iter_wide_rows(results, unique_columns):
        for col_i, value in enumerate(line, start=1):
            ws_wide.cell(row=row_idx, column=col_i, value=value)
        row_idx += 1

    ws_wide.column_dimensions["A"].width = 24
    ws_wide.column_dimensions["B"].width = 30
    ws_wide.column_dimensions["C"].width = 16
    ws_wide.column_dimensions["D"].width = 8
    for i in range(len(unique_columns)):
        col_letter = get_column_letter(len(META_HEADERS) + i + 1)
        ws_wide.column_dimensions[col_letter].width = 20
    ws_wide.freeze_panes = "A2"

    # --- Sheet 2: grupat pe blocuri, pentru citit vizual ---
    used_titles: set[str] = set()
    for doc in results:
        sheet_name = _safe_sheet_title(doc.get("filename", "Document"), used_titles)
        ws = wb.create_sheet(title=sheet_name)
        row_idx = 1

        for table in doc.get("tables", []):
            columns = table.get("columns") or []
            title_cell = ws.cell(row=row_idx, column=1, value=f"{table.get('title', '')}"
                                  f" [{table.get('category', '')}]")
            title_cell.font = Font(bold=True, size=12)
            row_idx += 1

            for col_i, col_name in enumerate(columns, start=1):
                cell = ws.cell(row=row_idx, column=col_i, value=col_name)
                cell.font = Font(bold=True)
            row_idx += 1

            for row in table.get("rows", []):
                for col_i, value in enumerate(row, start=1):
                    ws.cell(row=row_idx, column=col_i, value=value)
                row_idx += 1

            row_idx += 1

        for col_cells in ws.columns:
            length = max((len(str(c.value)) if c.value is not None else 0 for c in col_cells), default=8)
            col_letter = get_column_letter(col_cells[0].column)
            ws.column_dimensions[col_letter].width = min(max(length + 2, 10), 60)

    if not wb.sheetnames:
        wb.create_sheet(title="Fara date")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_csv(results: list[dict[str, Any]]) -> bytes:

    unique_columns = _collect_unique_columns(results)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(META_HEADERS + unique_columns)
    for line in _iter_wide_rows(results, unique_columns):
        writer.writerow(line)

    return buf.getvalue().encode("utf-8-sig")  # BOM ca Excel sa deschida diacriticele corect
"""