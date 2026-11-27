"""부서별 담당자 명단의 구조와 정리(clean). 명단은 앱 설정(data/settings.json, extractor/settings.py)에 보관한다.

  channel  : 부서 → 총괄담당자 (부서의 대외 요구자료를 취합·안내)
  members  : 부서 → 부서원 목록
  tasks    : "부서|업무" → 그 업무를 맡은 부서원 (없으면 분배안에서 총괄담당자가 들어감)
  excluded : 배분에서 뺀 "부서|업무" (일회성 질의 등) — 이 업무로는 더 이상 배분하지 않는다
  custom   : 사용자가 더한 업무 [{dept, task, keywords}] — 키워드가 질의에 있으면 이 부서·업무로 배분
  org      : 본부별 부서 구성 [{name, depts}] — 없으면(None) 기본 구성(assign.ORG)
  merged   : 없앤 부서 → 업무를 넘겨받은 부서 ("" = 넘겨받은 부서 없음 → 그 업무 질의는 '확인 필요')
             조직개편으로 부서 이름을 바꾸거나 통폐합해도 배분표(assign.TABLE)를 고치지 않고 따라가게 한다
"""

import re

from extractor.assign import NA_DEPT, ORG, TABLE

# 본부 색: 기본 본부는 정해진 색(--o0~--o5), 새로 만든 본부는 --o6~--o8을 돌려 쓴다
_DEFAULT_ORG_NAMES = [name for name, _ in ORG]
_EXTRA_COLORS = (6, 7, 8)


def empty() -> dict:
    return {"channel": {}, "tasks": {}, "members": {}, "excluded": [], "custom": [], "org": None, "merged": {}}


def default_org() -> list[dict]:
    return [{"name": n, "depts": list(ds)} for n, ds in ORG]


def resolver(merged: dict | None):
    """부서 이름 → 지금의 부서 이름. 없앤 부서는 넘겨받은 부서로(여러 번 통합돼도 끝까지 따라감), 넘겨받은 곳이 없으면 ""."""
    merged = merged or {}

    def resolve(dept: str) -> str:
        seen = set()
        while dept in merged and dept not in seen:
            seen.add(dept)
            dept = merged[dept]
        return "" if dept in seen else dept

    return resolve


def tasks(merged: dict | None = None) -> list[tuple[str, str]]:
    """배분표의 (부서, 업무) 목록 — 해당없음·특수 사례 등 부서가 아닌 배분 결과와 없앤 부서의 업무는 뺀다."""
    resolve, seen = resolver(merged), []
    for _, _, dept, task in TABLE:
        dept = resolve(dept) if dept else ""
        if dept and dept != NA_DEPT and (dept, task) not in seen:
            seen.append((dept, task))
    return seen


def org(data: dict | None = None) -> list[dict]:
    """화면용 본부별 부서 목록 — i: 본부 순서, c: 색 번호(--o{c})."""
    groups = (data or {}).get("org") or default_org()
    out, extra = [], 0
    for i, g in enumerate(groups):
        if g["name"] in _DEFAULT_ORG_NAMES:
            color = _DEFAULT_ORG_NAMES.index(g["name"])
        else:
            color, extra = _EXTRA_COLORS[extra % len(_EXTRA_COLORS)], extra + 1
        out.append({"name": g["name"], "depts": list(g["depts"]), "i": i, "c": color})
    return out


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
    roster["org"] = _clean_org(data.get("org"), text)
    merged = data.get("merged") if isinstance(data.get("merged"), dict) else {}
    roster["merged"] = {text(k): text(v) for k, v in merged.items()
                        if text(k) and isinstance(v, str) and text(k) != text(v) and "|" not in text(k) + text(v)}
    return roster


def _clean_org(groups, text) -> list[dict] | None:
    """[{name, depts}] — 빈 본부는 빼고, 한 부서는 한 본부에만. 형식이 맞지 않거나 비면 None(기본 구성)."""
    if not isinstance(groups, list):
        return None
    out, seen = [], set()
    for g in groups:
        if not isinstance(g, dict) or not text(g.get("name")) or not isinstance(g.get("depts"), list):
            continue
        depts = [text(d) for d in g["depts"] if text(d) and "|" not in text(d) and text(d) != NA_DEPT]
        depts = [d for d in dict.fromkeys(depts) if d not in seen]
        seen.update(depts)
        if depts:
            out.append({"name": text(g["name"]), "depts": depts})
    return out or None
