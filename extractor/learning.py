"""배분 정정 이력 학습 — 담당자가 고친 배분을 쌓고, 다음 배분에 반영한다.

  '배분 이력' 시트 : 대장 파일에 둔다. 저장·다운로드할 때 질의마다 모델 배분과 확정 부서를 기록
                    (같은 요구서는 최신으로 교체). 정확도·규칙 제안의 재료
  배분 추가 규칙   : 사용자가 승인한 키워드 → 부서 규칙. 앱 설정(settings.json)에 보관하며 기본 규칙보다 먼저 적용

반영 방식
  1) 추가 규칙: 질의에 키워드가 있으면 그 부서
  2) 이전 정정: 예전에 부서를 고친 질의와 글자가 같거나 기간만 다르면 고친 부서
제안 방식: 같은 부서로 2번 이상 고친 질의들에 공통으로 들어 있고, 그 말이 들어간 질의는 대부분(80% 이상)
그 부서로 확정된 단어를 '키워드 → 부서' 규칙 후보로 보여 준다.
"""

import re
from collections import Counter, defaultdict
from datetime import date

from extractor import history
from extractor.assign import NA_DEPT

LOG_SHEET = "배분 이력"
LOG_HEADER = ["기록일", "요구서 번호", "질의 번호", "질의", "모델 배분", "확정 부서"]

SUGGEST_MIN = 2         # 같은 부서로 고친 횟수가 이 이상인 단어만 제안
SUGGEST_PRECISION = 0.8  # 그 단어가 들어간 질의 중 그 부서로 확정된 비율
_STOP = {"현황", "자료", "관련", "내역", "최근", "년간", "연도별", "기관별", "기관", "사항", "결과", "목록", "일체", "포함",
         "제출", "대한", "위한", "여부", "기준", "경우", "사본", "등의", "전체", "운영", "관리", "실적", "계획", "추진", "기간",
         "사용", "대상", "내용", "건수", "인원", "금액", "일자", "사유", "구분", "해당", "조치", "처리", "발생", "주요"}
_TOKEN = re.compile(r"[가-힣A-Za-z]{2,}")


def _main(text: str) -> str:
    """질의 본문 — 세부 요청(" / …", " - …")을 뗀 앞부분."""
    return re.split(r" / |\s+-\s+", text)[0]


def _sheet(wb, name: str, header: list[str], widths: list[int]):
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    if name in wb.sheetnames:
        return wb[name]
    ws = wb.create_sheet(name)
    for c, (h, w) in enumerate(zip(header, widths), start=1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = Font(name="맑은 고딕", size=11, bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEBF7")
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A2"
    return ws


def _rows(wb, name: str, width: int) -> list[list[str]]:
    if name not in wb.sheetnames:
        return []
    out = []
    for row in wb[name].iter_rows(min_row=2, max_col=width, values_only=True):
        values = ["" if v is None else (v.isoformat()[:10] if hasattr(v, "isoformat") else str(v).strip()) for v in row]
        if any(values):
            out.append(values)
    return out


# ---------------- 이력 ----------------
def read_log(wb) -> list[dict]:
    keys = ["date", "doc", "key", "text", "model", "final"]
    return [dict(zip(keys, r)) for r in _rows(wb, LOG_SHEET, len(LOG_HEADER))]


def write_log(wb, entries: list[dict]) -> int:
    """질의별 배분 결과를 기록한다. 같은 요구서 번호의 예전 기록은 지우고 새로 적는다."""
    entries = [e for e in entries if e.get("doc") and e.get("text")]
    docs = {e["doc"] for e in entries}
    kept = [r for r in read_log(wb) if r["doc"] not in docs]
    today = date.today().isoformat()
    rows = kept + [{"date": today, **e} for e in entries]
    if LOG_SHEET in wb.sheetnames:
        del wb[LOG_SHEET]
    ws = _sheet(wb, LOG_SHEET, LOG_HEADER, [11, 13, 12, 70, 16, 16])
    for r in rows:
        ws.append([r["date"], r["doc"], r["key"], r["text"], r["model"], r["final"]])
    return len(entries)


def stats(log: list[dict]) -> dict:
    """모델 배분이 그대로 확정된 비율 (배분 정확도)."""
    total = len(log)
    kept = sum(r["model"] == r["final"] for r in log)
    return {"total": total, "kept": kept, "rate": round(kept / total * 100) if total else None}


def suggestions(log: list[dict], rules: list[dict], limit: int = 5) -> list[dict]:
    """반복된 정정에서 '키워드 → 부서' 규칙 후보를 찾는다."""
    have = {r["keyword"] for r in rules}
    # 세부 요청(" / …", " - …")에는 흔한 말이 많으므로 질의 본문에서만 단어를 고른다
    tokens = [set(_TOKEN.findall(_main(r["text"]))) - _STOP for r in log]
    seen_with: dict[str, Counter] = defaultdict(Counter)  # 단어 → 확정 부서별 질의 수
    for r, toks in zip(log, tokens):
        for t in toks:
            seen_with[t][r["final"]] += 1
    moved: dict[tuple[str, str], list[str]] = defaultdict(list)  # (단어, 부서) → 고친 질의들
    for r, toks in zip(log, tokens):
        if r["model"] != r["final"] and r["final"]:
            for t in toks:
                moved[(t, r["final"])].append(r["text"])
    out = []
    for (tok, dept), texts in moved.items():
        n = len(set(texts))
        total = sum(seen_with[tok].values())
        if tok in have or n < SUGGEST_MIN or seen_with[tok][dept] / total < SUGGEST_PRECISION:
            continue
        out.append({"keyword": tok, "dept": dept, "count": n, "total": total, "examples": sorted(set(texts))[:2]})
    out.sort(key=lambda s: (-s["count"], -s["total"], -len(s["keyword"])))
    # 같은 정정 묶음에서 나온 단어는 하나만 (예: '복무점검'·'점검' 중 긴 것)
    picked, used = [], set()
    for s in out:
        key = (s["dept"], tuple(s["examples"]))
        if key in used:
            continue
        used.add(key)
        picked.append(s)
    return picked[:limit]


# ---------------- 반영 ----------------
class Learner:
    """추가 규칙과 이전 정정을 새 배분에 반영한다."""

    def __init__(self, log: list[dict], rules: list[dict]):
        self.rules = rules
        corrected = [r for r in log if r["model"] != r["final"] and r["final"]]
        # 세부 요청은 요구서마다 조금씩 달라지므로 질의 본문끼리 비교한다
        self._index = history.Index([{"doc_no": r["doc"], "content": _main(r["text"]), "member": r["final"]}
                                     for r in corrected])

    def apply(self, questions: list[dict]) -> list[dict]:
        for q in questions:
            if q["dept"] == NA_DEPT and q.get("section"):
                continue  # 기관 유형 비해당 섹션은 그대로
            rule = next((r for r in self.rules if r["keyword"] in q["text"]), None)
            if rule:
                if rule["dept"] != q["dept"]:
                    q.update(dept=rule["dept"], task="", ambiguous=False, why=f"‘{rule['keyword']}’ 추가 규칙")
                continue
            hit = next((m for m in self._index.match(_main(q["text"]), limit=1) if m["kind"] in ("동일", "기간만 다름")), None)
            if hit and hit["member"] != q["dept"]:  # member 자리에 고친 부서를 넣어 두었다
                q.update(dept=hit["member"], task="", ambiguous=False, why=f"이전 정정 반영 ({hit['doc']})")
        return questions
