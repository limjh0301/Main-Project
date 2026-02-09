#!/usr/bin/env python3
"""
PDF to Excel Converter for Vehicle Operation Logs (공용차량 운행일지)

Extracts tables from PDF files and converts them to Excel (.xlsx) format.
Supports two extraction engines: pdfplumber (default) and tabula.
Supports both new (2025-2026 table) and old (2023-2024 form) PDF formats.

Usage:
    python3 pdf_to_excel.py input.pdf
    python3 pdf_to_excel.py input.pdf -o output.xlsx
    python3 pdf_to_excel.py input.pdf --engine tabula
    python3 pdf_to_excel.py input.pdf --format old           # 2023-2024 양식
    python3 pdf_to_excel.py ./pdf_folder/                    # batch convert all PDFs
    python3 pdf_to_excel.py ./pdf_folder/ --format old       # batch convert old format
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Standard column names for the unified output
STANDARD_COLUMNS = [
    "날짜",          # Date
    "차량번호",      # Vehicle No.
    "운전자",        # Driver
    "소속",          # Department
    "사용목적",      # Purpose
    "행선지",        # Destination
    "출발시간",      # Depart Time
    "도착시간",      # Return Time
    "출발(km)",      # Start KM
    "도착(km)",      # End KM
    "주행거리(km)",  # Distance
    "수령량(ℓ)",     # Fuel (L)
    "동승자",        # Passenger
    "비고",          # Notes
]


def detect_format(pdf_path: str) -> str:
    """Auto-detect PDF format: 'old' (2023-2024 form) or 'new' (2025-2026 table)."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return "new"
        text = pdf.pages[0].extract_text() or ""
        flat = text.replace(" ", "")
        # Korean markers
        old_markers_kr = ["차량운행일지", "계기표시", "전일누계", "금일주행", "관리운전원"]
        # English markers (for testing / bilingual PDFs)
        old_markers_en = ["PrevTotal", "TodayDrive", "CurrTotal", "Odometer", "VehicleLog"]
        kr_matches = sum(1 for m in old_markers_kr if m in flat)
        en_matches = sum(1 for m in old_markers_en if m in flat)
        if kr_matches >= 2 or en_matches >= 2:
            return "old"
    return "new"


def parse_old_format(pdf_path: str) -> pd.DataFrame:
    """Parse old (2023-2024) form-style vehicle operation log PDFs.

    Each page is one day's record with a fixed form layout.
    Extracts fields from structured tables on each page.
    """
    import pdfplumber

    records = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []

            if not text.strip():
                continue

            page_records = _parse_old_format_page(text, tables)
            if page_records:
                records.extend(page_records)

    if not records:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    return pd.DataFrame(records)


def _parse_old_format_page(text: str, tables: list) -> list[dict]:
    """Parse a single page of old-format PDF into record(s)."""

    # --- Extract date (Korean: 2023년 1월 3일 / English: 2023year 1month 3day) ---
    date_str = ""
    dm = re.search(r"(\d{4})\s*(?:년|year)\s*(\d{1,2})\s*(?:월|month)\s*(\d{1,2})\s*(?:일|day)", text)
    if dm:
        date_str = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

    # --- Extract vehicle number ---
    vehicle_no = ""
    vm = re.search(r"(?:차량번호|Vehicle\s*No\.?)\s*(\S+)", text)
    if vm:
        vehicle_no = vm.group(1)

    # --- Extract purpose ---
    purpose = ""
    pm = re.search(r"(?:사용목적|Purpose)\s+(.+)", text)
    if pm:
        purpose = pm.group(1).strip()

    # --- Extract mileage from summary table ---
    prev_total_km = ""
    today_km = ""
    curr_total_km = ""
    fuel = ""

    for table in tables:
        for row in table:
            if not row:
                continue
            row_str = " ".join(str(c) for c in row if c)
            # Previous total
            m = re.search(r"(?:전일누계|Prev\s*Total)\s*(\d[\d,]*)\s*km", row_str, re.I)
            if m:
                prev_total_km = m.group(1).replace(",", "")
            # Today's distance
            m = re.search(r"(?:금일주행|Today\s*Drive)\s*(\d[\d,]*)\s*km", row_str, re.I)
            if m:
                today_km = m.group(1).replace(",", "")
            # Current total
            m = re.search(r"(?:금일누계|Curr\s*Total)\s*(\d[\d,]*)\s*km", row_str, re.I)
            if m:
                curr_total_km = m.group(1).replace(",", "")
            # Fuel
            m = re.search(r"(?:수령량|Qty)\s*(\d[\d.]*)\s*[ℓlL]", row_str)
            if m:
                fuel = m.group(1)

    # --- Extract trips from the main trip table ---
    trips = []
    for table in tables:
        for row in table:
            if not row or len(row) < 3:
                continue
            cells = [str(c).strip() if c else "" for c in row]
            row_joined = " ".join(cells)

            # Detect time patterns: 출:HH:MM / Dep:HH:MM / 착:HH:MM / Arr:HH:MM
            dep_match = re.search(
                r"(?:출|Dep)\s*[:\uff1a]\s*(\d{1,2}[:\uff1a]\d{2})", row_joined
            )
            if not dep_match:
                continue

            # Skip rows with only empty times (e.g., "Dep:\nArr:")
            if not dep_match.group(1):
                continue

            trip = {"depart_time": dep_match.group(1).replace("\uff1a", ":")}

            arr_match = re.search(
                r"(?:착|Arr)\s*[:\uff1a]\s*(\d{1,2}[:\uff1a]\d{2})", row_joined
            )
            if arr_match:
                trip["arrive_time"] = arr_match.group(1).replace("\uff1a", ":")

            # Odometer: 4-6 digit numbers (excluding time digits)
            # Look in specific cells (typically columns 2 and 3 in 8-col table)
            odometer_nums = []
            for cell in cells:
                cell_clean = re.sub(r"(?:출|착|Dep|Arr)\s*[:\uff1a]\s*\d{1,2}[:\uff1a]\d{2}", "", cell)
                nums = re.findall(r"\b(\d{4,6})\b", cell_clean)
                odometer_nums.extend(nums)
            if len(odometer_nums) >= 2:
                trip["start_km"] = odometer_nums[0]
                trip["end_km"] = odometer_nums[1]

            # Destination (first cell usually, or cell with meaningful text)
            if cells[0] and cells[0] not in ("", "None"):
                dest = cells[0].replace("\n", " ").strip()
                if dest and not re.search(r"(?:출|착|Dep|Arr)[:\uff1a]", dest):
                    trip["destination"] = dest

            # For 8-column tables: [dest, time, start_km, end_km, dept, name, pass_dept, pass_name]
            # For other layouts, fall back to heuristic matching
            if len(cells) >= 8:
                dept_cell = cells[4].strip() if cells[4] else ""
                name_cell = cells[5].strip() if cells[5] else ""
                if name_cell and name_cell not in ("None", "", "Name"):
                    trip["driver"] = name_cell
                if dept_cell and dept_cell not in ("None", "", "Dept"):
                    trip["department"] = dept_cell
                # Passenger
                pass_name = cells[7].strip() if cells[7] else ""
                if pass_name and pass_name not in ("None", "", "Name"):
                    trip["passenger"] = pass_name
            else:
                # Heuristic: Korean name (2-4 chars)
                for cell in cells[4:]:
                    if cell and re.fullmatch(r"[가-힣]{2,4}", cell):
                        trip["driver"] = cell
                        break
                for cell in cells[4:]:
                    if cell and any(kw in cell for kw in ["팀", "부", "실"]):
                        trip["department"] = cell
                        break

            trips.append(trip)

    # --- Build records ---
    if not trips:
        # No trips found; create one record from page-level data
        if not date_str and not vehicle_no:
            return []
        distance = today_km
        if not distance and prev_total_km and curr_total_km:
            try:
                distance = str(int(curr_total_km) - int(prev_total_km))
            except ValueError:
                pass
        return [{
            "날짜": date_str, "차량번호": vehicle_no,
            "운전자": "", "소속": "", "사용목적": purpose, "행선지": "",
            "출발시간": "", "도착시간": "",
            "출발(km)": prev_total_km, "도착(km)": curr_total_km,
            "주행거리(km)": distance, "수령량(ℓ)": fuel,
            "동승자": "", "비고": "",
        }]

    records = []
    for i, trip in enumerate(trips):
        start_km = trip.get("start_km", "")
        end_km = trip.get("end_km", "")
        distance = ""

        if not start_km and i == 0 and prev_total_km:
            start_km = prev_total_km
        if not end_km and i == len(trips) - 1 and curr_total_km:
            end_km = curr_total_km

        if start_km and end_km:
            try:
                distance = str(int(end_km.replace(",", "")) - int(start_km.replace(",", "")))
            except ValueError:
                pass
        if not distance:
            distance = today_km if i == 0 else ""

        records.append({
            "날짜": date_str,
            "차량번호": vehicle_no,
            "운전자": trip.get("driver", ""),
            "소속": trip.get("department", ""),
            "사용목적": purpose,
            "행선지": trip.get("destination", ""),
            "출발시간": trip.get("depart_time", ""),
            "도착시간": trip.get("arrive_time", ""),
            "출발(km)": start_km,
            "도착(km)": end_km,
            "주행거리(km)": distance,
            "수령량(ℓ)": fuel if i == 0 else "",
            "동승자": "",
            "비고": "",
        })

    return records


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
    pdf_format: str = "auto",
) -> str:
    """Convert a PDF file to Excel.

    Args:
        pdf_path: Path to the input PDF file.
        output_path: Path for the output Excel file. Auto-generated if None.
        engine: Extraction engine to use ('pdfplumber' or 'tabula').
        sheet_name: Name for the Excel sheet.
        merge: If True, merge all tables into one sheet. If False, each table gets its own sheet.
        pdf_format: 'auto', 'old' (2023-2024 form), or 'new' (2025-2026 table).

    Returns:
        Path to the generated Excel file.
    """
    pdf_path = str(Path(pdf_path).resolve())

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if output_path is None:
        output_path = str(Path(pdf_path).with_suffix(".xlsx"))

    # Auto-detect format
    if pdf_format == "auto":
        pdf_format = detect_format(pdf_path)

    print(f"  Format: {pdf_format} ({'2023-2024 양식' if pdf_format == 'old' else '2025-2026 양식'})")
    print(f"  Input:  {pdf_path}")

    # --- Old format: form-style parsing ---
    if pdf_format == "old":
        df = parse_old_format(pdf_path)
        if df.empty:
            print("  Warning: No records found in PDF.")
            pd.DataFrame(columns=STANDARD_COLUMNS).to_excel(output_path, index=False)
            return output_path
        print(f"  Found {len(df)} record(s)")
        df.to_excel(output_path, index=False, sheet_name=sheet_name)
        style_excel(output_path)
        print(f"  Output: {output_path}")
        return output_path

    # --- New format: table extraction ---
    print(f"  Engine: {engine}")

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
                promoted.to_excel(writer, index=False, sheet_name=name[:31])

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
    parser.add_argument(
        "--format",
        choices=["auto", "old", "new"],
        default="auto",
        help="PDF format: 'auto' (auto-detect), 'old' (2023-2024 양식), 'new' (2025-2026 양식). Default: auto",
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
        "pdf_format": args.format,
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
