#!/usr/bin/env python3
"""
PDF to Excel Converter for Vehicle Operation Logs (공용차량 운행일지)

Supports:
- Old format (2023-2024): form-style, including 2-up (모아찍기) pages
- New format (2025-2026): table-style

Usage:
    python3 pdf_to_excel.py input.pdf
    python3 pdf_to_excel.py input.pdf -o output.xlsx
    python3 pdf_to_excel.py input.pdf --format old
    python3 pdf_to_excel.py ./pdf_folder/
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Output columns (simplified per user request)
STANDARD_COLUMNS = [
    "날짜",
    "사용목적",
    "행선지",
    "출발시간",
    "도착시간",
    "운전자",
    "동승자",
    "전일누계(km)",
    "출발(km)",
    "도착(km)",
    "금일주행(km)",
    "금일누계(km)",
]


# =============================================================================
# Format detection
# =============================================================================

def detect_format(pdf_path: str) -> str:
    """Auto-detect PDF format: 'old' (2023-2024 form) or 'new' (2025-2026 table)."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return "new"
        text = pdf.pages[0].extract_text() or ""
        flat = text.replace(" ", "")
        old_markers = ["차량운행일지", "계기표시", "전일누계", "금일주행", "관리운전원", "금일누계"]
        if sum(1 for m in old_markers if m in flat) >= 2:
            return "old"
    return "new"


# =============================================================================
# Old format (2023-2024) parser — supports 2-up (모아찍기) pages
# =============================================================================

def parse_old_format(pdf_path: str) -> pd.DataFrame:
    """Parse old form-style PDFs, including 2-up printed pages.

    Strategy: split each page into left/right halves using pdfplumber crop,
    then parse each half independently.
    """
    import pdfplumber

    records = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            sub_pages = _split_page(page)
            for sub in sub_pages:
                text = sub.extract_text() or ""
                if not text.strip():
                    continue
                tables = sub.extract_tables() or []
                page_records = _parse_form(text, tables)
                records.extend(page_records)

    if not records:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    return pd.DataFrame(records)


def _split_page(page) -> list:
    """Split a page into sub-pages if it contains 2-up layout.

    Detects 2-up by checking if '차량운행일지' appears twice (left and right).
    Falls back to treating the whole page as one form.
    """
    text = page.extract_text() or ""
    flat = text.replace(" ", "")

    # Count how many forms are on this page
    form_count = len(re.findall(r"차량운행일지", flat))

    if form_count >= 2:
        # 2-up: crop left half and right half
        width = page.width
        height = page.height
        mid = width / 2

        left = page.crop((0, 0, mid, height))
        right = page.crop((mid, 0, width, height))
        return [left, right]

    return [page]


def _parse_form(text: str, tables: list) -> list[dict]:
    """Parse one form (one day's log) from text and tables."""
    records = []

    # --- Date ---
    date_str = ""
    dm = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", text)
    if dm:
        date_str = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

    if not date_str:
        return []

    # --- Purpose ---
    purpose = ""
    pm = re.search(r"사용\s*목\s*적\s+(.+)", text)
    if pm:
        purpose = pm.group(1).strip()
        # Clean: remove trailing table headers that might get mixed in
        purpose = re.split(r"\s*계기", purpose)[0].strip()

    # --- Mileage summary ---
    prev_km = ""
    today_km = ""
    curr_km = ""

    for table in tables:
        for row in table:
            if not row:
                continue
            row_str = " ".join(str(c) for c in row if c)
            m = re.search(r"전일\s*누계\s*(\d[\d,]*)\s*km", row_str, re.I)
            if m:
                prev_km = m.group(1).replace(",", "")
            m = re.search(r"금일\s*주행\s*(\d[\d,]*)\s*km", row_str, re.I)
            if m:
                today_km = m.group(1).replace(",", "")
            m = re.search(r"금일\s*누계\s*(\d[\d,]*)\s*km", row_str, re.I)
            if m:
                curr_km = m.group(1).replace(",", "")

    # Fallback: try text-based extraction
    if not prev_km:
        m = re.search(r"전일\s*누계\s*(\d[\d,]*)\s*km", text, re.I)
        if m:
            prev_km = m.group(1).replace(",", "")
    if not today_km:
        m = re.search(r"금일\s*주행\s*(\d[\d,]*)\s*km", text, re.I)
        if m:
            today_km = m.group(1).replace(",", "")
    if not curr_km:
        m = re.search(r"금일\s*누계\s*(\d[\d,]*)\s*km", text, re.I)
        if m:
            curr_km = m.group(1).replace(",", "")

    # --- Extract individual trips from tables ---
    trips = _extract_trips(tables, text)

    if trips:
        for i, trip in enumerate(trips):
            start_km = trip.get("start_km", "")
            end_km = trip.get("end_km", "")

            records.append({
                "날짜": date_str,
                "사용목적": purpose,
                "행선지": trip.get("destination", ""),
                "출발시간": trip.get("depart_time", ""),
                "도착시간": trip.get("arrive_time", ""),
                "운전자": trip.get("driver", ""),
                "동승자": trip.get("passenger", ""),
                "전일누계(km)": prev_km if i == 0 else "",
                "출발(km)": start_km,
                "도착(km)": end_km,
                "금일주행(km)": today_km if i == 0 else "",
                "금일누계(km)": curr_km if i == 0 else "",
            })
    else:
        # No trips extracted, create a summary record
        records.append({
            "날짜": date_str,
            "사용목적": purpose,
            "행선지": "",
            "출발시간": "",
            "도착시간": "",
            "운전자": "",
            "동승자": "",
            "전일누계(km)": prev_km,
            "출발(km)": prev_km,
            "도착(km)": curr_km,
            "금일주행(km)": today_km,
            "금일누계(km)": curr_km,
        })

    return records


def _extract_trips(tables: list, text: str) -> list[dict]:
    """Extract trip rows from tables, with text fallback."""
    trips = []

    # --- From tables ---
    for table in tables:
        for row in table:
            if not row or len(row) < 3:
                continue
            cells = [str(c).strip() if c else "" for c in row]
            row_text = " ".join(cells)

            # Must contain departure time pattern
            dep = re.search(r"출\s*[:\uff1a]\s*(\d{1,2}[:\uff1a]\d{2})", row_text)
            if not dep:
                continue

            trip = {"depart_time": dep.group(1).replace("\uff1a", ":")}

            # Arrival time
            arr = re.search(r"착\s*[:\uff1a]\s*(\d{1,2}[:\uff1a]\d{2})", row_text)
            if arr:
                trip["arrive_time"] = arr.group(1).replace("\uff1a", ":")

            # Odometer: find 4-5 digit numbers, excluding time digits
            for cell in cells:
                clean = re.sub(r"[출착]\s*[:\uff1a]\s*\d{1,2}[:\uff1a]\d{2}", "", cell)
                nums = re.findall(r"\b(\d{4,6})\b", clean)
                if nums:
                    if "start_km" not in trip:
                        trip["start_km"] = nums[0]
                        if len(nums) >= 2:
                            trip["end_km"] = nums[1]
                    elif "end_km" not in trip:
                        trip["end_km"] = nums[0]

            # Destination: first cell if it has Korean text and isn't a header/time
            dest = cells[0].replace("\n", " ").strip() if cells[0] else ""
            skip_patterns = ["행선지", "출", "착", "계기", "운행", "운전", "동승", "소속", "성명"]
            if dest and re.search(r"[가-힣]", dest) and not any(s in dest for s in skip_patterns):
                trip["destination"] = dest

            # Driver & passenger from fixed column positions
            # Typical layout: [dest, time, start_km, end_km, dept, driver, pass_dept, passenger]
            if len(cells) >= 6:
                name = cells[5].strip() if len(cells) > 5 else ""
                if name and re.search(r"[가-힣]{2,4}", name) and name not in ("성명", "소속"):
                    trip["driver"] = name
            if len(cells) >= 8:
                pname = cells[7].strip() if len(cells) > 7 else ""
                if pname and re.search(r"[가-힣]{2,4}", pname) and pname not in ("성명", "소속"):
                    trip["passenger"] = pname

            # Fallback driver: scan all cells for Korean name
            if "driver" not in trip:
                for cell in cells:
                    if re.fullmatch(r"[가-힣]{2,4}", cell):
                        trip["driver"] = cell
                        break

            trips.append(trip)

    # --- Text fallback ---
    if not trips:
        for line in text.split("\n"):
            dep = re.search(r"출\s*[:\uff1a]\s*(\d{1,2}[:\uff1a]\d{2})", line)
            if not dep:
                continue
            trip = {"depart_time": dep.group(1).replace("\uff1a", ":")}
            arr = re.search(r"착\s*[:\uff1a]\s*(\d{1,2}[:\uff1a]\d{2})", line)
            if arr:
                trip["arrive_time"] = arr.group(1).replace("\uff1a", ":")
            nums = re.findall(r"\b(\d{4,6})\b", re.sub(r"\d{1,2}:\d{2}", "", line))
            if len(nums) >= 2:
                trip["start_km"] = nums[0]
                trip["end_km"] = nums[1]
            names = re.findall(r"[가-힣]{2,4}", line)
            skip = {"출발", "도착", "운행", "시간", "계기", "표시", "운전", "동승", "소속", "성명", "행선지"}
            for n in names:
                if n not in skip:
                    trip["driver"] = n
                    break
            trips.append(trip)

    return trips


# =============================================================================
# New format (2025-2026) table parser
# =============================================================================

def extract_tables_pdfplumber(pdf_path: str) -> list[pd.DataFrame]:
    """Extract tables from PDF using pdfplumber."""
    import pdfplumber

    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            if not page_tables:
                text = page.extract_text()
                if text and text.strip():
                    lines = [line.split() for line in text.strip().split("\n") if line.strip()]
                    if lines:
                        tables.append(pd.DataFrame(lines))
                continue
            for table in page_tables:
                if not table:
                    continue
                cleaned = [row for row in table if any(cell and str(cell).strip() for cell in row)]
                if cleaned:
                    tables.append(pd.DataFrame(cleaned))
    return tables


def extract_tables_tabula(pdf_path: str) -> list[pd.DataFrame]:
    """Extract tables from PDF using tabula-py."""
    import tabula

    try:
        tables = tabula.read_pdf(pdf_path, pages="all", multiple_tables=True, lattice=True)
    except Exception:
        tables = []
    if not tables:
        try:
            tables = tabula.read_pdf(pdf_path, pages="all", multiple_tables=True, stream=True)
        except Exception:
            tables = []
    return [t for t in tables if not t.empty]


def merge_tables(tables: list[pd.DataFrame]) -> pd.DataFrame:
    if not tables:
        return pd.DataFrame()
    if len(tables) == 1:
        return promote_header(tables[0])
    groups: dict[int, list[pd.DataFrame]] = {}
    for t in tables:
        groups.setdefault(len(t.columns), []).append(t)
    largest = max(groups.values(), key=lambda g: sum(len(t) for t in g))
    norm = []
    for t in largest:
        t = t.copy()
        t.columns = range(len(t.columns))
        norm.append(t)
    return promote_header(pd.concat(norm, ignore_index=True))


def promote_header(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    first_row = df.iloc[0]
    header_like = sum(
        1 for val in first_row
        if val is not None and str(val).strip() and not str(val).strip().replace(".", "").isdigit()
    )
    if header_like >= len(first_row) * 0.5:
        headers = [str(val).strip() if val is not None else f"Column_{i}" for i, val in enumerate(first_row)]
        df = df.iloc[1:].reset_index(drop=True)
        df.columns = headers
    return df


# =============================================================================
# Excel styling
# =============================================================================

def style_excel(wb_path: str) -> None:
    wb = load_workbook(wb_path)
    ws = wb.active

    header_font = Font(name="맑은 고딕", bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    cell_font = Font(name="맑은 고딕", size=10)
    thin_border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
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

    for col_idx in range(1, ws.max_column + 1):
        max_length = 0
        col_letter = get_column_letter(col_idx)
        for cell in ws[col_letter]:
            if cell.value:
                val_str = str(cell.value)
                length = sum(2 if ord(c) > 127 else 1 for c in val_str)
                max_length = max(max_length, length)
        ws.column_dimensions[col_letter].width = min(max(max_length + 4, 8), 50)

    ws.freeze_panes = "A2"
    wb.save(wb_path)


# =============================================================================
# Main conversion
# =============================================================================

def convert_pdf_to_excel(
    pdf_path: str,
    output_path: str | None = None,
    engine: str = "pdfplumber",
    sheet_name: str = "운행일지",
    merge: bool = True,
    pdf_format: str = "auto",
) -> str:
    pdf_path = str(Path(pdf_path).resolve())

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if output_path is None:
        output_path = str(Path(pdf_path).with_suffix(".xlsx"))

    if pdf_format == "auto":
        pdf_format = detect_format(pdf_path)

    print(f"  양식: {'2023-2024 (폼/모아찍기)' if pdf_format == 'old' else '2025-2026 (표)'}")
    print(f"  입력: {pdf_path}")

    if pdf_format == "old":
        df = parse_old_format(pdf_path)
        if df.empty:
            print("  경고: 데이터를 찾지 못했습니다.")
            pd.DataFrame(columns=STANDARD_COLUMNS).to_excel(output_path, index=False)
            return output_path
        print(f"  추출: {len(df)}건")
        df.to_excel(output_path, index=False, sheet_name=sheet_name)
        style_excel(output_path)
        print(f"  출력: {output_path}")
        return output_path

    print(f"  엔진: {engine}")
    if engine == "pdfplumber":
        tables = extract_tables_pdfplumber(pdf_path)
    elif engine == "tabula":
        tables = extract_tables_tabula(pdf_path)
    else:
        raise ValueError(f"Unknown engine: {engine}")

    if not tables:
        print("  경고: 테이블을 찾지 못했습니다.")
        pd.DataFrame().to_excel(output_path, index=False)
        return output_path

    print(f"  추출: {len(tables)} 테이블")

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
    print(f"  출력: {output_path}")
    return output_path


def batch_convert(input_dir: str, output_dir: str | None = None, **kwargs) -> list[str]:
    input_path = Path(input_dir)
    pdf_files = sorted(input_path.glob("*.pdf")) + sorted(input_path.glob("*.PDF"))

    if not pdf_files:
        print(f"PDF 파일 없음: {input_dir}")
        return []

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
    else:
        out_path = input_path

    results = []
    print(f"PDF 파일 {len(pdf_files)}개 발견\n")

    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"[{i}/{len(pdf_files)}] {pdf_file.name}")
        output_file = str(out_path / pdf_file.with_suffix(".xlsx").name)
        try:
            result = convert_pdf_to_excel(str(pdf_file), output_file, **kwargs)
            results.append(result)
            print()
        except Exception as e:
            print(f"  오류: {e}\n")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="PDF to Excel Converter - 공용차량 운행일지 변환기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 운행일지.pdf                       # 단일 변환 (자동 감지)
  %(prog)s 운행일지.pdf -o result.xlsx         # 출력 파일명 지정
  %(prog)s ./pdfs/                             # 폴더 일괄 변환
  %(prog)s 운행일지.pdf --format old           # 2023-2024 양식 강제
  %(prog)s 운행일지.pdf --engine tabula        # tabula 엔진 사용
        """,
    )
    parser.add_argument("input", help="PDF 파일 또는 PDF 폴더 경로")
    parser.add_argument("-o", "--output", help="출력 Excel 파일 경로")
    parser.add_argument(
        "--engine", choices=["pdfplumber", "tabula"], default="pdfplumber",
        help="추출 엔진 (기본: pdfplumber)",
    )
    parser.add_argument("--sheet-name", default="운행일지", help="시트 이름")
    parser.add_argument("--no-merge", action="store_true", help="테이블별 별도 시트")
    parser.add_argument(
        "--format", choices=["auto", "old", "new"], default="auto",
        help="양식: auto(자동), old(2023-2024), new(2025-2026)",
    )

    args = parser.parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"오류: '{args.input}' 경로를 찾을 수 없습니다.")
        sys.exit(1)

    print("=" * 50)
    print("  PDF → Excel 변환기 (운행일지)")
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
        print(f"\n완료: {len(results)}개 파일 변환")
    else:
        print(f"변환: {input_path.name}")
        try:
            result = convert_pdf_to_excel(str(input_path), args.output, **kwargs)
            print(f"\n완료! → {result}")
        except Exception as e:
            print(f"\n오류: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
