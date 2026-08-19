"""엑셀 관리대장 생성·누적 모듈 (openpyxl).

관리대장 열 구조는 시스템이 자동 생성하며, 임의로 열을 바꾸면 기능 오류가
발생할 수 있으므로 기존 파일을 열 때 헤더를 검증한다.
요구서 1건 = 1행으로 기록한다.
"""

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

SHEET_NAME = "관리대장"

# (헤더, 너비, 행 데이터 키) — 키가 None이면 수동 관리 항목(빈 값으로 둠)
COLUMNS = [
    ("소관위원회", 18, "committee"),
    ("요구일자", 12, "request_date"),
    ("제출기한", 12, "deadline"),
    ("요구서번호", 14, "doc_no"),
    ("요구의원/기관", 14, "member"),
    ("정당", 14, "party"),
    ("지역구", 16, "district"),
    ("자료 요구내용", 55, "content"),
    ("요구자", 10, "requester"),
    ("요구자 이메일", 24, "email"),
    ("우리회사의 담당 부서", 18, None),
    ("제출여부", 10, None),
    ("비고/메모", 20, None),
]

HEADER = [name for name, _, _ in COLUMNS]
_CONTENT_COL = HEADER.index("자료 요구내용") + 1

_HEADER_FILL = PatternFill("solid", fgColor="1F6FB2")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_THIN_BORDER = Border(*(Side(style="thin", color="CCCCCC"),) * 4)


class LedgerFormatError(ValueError):
    """기존 엑셀 파일의 열 구조가 관리대장 서식과 다를 때 발생."""


def create_ledger() -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME
    for idx, (name, width, _) in enumerate(COLUMNS, start=1):
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
    header = [
        (str(ws.cell(row=1, column=i + 1).value).strip() if ws.cell(row=1, column=i + 1).value else "")
        for i in range(len(HEADER))
    ]
    if header != HEADER:
        raise LedgerFormatError(
            "선택한 엑셀 파일이 관리대장 서식과 다릅니다. "
            "'새 관리대장 생성'으로 다시 만들거나 올바른 파일을 선택해 주세요."
        )
    return wb


def append_rows(wb: Workbook, rows: list[dict]) -> int:
    """요구서 1건당 1행씩 관리대장에 추가하고, 추가된 행 수를 반환한다."""
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb.active
    next_row = ws.max_row + 1

    for offset, row_data in enumerate(rows):
        for col, (_, _, key) in enumerate(COLUMNS, start=1):
            value = row_data.get(key, "") if key else ""
            cell = ws.cell(row=next_row + offset, column=col, value=value)
            cell.border = _THIN_BORDER
            cell.alignment = Alignment(
                vertical="center", wrap_text=(col == _CONTENT_COL)
            )
    return len(rows)
