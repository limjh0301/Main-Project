"""부서별 담당자 명단의 구조와 정리(clean). 명단은 앱 설정(data/settings.json, extractor/settings.py)에 보관한다.

  channel  : 부서 → 총괄담당자 (부서의 대외 요구자료를 취합·안내)
  members  : 부서 → 부서원 목록
  tasks    : "부서|업무" → 그 업무를 맡은 부서원 (없으면 분배안에서 총괄담당자가 들어감)
  excluded : 배분에서 뺀 "부서|업무" (일회성 질의 등) — 이 업무로는 더 이상 배분하지 않는다
  custom   : 사용자가 더한 업무 [{dept, task, keywords}] — 키워드가 질의에 있으면 이 부서·업무로 배분
"""

import re

from extractor.assign import NA_DEPT, TABLE


def empty() -> dict:
    return {"channel": {}, "tasks": {}, "members": {}, "excluded": [], "custom": []}


def tasks() -> list[tuple[str, str]]:
    """배분표의 (부서, 업무) 목록 — 해당없음 등 부서가 아닌 배분 결과는 뺀다."""
    seen = []
    for _, _, dept, task in TABLE:
        if dept and dept != NA_DEPT and (dept, task) not in seen:
            seen.append((dept, task))
    return seen


def keywords(text: str) -> list[str]:
    """'법률, 소송·자문' → ['법률', '소송', '자문'] (2글자 이상만)."""
    return list(dict.fromkeys(k.strip() for k in re.split(r"[,，、·/]", text or "") if len(k.strip()) >= 2))


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
