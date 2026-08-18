"""엑셀 관리대장 생성·누적 모듈 (openpyxl).

관리대장 열 구조는 시스템이 자동 생성하며, 임의로 열을 바꾸면 기능 오류가
발생할 수 있으므로 기존 파일을 열 때 헤더를 검증한다.
"""

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

SHEET_NAME = "관리대장"

COLUMNS = [
    ("연번", 6),
    ("접수일자", 12),
    ("위원회", 18),
    ("의원명", 10),
    ("문서번호", 16),
    ("요구자료명", 50),
    ("제출기한", 12),
    ("담당부서", 16),
    ("처리상태", 10),
    ("비고", 20),
    ("원본파일", 24),
]

HEADER = [name for name, _ in COLUMNS]

_HEADER_FILL = PatternFill("solid", fgColor="1F6FB2")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_THIN_BORDER = Border(*(Side(style="thin", color="CCCCCC"),) * 4)


class LedgerFormatError(ValueError):
    """기존 엑셀 파일의 열 구조가 관리대장 서식과 다를 때 발생."""


def create_ledger() -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME
    for idx, (name, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=idx, value=name)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _THIN_BORDER
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = "A2"
    return wb


def open_ledger(path: str) -> Workbook:
    wb = load_workbook(path)
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
    else:
        ws = wb.active
    header = [ws.cell(row=1, column=i + 1).value for i in range(len(HEADER))]
    if header != HEADER:
        raise LedgerFormatError(
            "선택한 엑셀 파일이 관리대장 서식과 다릅니다. "
            "'새 관리대장 생성'으로 다시 만들거나 올바른 파일을 선택해 주세요."
        )
    return wb


def append_rows(wb: Workbook, rows: list[dict]) -> list[int]:
    """파싱 결과를 관리대장에 추가하고, 부여된 연번 목록을 반환한다."""
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
    next_row = ws.max_row + 1
    # 마지막 연번 이어받기 (빈 시트면 0부터)
    last_serial = 0
    for row in range(ws.max_row, 1, -1):
        value = ws.cell(row=row, column=1).value
        if isinstance(value, int):
            last_serial = value
            break

    serials = []
    for offset, row_data in enumerate(rows):
        serial = last_serial + offset + 1
        serials.append(serial)
        values = [
            serial,
            row_data.get("request_date", ""),
            row_data.get("committee", ""),
            row_data.get("member", ""),
            row_data.get("doc_no", ""),
            row_data.get("item", ""),
            row_data.get("deadline", ""),
            row_data.get("department", ""),
            "접수",
            "",
            row_data.get("source_file", ""),
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=next_row + offset, column=col, value=value)
            cell.border = _THIN_BORDER
            cell.alignment = Alignment(vertical="center", wrap_text=(col == 6))
    return serials
