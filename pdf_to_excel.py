#!/usr/bin/env python3
"""
PDF to Excel Converter for Vehicle Operation Logs (공용차량 운행일지)

Extracts tables from PDF files and converts them to Excel (.xlsx) format.
Supports two extraction engines: pdfplumber (default) and tabula.

Usage:
    python3 pdf_to_excel.py input.pdf
    python3 pdf_to_excel.py input.pdf -o output.xlsx
    python3 pdf_to_excel.py input.pdf --engine tabula
    python3 pdf_to_excel.py ./pdf_folder/          # batch convert all PDFs in folder
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def extract_tables_pdfplumber(pdf_path: str) -> list[pd.DataFrame]:
    """Extract tables from PDF using pdfplumber."""
    import pdfplumber

    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            page_tables = page.extract_tables()
            if not page_tables:
                # If no tables found, try extracting text as fallback
                text = page.extract_text()
                if text and text.strip():
                    lines = [line.split() for line in text.strip().split("\n") if line.strip()]
                    if lines:
                        df = pd.DataFrame(lines)
                        df.attrs["page"] = page_num
                        tables.append(df)
                continue

            for table in page_tables:
                if not table:
                    continue
                # Filter out completely empty rows
                cleaned = [row for row in table if any(cell and str(cell).strip() for cell in row)]
                if cleaned:
                    df = pd.DataFrame(cleaned)
                    df.attrs["page"] = page_num
                    tables.append(df)

    return tables


def extract_tables_tabula(pdf_path: str) -> list[pd.DataFrame]:
    """Extract tables from PDF using tabula-py."""
    import tabula

    try:
        tables = tabula.read_pdf(
            pdf_path,
            pages="all",
            multiple_tables=True,
            lattice=True,  # Try lattice mode first (for bordered tables)
        )
    except Exception:
        tables = []

    if not tables:
        try:
            tables = tabula.read_pdf(
                pdf_path,
                pages="all",
                multiple_tables=True,
                stream=True,  # Fallback to stream mode
            )
        except Exception:
            tables = []

    # Filter out empty dataframes
    return [t for t in tables if not t.empty]


def merge_tables(tables: list[pd.DataFrame]) -> pd.DataFrame:
    """Merge multiple extracted tables into a single DataFrame.

    Tries to detect if tables share the same structure (column count)
    and merges them. The first row of the first table is used as header
    if it looks like a header row.
    """
    if not tables:
        return pd.DataFrame()

    if len(tables) == 1:
        df = tables[0]
        return promote_header(df)

    # Group tables by column count
    groups: dict[int, list[pd.DataFrame]] = {}
    for t in tables:
        ncols = len(t.columns)
        groups.setdefault(ncols, []).append(t)

    # Take the largest group (most common structure)
    largest_group = max(groups.values(), key=lambda g: sum(len(t) for t in g))

    # Normalize column names to positional
    normalized = []
    for t in largest_group:
        t = t.copy()
        t.columns = range(len(t.columns))
        normalized.append(t)

    merged = pd.concat(normalized, ignore_index=True)
    return promote_header(merged)


def promote_header(df: pd.DataFrame) -> pd.DataFrame:
    """Promote the first row to column headers if it looks like a header."""
    if df.empty:
        return df

    first_row = df.iloc[0]
    # Check if first row contains non-numeric, non-empty strings (likely a header)
    header_like = sum(
        1
        for val in first_row
        if val is not None and str(val).strip() and not str(val).strip().replace(".", "").isdigit()
    )

    if header_like >= len(first_row) * 0.5:
        headers = [str(val).strip() if val is not None else f"Column_{i}" for i, val in enumerate(first_row)]
        df = df.iloc[1:].reset_index(drop=True)
        df.columns = headers

    return df


def style_excel(wb_path: str) -> None:
    """Apply styling to the generated Excel file for readability."""
    wb = load_workbook(wb_path)
    ws = wb.active

    # Styles
    header_font = Font(name="맑은 고딕", bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    cell_font = Font(name="맑은 고딕", size=10)
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_align = Alignment(horizontal="left", vertical="center", wrap_text=True)

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column), 1):
        for cell in row:
            cell.border = thin_border
            if row_idx == 1:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = center_align
            else:
                cell.font = cell_font
                cell.alignment = left_align

    # Auto-fit column widths
    for col_idx in range(1, ws.max_column + 1):
        max_length = 0
        col_letter = get_column_letter(col_idx)
        for cell in ws[col_letter]:
            if cell.value:
                # Account for Korean characters (wider)
                val_str = str(cell.value)
                length = sum(2 if ord(c) > 127 else 1 for c in val_str)
                max_length = max(max_length, length)
        ws.column_dimensions[col_letter].width = min(max(max_length + 4, 8), 50)

    # Freeze header row
    ws.freeze_panes = "A2"

    wb.save(wb_path)


def convert_pdf_to_excel(
    pdf_path: str,
    output_path: str | None = None,
    engine: str = "pdfplumber",
    sheet_name: str = "운행일지",
    merge: bool = True,
) -> str:
    """Convert a PDF file to Excel.

    Args:
        pdf_path: Path to the input PDF file.
        output_path: Path for the output Excel file. Auto-generated if None.
        engine: Extraction engine to use ('pdfplumber' or 'tabula').
        sheet_name: Name for the Excel sheet.
        merge: If True, merge all tables into one sheet. If False, each table gets its own sheet.

    Returns:
        Path to the generated Excel file.
    """
    pdf_path = str(Path(pdf_path).resolve())

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if output_path is None:
        output_path = str(Path(pdf_path).with_suffix(".xlsx"))

    print(f"  Engine: {engine}")
    print(f"  Input:  {pdf_path}")

    # Extract tables
    if engine == "pdfplumber":
        tables = extract_tables_pdfplumber(pdf_path)
    elif engine == "tabula":
        tables = extract_tables_tabula(pdf_path)
    else:
        raise ValueError(f"Unknown engine: {engine}. Use 'pdfplumber' or 'tabula'.")

    if not tables:
        print("  Warning: No tables found in PDF. Creating empty Excel file.")
        pd.DataFrame().to_excel(output_path, index=False)
        return output_path

    print(f"  Found {len(tables)} table(s)")

    if merge:
        df = merge_tables(tables)
        df.to_excel(output_path, index=False, sheet_name=sheet_name)
    else:
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            for i, table in enumerate(tables):
                promoted = promote_header(table)
                name = f"{sheet_name}_{i + 1}" if len(tables) > 1 else sheet_name
                promoted.to_excel(writer, index=False, sheet_name=name[:31])  # sheet name max 31 chars

    # Apply styling
    style_excel(output_path)

    print(f"  Output: {output_path}")
    return output_path


def batch_convert(input_dir: str, output_dir: str | None = None, **kwargs) -> list[str]:
    """Convert all PDF files in a directory to Excel."""
    input_path = Path(input_dir)
    pdf_files = sorted(input_path.glob("*.pdf")) + sorted(input_path.glob("*.PDF"))

    if not pdf_files:
        print(f"No PDF files found in: {input_dir}")
        return []

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
    else:
        out_path = input_path

    results = []
    print(f"Found {len(pdf_files)} PDF file(s) to convert\n")

    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] Converting: {pdf_file.name}")
        output_file = str(out_path / pdf_file.with_suffix(".xlsx").name)
        try:
            result = convert_pdf_to_excel(str(pdf_file), output_file, **kwargs)
            results.append(result)
            print(f"  Done!\n")
        except Exception as e:
            print(f"  Error: {e}\n")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="PDF to Excel Converter - 공용차량 운행일지 변환기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 운행일지.pdf                       # Convert single PDF
  %(prog)s 운행일지.pdf -o result.xlsx         # Specify output filename
  %(prog)s ./pdfs/                             # Batch convert all PDFs in folder
  %(prog)s 운행일지.pdf --engine tabula        # Use tabula engine
  %(prog)s 운행일지.pdf --no-merge             # Keep tables in separate sheets
        """,
    )
    parser.add_argument("input", help="Input PDF file or directory containing PDF files")
    parser.add_argument("-o", "--output", help="Output Excel file path (or output directory for batch mode)")
    parser.add_argument(
        "--engine",
        choices=["pdfplumber", "tabula"],
        default="pdfplumber",
        help="PDF table extraction engine (default: pdfplumber)",
    )
    parser.add_argument(
        "--sheet-name",
        default="운행일지",
        help="Excel sheet name (default: 운행일지)",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Don't merge tables; put each table in a separate sheet",
    )

    args = parser.parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: '{args.input}' does not exist.")
        sys.exit(1)

    print("=" * 50)
    print("  PDF -> Excel Converter (운행일지 변환기)")
    print("=" * 50)
    print()

    kwargs = {
        "engine": args.engine,
        "sheet_name": args.sheet_name,
        "merge": not args.no_merge,
    }

    if input_path.is_dir():
        results = batch_convert(str(input_path), args.output, **kwargs)
        print(f"\nCompleted: {len(results)} file(s) converted.")
    else:
        print(f"Converting: {input_path.name}")
        try:
            result = convert_pdf_to_excel(str(input_path), args.output, **kwargs)
            print(f"\nDone! Excel file saved to: {result}")
        except Exception as e:
            print(f"\nError: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
