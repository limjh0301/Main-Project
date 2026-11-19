"""앱 설정 저장소 — 담당자 명단·업무 추가/제외·배분 추가 규칙을 `data/settings.json`에 보관한다.

담당자 실명이 들어가므로 data/ 폴더는 저장소(git)에 올리지 않는다. 설정은 앱 설정 화면(/settings)에서
고치며, 저장 즉시 다음 파일 처리부터 반영된다 (앱 재시작 불필요).

저장 내용
  channel  : 부서 → 총괄담당자
  tasks    : "부서|업무" → 담당자
  members  : 부서 → 부서원 목록
  excluded : 배분에서 뺀 "부서|업무" 목록
  custom   : 추가한 업무 [{dept, task, keywords}]
  rules    : 배분 추가 규칙 [{keyword, dept, added, basis}] — 기본 규칙보다 먼저 적용

save()는 임시 파일에 쓴 뒤 os.replace로 바꿔 끼워, 저장 중 꺼져도 파일이 깨지지 않게 한다.
"""

import json
import os
import re

from extractor import roster

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
FILE_NAME = "settings.json"


def path() -> str:
    return os.path.join(DATA_DIR, FILE_NAME)


def empty() -> dict:
    return {**roster.empty(), "rules": []}


def exists() -> bool:
    return os.path.isfile(path())


def _text(v, limit: int = 40) -> str:
    return v.strip()[:limit] if isinstance(v, str) else ""


def clean_rules(rules) -> list[dict]:
    """[{keyword, dept, added, basis}] — 키워드 2글자 이상, 같은 키워드는 처음 것만."""
    out, seen = [], set()
    for r in rules if isinstance(rules, list) else []:
        if not isinstance(r, dict):
            continue
        keyword, dept = _text(r.get("keyword")), _text(r.get("dept"))
        if len(keyword) < 2 or not dept or keyword in seen:
            continue
        seen.add(keyword)
        added = _text(r.get("added"), 10)
        out.append({"keyword": keyword, "dept": dept,
                    "added": added if re.fullmatch(r"\d{4}-\d{2}-\d{2}", added) else "",
                    "basis": _text(r.get("basis"), 200)})
    return out


def clean(data) -> dict:
    data = data if isinstance(data, dict) else {}
    return {**roster.clean(data), "rules": clean_rules(data.get("rules"))}


def load() -> dict:
    """설정 파일을 읽는다. 없거나 깨진 파일이면 기본값(빈 명단)으로 시작한다."""
    try:
        with open(path(), encoding="utf-8") as f:
            return clean(json.load(f))
    except (OSError, ValueError):
        return empty()


def save(data) -> dict:
    """설정을 검증해 저장하고, 저장된 내용을 돌려준다."""
    cleaned = clean(data)
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path())
    return cleaned
