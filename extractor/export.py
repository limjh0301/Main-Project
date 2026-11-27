"""업무 분장내역 엑셀 — 결과 화면에서 최종 확인한 배분을 부서별로 정리해 내보낸다.

화면의 최종 상태(바꾼 부서·담당자, 기제출 체크)를 받아 세 시트로 만든다.
  분장내역   : 질의마다 부서·담당자·요구서·질의 내용·제출기한·기제출·비고 (부서 순 → 요구서 → 질의 순)
  부서별 요약: 부서마다 총괄담당자·질의 수·작성 요청·기제출 갈음·가장 이른 제출기한·담당자
  해당없음   : 우리 기관 비해당 등으로 배분하지 않은 질의
"""

import re
from collections import OrderedDict
from datetime import date

from extractor.assign import NA_DEPT, ORG

TITLE = "국회 요구자료 업무 분장내역"
MAIN_COLUMNS = [("부서", 16), ("담당자", 10), ("요구서 번호", 13), ("요구의원", 10), ("요구 제목", 28),
                ("질의 번호", 10), ("질의 내용", 70), ("제출기한", 11), ("기제출", 9), ("비고", 28)]
SUMMARY_COLUMNS = [("부서", 18), ("총괄담당자", 11), ("질의 수", 8), ("작성 요청", 9), ("기제출 갈음", 10),
                   ("가장 이른 제출기한", 15), ("담당자", 40)]
NA_COLUMNS = [("요구서 번호", 13), ("요구 제목", 28), ("질의 번호", 14), ("질의 내용", 70), ("사유", 30)]
_ORDER = [d for _, depts in ORG for d in depts]  # 기본 순서: 본부 순 → 본부 안 부서 순


def _text(v, limit: int = 4000) -> str:
    return v.strip()[:limit] if isinstance(v, str) else ""


def clean(data: dict) -> tuple[list[dict], dict]:
    """화면에서 보낸 분장 데이터 검증 — (질의 행 목록, 부서 → 총괄담당자)."""
    rows = []
    for r in data.get("rows") or []:
        if not isinstance(r, dict):
            continue
        row = {k: _text(r.get(k)) for k in ("dept", "worker", "doc", "member", "title", "key", "text", "due", "src", "note")}
        row["done"] = r.get("done") is True
        if row["dept"] and row["text"]:
            rows.append(row)
    channel = data.get("channel") if isinstance(data.get("channel"), dict) else {}
    return rows, {_text(k, 40): _text(v, 40) for k, v in channel.items() if _text(k, 40)}


def _due(v: str):
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v or "")
    try:
        return date(*map(int, m.groups())) if m else None
    except ValueError:
        return None


def _rank(dept: str, order: list[str]) -> tuple:
    return (order.index(dept) if dept in order else len(order), dept)


def _key_rank(key: str) -> tuple:
    """질의 번호 정렬: '2' < '10' < '[연구기관] 3', '1-2' < '1-10'."""
    sec = re.match(r"^\[(.+?)\]\s*(.*)$", key)
    body = sec.group(2) if sec else key
    return (sec.group(1) if sec else "", [int(n) for n in re.findall(r"\d+", body)] or [0], body)


def build(rows: list[dict], channel: dict, today: date | None = None, order: list[str] | None = None):
    """order: 부서 정렬 순서 (설정에서 바꾼 부서 구성). 없으면 기본 본부 순."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    side = Side(style="thin")
    border = Border(left=side, right=side, top=side, bottom=side)
    head_font, body_font = Font(name="맑은 고딕", size=10, bold=True), Font(name="맑은 고딕", size=9)
    head_fill = PatternFill("solid", fgColor="DDEBF7")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    def sheet(ws, columns, title=None):
        start = 1
        if title:
            ws.cell(row=1, column=1, value=title).font = Font(name="맑은 고딕", size=14, bold=True)
            start = 3
        for c, (name, width) in enumerate(columns, start=1):
            cell = ws.cell(row=start, column=c, value=name)
            cell.font, cell.fill, cell.alignment, cell.border = head_font, head_fill, center, border
            ws.column_dimensions[get_column_letter(c)].width = width
        ws.freeze_panes = f"A{start + 1}"
        return start

    def put(ws, r, values, wide: set[int]):
        for c, v in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=v if v != "" else None)
            cell.font, cell.border = body_font, border
            cell.alignment = left if c in wide else center
            if isinstance(v, date):
                cell.number_format = "yyyy.mm.dd"

    today, order = today or date.today(), order or _ORDER
    wb = Workbook()
    ws = wb.active
    ws.title = "분장내역"
    assigned = sorted((r for r in rows if r["dept"] != NA_DEPT),
                      key=lambda r: (_rank(r["dept"], order), r["doc"], _key_rank(r["key"])))
    start = sheet(ws, MAIN_COLUMNS, f"{TITLE} ({today:%Y.%m.%d} 기준)")
    for i, r in enumerate(assigned, start=start + 1):
        put(ws, i, [r["dept"], r["worker"], r["doc"], r["member"], r["title"], r["key"], r["text"], _due(r["due"]),
                    "기제출" if r["done"] else "", "; ".join(x for x in (r["src"] and f"출처 {r['src']}", r["note"]) if x)],
            wide={5, 7, 10})
    ws.auto_filter.ref = f"A{start}:{get_column_letter(len(MAIN_COLUMNS))}{start + max(len(assigned), 1)}"

    ws2 = wb.create_sheet("부서별 요약")
    sheet(ws2, SUMMARY_COLUMNS)
    by: OrderedDict[str, list[dict]] = OrderedDict()
    for r in assigned:
        by.setdefault(r["dept"], []).append(r)
    for i, (dept, grp) in enumerate(by.items(), start=2):
        todo = [r for r in grp if not r["done"]]
        dues = [d for d in (_due(r["due"]) for r in todo) if d]
        workers = list(OrderedDict.fromkeys(r["worker"] for r in grp if r["worker"]))
        put(ws2, i, [dept, channel.get(dept, ""), len(grp), len(todo), len(grp) - len(todo),
                     min(dues) if dues else None, ", ".join(workers)], wide={7})
    total = len(by) + 2
    put(ws2, total, ["합계", "", len(assigned), sum(not r["done"] for r in assigned),
                     sum(r["done"] for r in assigned), None, ""], wide=set())
    for c in range(1, len(SUMMARY_COLUMNS) + 1):
        ws2.cell(row=total, column=c).font = head_font

    na = [r for r in rows if r["dept"] == NA_DEPT]
    if na:
        ws3 = wb.create_sheet("해당없음")
        sheet(ws3, NA_COLUMNS)
        for i, r in enumerate(sorted(na, key=lambda r: (r["doc"], _key_rank(r["key"]))), start=2):
            put(ws3, i, [r["doc"], r["title"], r["key"], r["text"], r["note"]], wide={2, 4, 5})
    return wb
