"""엑셀 관리대장 생성·누적 모듈 (openpyxl).

기관에서 쓰는 '국회 요구자료' 관리대장 양식을 따른다.
  1행: 제목(예: 2026년도 국회 요구자료) / 3행: 머리글 / 4행부터: 요구서 1건 = 1행
기존 관리대장을 올리면 머리글 행을 찾아 열 구조를 검증하고, 마지막 기록 다음 행에
이어 쓴다. 이어 쓸 때는 바로 위 기록 행의 서식(글꼴·테두리·표시형식)을 그대로 따른다.
소속(정당)은 '국회의원 현황' 명단(제22대)에서 의원명으로 찾아 값으로 적는다.
"""

import csv
import os
import re
from copy import copy
from datetime import date, datetime

SHEET_NAME = "기관명"
TITLE_FORMAT = "{year}년도 국회 요구자료"
HEADER_ROW = 3  # 새 관리대장의 머리글 행 (기존 파일은 위쪽 10행 안에서 찾는다)
_HEADER_SEARCH_ROWS = 10
_MEMBER_CSV = os.path.join(os.path.dirname(__file__), "data", "assembly_members.csv")

# (머리글, 너비, 행 데이터 키) — 키가 None이면 수동 관리 항목(빈 값으로 둠)
COLUMNS = [
    ("순번", 4.6, "seq"),
    ("요구서 번호", 10.5, "doc_no"),
    ("접수일자", 11.1, "request_date"),
    ("제출기한", 10.1, "deadline"),
    ("소속", 13, "party"),
    ("의원명", 12.1, "member"),
    ("비서관", 9, "requester"),
    ("자료요구서 제목 및 내용", 120.5, "content"),
    ("제출일자", 13.2, None),
    ("비고", 29.9, "memo"),
]

HEADER = [name for name, _, _ in COLUMNS]
_KEYS = [key for _, _, key in COLUMNS]
_COL = {key: i + 1 for i, key in enumerate(_KEYS) if key}
_DATE_KEYS = ("request_date", "deadline")
_DATE_FORMAT = "mm-dd-yy"

# 행 높이: 줄당 12pt (엑셀 최대 409.5pt). 내용 칸 한 줄에 들어가는 글자 폭(한글 2, 그 외 1)
_LINE_HEIGHT, _MIN_HEIGHT, _MAX_HEIGHT, _LINE_WIDTH = 12, 24, 409.5, 140

_STYLES: dict = {}
_MEMBERS: list[list[str]] = []  # [0]=헤더, [1:]=의원 행
_MEMBER_INFO: dict[str, tuple[str, str, str]] = {}  # 의원명 -> (정당, 소속위원회, 지역)


class LedgerFormatError(ValueError):
    """기존 엑셀 파일의 열 구조가 관리대장 양식과 다를 때 발생."""


# ---------------- 국회의원 명단 ----------------
def _members() -> list[list[str]]:
    if not _MEMBERS:
        with open(_MEMBER_CSV, newline="", encoding="utf-8") as f:
            _MEMBERS.extend(csv.reader(f))
    return _MEMBERS


def member_info(name: str) -> tuple[str, str, str] | None:
    """의원명으로 (정당, 소속위원회, 지역)을 찾는다. 없으면 None."""
    if not _MEMBER_INFO:
        for row in _members()[1:]:
            _MEMBER_INFO.setdefault(row[2], (row[3], row[4], row[5]))
    return _MEMBER_INFO.get(name)


def member_names() -> list[str]:
    """국회의원 현황의 의원명 목록 (긴 이름부터 — 파일명에서 찾을 때 짧은 이름이 먼저 걸리지 않도록)."""
    return sorted({row[2] for row in _members()[1:]}, key=len, reverse=True)


def enrich_member_fields(data: dict) -> dict:
    """요구의원이 국회의원 현황에 있으면 정당·소관위원회·지역구를 명단 값으로 채운다."""
    info = member_info(data.get("member", ""))
    if info:
        data["party"], data["committee"], data["district"] = info
    return data


# ---------------- 양식 ----------------
def _styles() -> dict:
    if not _STYLES:
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

        side = Side(style="thin")
        _STYLES.update(
            title_font=Font(name="HY헤드라인M", size=22),
            header_fill=PatternFill("solid", fgColor="DDEBF7"),
            header_font=Font(name="맑은 고딕", size=11, bold=True),
            body_font=Font(name="맑은 고딕", size=9),
            border=Border(left=side, right=side, top=side, bottom=side),
            center=Alignment(horizontal="center", vertical="center"),
            content=Alignment(horizontal="left", vertical="center", wrap_text=True),
        )
    return _STYLES


def _norm_header(value) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _locate(wb):
    """(관리대장 시트, 머리글 행)을 찾는다. 없으면 LedgerFormatError."""
    want = [_norm_header(h) for h in HEADER]
    for ws in wb.worksheets:
        for r in range(1, min(ws.max_row, _HEADER_SEARCH_ROWS) + 1):
            if [_norm_header(ws.cell(row=r, column=c).value) for c in range(1, len(HEADER) + 1)] == want:
                return ws, r
    raise LedgerFormatError(
        "선택한 엑셀 파일이 관리대장 양식과 다릅니다. 머리글이 "
        f"'{' · '.join(HEADER)}' 순서인지 확인하거나 '새 관리대장 생성'을 사용해 주세요."
    )


def create_ledger(year: int | None = None):
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    st = _styles()
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME
    title = ws.cell(row=1, column=1, value=TITLE_FORMAT.format(year=year or date.today().year))
    title.font = st["title_font"]
    ws.row_dimensions[1].height = 27
    for idx, (name, width, _) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=HEADER_ROW, column=idx, value=name)
        cell.fill, cell.font, cell.alignment, cell.border = (
            st["header_fill"], st["header_font"], st["center"], st["border"])
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = f"A{HEADER_ROW + 1}"
    ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(len(COLUMNS))}{HEADER_ROW}"
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToHeight = 0
    return wb


def open_ledger(path: str):
    from openpyxl import load_workbook

    wb = load_workbook(path)
    _locate(wb)  # 양식 검증
    return wb


# ---------------- 기록 ----------------
def _values(ws, header_row: int, cols: range):
    """머리글 아래에서 값이 있는 칸만 (행, 열, 값)으로 돌려준다.

    서식만 넓게 지정된 대장은 max_row가 100만 행을 넘기도 하므로, 빈 칸을 하나씩
    훑지 않고 실제로 만들어진 셀만 본다.
    """
    for (r, c), cell in ws._cells.items():
        if r > header_row and c in cols and cell.value not in (None, ""):
            yield r, c, cell.value


def _last_data_row(ws, header_row: int) -> int:
    """마지막 기록 행. 순번만 미리 채워 둔 빈 행은 기록으로 보지 않는다 (요구서 번호~비고 중 값이 있어야 함)."""
    return max((r for r, _, _ in _values(ws, header_row, range(2, len(COLUMNS) + 1))), default=header_row)


def next_row(wb) -> int:
    """다음에 기록될 관리대장 행 번호."""
    ws, header_row = _locate(wb)
    return _last_data_row(ws, header_row) + 1


def existing_doc_nos(wb) -> set[str]:
    """관리대장에 이미 기록된 요구서 번호 (같은 요구서를 두 번 올려도 중복 기록하지 않도록)."""
    ws, header_row = _locate(wb)
    col = _COL["doc_no"]
    return {str(v).strip() for _, _, v in _values(ws, header_row, range(col, col + 1))}


def _to_date(value):
    """'2026-09-21' / '2026.09.28' → date. 날짜가 아니면 원래 값."""
    if isinstance(value, (date, datetime)):
        return value
    m = re.fullmatch(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(value or "").strip())
    if not m:
        return value
    try:
        return date(*map(int, m.groups()))
    except ValueError:
        return value


def _row_height(content: str) -> float:
    width = lambda s: sum(2 if ord(ch) > 0x1100 else 1 for ch in s)
    lines = sum(max(1, -(-width(line) // _LINE_WIDTH)) for line in str(content).split("\n"))
    return min(_MAX_HEIGHT, max(_MIN_HEIGHT, lines * _LINE_HEIGHT))


def append_rows(wb, rows: list[dict]) -> int:
    """요구서 1건당 1행씩 마지막 기록 다음 행부터 적고, 적은 행 수를 반환한다.

    순번은 기존 기록의 마지막 순번에 이어 붙인다. 서식은 바로 위 기록 행을 따르고,
    기록이 없으면(새 관리대장) 기본 양식을 쓴다.
    """
    from openpyxl.utils import get_column_letter

    ws, header_row = _locate(wb)
    last = _last_data_row(ws, header_row)
    seq = int(max((v for r, _, v in _values(ws, header_row, range(1, 2))
                   if r <= last and isinstance(v, (int, float))), default=0))
    st = _styles()

    for offset, data in enumerate(rows, start=1):
        row_idx, seq = last + offset, seq + 1
        values = {**data, "seq": seq}
        for col, key in enumerate(_KEYS, start=1):
            value = values.get(key, "") if key else None
            if key in _DATE_KEYS:
                value = _to_date(value) or None
            cell = ws.cell(row=row_idx, column=col, value=value if value != "" else None)
            template = ws.cell(row=row_idx - 1, column=col) if row_idx - 1 > header_row else None
            if template is not None and template.has_style:
                cell._style = copy(template._style)
            else:
                cell.font, cell.border = st["body_font"], st["border"]
                cell.alignment = st["content"] if key == "content" else st["center"]
                if key in _DATE_KEYS or key is None:
                    cell.number_format = _DATE_FORMAT
        ws.row_dimensions[row_idx].height = _row_height(values.get("content", ""))

    # 자동 필터 범위가 새 행을 덮도록 넓힌다
    end = last + len(rows)
    ref = ws.auto_filter.ref
    m = re.fullmatch(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", ref or "")
    if m and int(m.group(4)) < end:
        ws.auto_filter.ref = f"{m.group(1)}{m.group(2)}:{m.group(3)}{end}"
    elif not m:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(len(COLUMNS))}{end}"
    return len(rows)


def fill_dates(wb, first: int, last: int, key: str, value) -> int:
    """관리대장 first~last 행의 접수일자(request_date)·제출기한(deadline) 칸에 날짜를 적고, 적은 칸 수를 반환한다.

    결과 화면에서 사용자가 직접 입력·수정한 값이므로 기존 값을 덮어쓴다.
    """
    if key not in _DATE_KEYS:
        raise ValueError(key)
    ws, header_row = _locate(wb)
    col, filled = _COL[key], 0
    for row_idx in range(max(first, header_row + 1), last + 1):
        cell = ws.cell(row=row_idx, column=col)
        cell.value = _to_date(value)
        cell.number_format = _DATE_FORMAT
        filled += 1
    return filled
