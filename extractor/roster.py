"""부서별 담당자 명단 — 관리대장 파일의 '부서별 담당자' 시트로 읽고 쓴다.

명단은 코드에 두지 않고 대장 파일에 함께 보관한다. 대장을 올리면 이 시트를 읽어 배분안의
담당자를 채우고, 화면에서 고친 명단은 다운로드하는 대장에 다시 적는다. 엑셀에서 직접 고쳐도 된다.

시트 열: 본부 | 부서 | 구분 | 업무 | 담당자 | 키워드
  구분 '총괄담당자': 부서의 대외 요구자료를 취합·안내하는 담당자 (예전 대장의 '창구'도 읽는다)
  구분 '업무'      : 배분표의 (부서, 업무)를 맡은 실무자
  구분 '추가 업무' : 사용자가 더한 업무 — 키워드(쉼표로 구분)가 질의에 있으면 이 부서·업무로 배분
  구분 '제외'      : 배분표에서 뺀 업무 (일회성 질의 등) — 이 업무로는 더 이상 배분하지 않는다
  구분 '부서원'    : 담당자 선택 목록에 추가로 보여 줄 부서원
"""

import re

from extractor.assign import NA_DEPT, ORG, TABLE

SHEET_NAME = "부서별 담당자"
HEADER = ["본부", "부서", "구분", "업무", "담당자", "키워드"]
_WIDTHS = [14, 22, 12, 40, 16, 30]
CHANNEL_KIND = "총괄담당자"
_CHANNEL_KINDS = (CHANNEL_KIND, "창구")  # '창구'는 예전 표현
CUSTOM_KIND = "추가 업무"
EXCLUDED_KIND = "제외"
CHANNEL_TASK = "요청 취합·안내"


def empty() -> dict:
    return {"channel": {}, "tasks": {}, "members": {}, "excluded": [], "custom": []}


def tasks() -> list[tuple[str, str]]:
    """배분표의 (부서, 업무) 목록 — 해당없음 등 부서가 아닌 배분 결과는 뺀다."""
    seen = []
    for _, _, dept, task in TABLE:
        if dept and dept != NA_DEPT and (dept, task) not in seen:
            seen.append((dept, task))
    return seen


def org_of(dept: str) -> str:
    return next((name for name, depts in ORG if dept in depts), "기타")


def keywords(text: str) -> list[str]:
    """'법률, 소송·자문' → ['법률', '소송', '자문'] (2글자 이상만)."""
    return list(dict.fromkeys(k.strip() for k in re.split(r"[,，、·/]", text or "") if len(k.strip()) >= 2))


def _dept_order(roster: dict) -> list[str]:
    """본부 순서 → 배분표에만 있는 부서 → 명단에만 있는 부서."""
    order = [d for _, depts in ORG for d in depts]
    extra = [d for d, _ in tasks()] + list(roster["channel"]) + list(roster["members"])
    extra += [c["dept"] for c in roster["custom"]]
    for dept in extra:
        if dept not in order:
            order.append(dept)
    return order


def read(wb) -> dict:
    """대장의 담당자 시트를 읽는다. 시트가 없으면 빈 명단. 키워드 열이 없는 예전 시트도 읽는다."""
    roster = empty()
    if SHEET_NAME not in wb.sheetnames:
        return roster
    ws = wb[SHEET_NAME]
    for row in ws.iter_rows(min_row=2, max_col=len(HEADER), values_only=True):
        row = list(row) + [None] * (len(HEADER) - len(row))
        _, dept, kind, task, name, kws = (str(v).strip() if v is not None else "" for v in row)
        if not dept:
            continue
        if kind == EXCLUDED_KIND and task:
            roster["excluded"].append(f"{dept}|{task}")
        elif kind == CUSTOM_KIND and task:
            roster["custom"].append({"dept": dept, "task": task, "keywords": keywords(kws)})
        if not name:
            continue
        if kind in _CHANNEL_KINDS:
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
    excluded = data.get("excluded") if isinstance(data.get("excluded"), list) else []
    roster["excluded"] = list(dict.fromkeys(text(k) for k in excluded if "|" in text(k)))
    custom = data.get("custom") if isinstance(data.get("custom"), list) else []
    seen = set()
    for c in custom:
        if not isinstance(c, dict) or not text(c.get("dept")) or not text(c.get("task")):
            continue
        key = (text(c["dept"]), text(c["task"]))
        kws = c.get("keywords")
        kws = keywords(", ".join(k for k in kws if isinstance(k, str)) if isinstance(kws, list) else text(kws))
        if key not in seen:
            seen.add(key)
            roster["custom"].append({"dept": key[0], "task": key[1], "keywords": kws})
    return roster


def write(wb, roster: dict) -> None:
    """담당자 시트를 명단으로 다시 만든다. 배분표의 모든 업무를 빈 담당자 칸까지 포함해 적는다."""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    roster = {**empty(), **roster}
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

    excluded = set(roster["excluded"])
    custom_keys = {(c["dept"], c["task"]) for c in roster["custom"]}
    by_dept: dict[str, list[tuple]] = {}
    for dept, task in tasks():
        kind = EXCLUDED_KIND if f"{dept}|{task}" in excluded else "업무"
        by_dept.setdefault(dept, []).append((kind, task, roster["tasks"].get(f"{dept}|{task}", ""), ""))
    for c in roster["custom"]:
        by_dept.setdefault(c["dept"], []).append(
            (CUSTOM_KIND, c["task"], roster["tasks"].get(f'{c["dept"]}|{c["task"]}', ""), ", ".join(c["keywords"])))
    for key, name in roster["tasks"].items():  # 배분표에도 추가 업무에도 없는 업무(예전 명단)도 보존
        dept, _, task = key.partition("|")
        if (dept, task) not in tasks() and (dept, task) not in custom_keys:
            by_dept.setdefault(dept, []).append(("업무", task, name, ""))

    rows = []
    for dept in _dept_order(roster):
        lines = [(CHANNEL_KIND, CHANNEL_TASK, roster["channel"].get(dept, ""), "")]
        lines += by_dept.get(dept, [])
        lines += [("부서원", "", n, "") for n in roster["members"].get(dept, [])]
        rows += [(org_of(dept), dept, *line) for line in lines]
    for r, values in enumerate(rows, start=2):
        for c, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=c, value=value or None)
            cell.font = Font(name="맑은 고딕", size=10)
            cell.border = border
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADER))}{max(len(rows) + 1, 2)}"
