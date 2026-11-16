"""부서별 담당자 명단 — 관리대장 파일의 '부서별 담당자' 시트로 읽고 쓴다.

명단은 코드에 두지 않고 대장 파일에 함께 보관한다. 대장을 올리면 이 시트를 읽어 배분안의
담당자를 채우고, 화면에서 고친 명단은 다운로드하는 대장에 다시 적는다. 엑셀에서 직접 고쳐도 된다.

시트 열: 본부 | 부서 | 구분 | 업무 | 담당자
  구분 '창구'  : 부서의 대외 요구자료 창구(요청 취합·안내) 담당자
  구분 '업무'  : 배분표의 (부서, 업무)를 맡은 실무자
  구분 '부서원': 담당자 선택 목록에 추가로 보여 줄 부서원
"""

from extractor.assign import NA_DEPT, ORG, TABLE

SHEET_NAME = "부서별 담당자"
HEADER = ["본부", "부서", "구분", "업무", "담당자"]
_WIDTHS = [14, 22, 8, 40, 16]
CHANNEL_TASK = "요청 취합·안내"


def empty() -> dict:
    return {"channel": {}, "tasks": {}, "members": {}}


def tasks() -> list[tuple[str, str]]:
    """배분표의 (부서, 업무) 목록 — 해당없음 등 부서가 아닌 배분 결과는 뺀다."""
    seen = []
    for _, _, dept, task in TABLE:
        if dept and dept != NA_DEPT and (dept, task) not in seen:
            seen.append((dept, task))
    return seen


def org_of(dept: str) -> str:
    return next((name for name, depts in ORG if dept in depts), "기타")


def _dept_order(roster: dict) -> list[str]:
    """본부 순서 → 배분표에만 있는 부서 → 명단에만 있는 부서."""
    order = [d for _, depts in ORG for d in depts]
    for dept in [d for d, _ in tasks()] + list(roster["channel"]) + list(roster["members"]):
        if dept not in order:
            order.append(dept)
    return order


def read(wb) -> dict:
    """대장의 담당자 시트를 읽는다. 시트가 없으면 빈 명단."""
    roster = empty()
    if SHEET_NAME not in wb.sheetnames:
        return roster
    ws = wb[SHEET_NAME]
    for row in ws.iter_rows(min_row=2, max_col=len(HEADER), values_only=True):
        _, dept, kind, task, name = (str(v).strip() if v is not None else "" for v in row)
        if not dept or not name:
            continue
        if kind == "창구":
            roster["channel"][dept] = name
        elif kind == "부서원":
            roster["members"].setdefault(dept, [])
            if name not in roster["members"][dept]:
                roster["members"][dept].append(name)
        elif task:
            roster["tasks"][f"{dept}|{task}"] = name
    return roster


def clean(data: dict) -> dict:
    """화면에서 보낸 명단을 검증·정리한다 (문자열만, 빈 값 제거)."""
    def text(v) -> str:
        return v.strip()[:40] if isinstance(v, str) else ""

    roster = empty()
    for key in ("channel", "tasks"):
        src = data.get(key) if isinstance(data.get(key), dict) else {}
        roster[key] = {text(k): text(v) for k, v in src.items() if text(k) and text(v)}
    members = data.get("members") if isinstance(data.get("members"), dict) else {}
    for dept, names in members.items():
        names = [text(n) for n in names] if isinstance(names, list) else []
        if text(dept) and any(names):
            roster["members"][text(dept)] = list(dict.fromkeys(n for n in names if n))
    return roster


def write(wb, roster: dict) -> None:
    """담당자 시트를 명단으로 다시 만든다. 배분표의 모든 업무를 빈 담당자 칸까지 포함해 적는다."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    ws = wb.create_sheet(SHEET_NAME)
    side = Side(style="thin")
    border = Border(left=side, right=side, top=side, bottom=side)
    for c, (name, width) in enumerate(zip(HEADER, _WIDTHS), start=1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.font = Font(name="맑은 고딕", size=11, bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEBF7")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border
        ws.column_dimensions[get_column_letter(c)].width = width

    by_dept: dict[str, list[tuple[str, str, str]]] = {}
    for dept, task in tasks():
        by_dept.setdefault(dept, []).append(("업무", task, roster["tasks"].get(f"{dept}|{task}", "")))
    for key, name in roster["tasks"].items():  # 배분표에 없는 업무(예전 명단)도 보존
        dept, _, task = key.partition("|")
        if (dept, task) not in tasks():
            by_dept.setdefault(dept, []).append(("업무", task, name))

    rows = []
    for dept in _dept_order(roster):
        lines = [("창구", CHANNEL_TASK, roster["channel"].get(dept, ""))]
        lines += by_dept.get(dept, [])
        lines += [("부서원", "", n) for n in roster["members"].get(dept, [])]
        rows += [(org_of(dept), dept, *line) for line in lines]
    for r, values in enumerate(rows, start=2):
        for c, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=value or None)
            cell.font = Font(name="맑은 고딕", size=10)
            cell.border = border
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:E{max(len(rows) + 1, 2)}"
