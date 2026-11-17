"""앱 설정 저장소 — 담당자 명단·업무 추가/제외·배분 추가 규칙을 `data/settings.json`에 보관한다.

담당자 실명이 들어가므로 data/ 폴더는 저장소(git)에 올리지 않는다. 설정은 앱 설정 화면(/settings)에서
고치며, 저장 즉시 다음 파일 처리부터 반영된다 (앱 재시작 불필요).

저장 내용
  channel  : 부서 → 총괄담당자
  tasks    : "부서|업무" → 담당자
  members  : 부서 → 그 밖의 부서원 목록
  excluded : 배분에서 뺀 "부서|업무" 목록
  custom   : 추가한 업무 [{dept, task, keywords}]
  rules    : 배분 추가 규칙 [{keyword, dept, added, basis}] — 기본 규칙보다 먼저 적용

save()는 임시 파일에 쓴 뒤 os.replace로 바꿔 끼우고, 저장 직전 파일을 data/backup/에 남긴다(최근 20개).
"""

import json
import os
import re
from datetime import datetime

from extractor import learning, roster

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
FILE_NAME = "settings.json"
BACKUP_DIR_NAME = "backup"
BACKUP_KEEP = 20
_BACKUP_RE = re.compile(r"^settings_(\d{6})_(\d{6})(?:_\d+)?\.json$")


def path() -> str:
    return os.path.join(DATA_DIR, FILE_NAME)


def backup_dir() -> str:
    return os.path.join(DATA_DIR, BACKUP_DIR_NAME)


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
    """설정 파일을 읽는다. 없으면 기본값(빈 명단). 깨진 파일은 기본값으로 시작하되 파일은 그대로 둔다(저장 시 백업됨)."""
    try:
        with open(path(), encoding="utf-8") as f:
            return clean(json.load(f))
    except (OSError, ValueError):
        return empty()


def _backup_current() -> str | None:
    """현재 설정 파일을 backup/settings_YYMMDD_HHMMSS.json으로 복사하고 오래된 백업을 정리한다."""
    if not exists():
        return None
    os.makedirs(backup_dir(), exist_ok=True)
    stamp = datetime.now().strftime("%y%m%d_%H%M%S")
    target = os.path.join(backup_dir(), f"settings_{stamp}.json")
    n = 1
    while os.path.exists(target):  # 같은 초에 두 번 저장하면 번호를 붙인다
        n += 1
        target = os.path.join(backup_dir(), f"settings_{stamp}_{n}.json")
    with open(path(), "rb") as src, open(target, "wb") as dst:
        dst.write(src.read())
    for name in [b["name"] for b in backups()[BACKUP_KEEP:]]:
        try:
            os.remove(os.path.join(backup_dir(), name))
        except OSError:
            pass
    return os.path.basename(target)


def save(data) -> dict:
    """설정을 검증해 저장하고, 저장된 내용을 돌려준다."""
    cleaned = clean(data)
    os.makedirs(DATA_DIR, exist_ok=True)
    _backup_current()
    tmp = path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path())
    return cleaned


def backups() -> list[dict]:
    """백업 목록 (최신순): name · time(YYYY-MM-DD HH:MM:SS) · size."""
    if not os.path.isdir(backup_dir()):
        return []
    out = []
    for name in os.listdir(backup_dir()):
        m = _BACKUP_RE.match(name)
        if not m:
            continue
        d, t = m.group(1), m.group(2)
        out.append({"name": name, "time": f"20{d[:2]}-{d[2:4]}-{d[4:]} {t[:2]}:{t[2:4]}:{t[4:]}",
                    "size": os.path.getsize(os.path.join(backup_dir(), name))})
    return sorted(out, key=lambda b: b["name"], reverse=True)


def restore(name: str) -> dict:
    """백업 파일의 설정으로 되돌린다 (되돌리기 전 현재 설정도 백업됨). 없는 이름이면 ValueError."""
    if not _BACKUP_RE.match(name or "") or not os.path.isfile(os.path.join(backup_dir(), name)):
        raise ValueError("없는 백업입니다.")
    with open(os.path.join(backup_dir(), name), encoding="utf-8") as f:
        return save(json.load(f))


# ---------------- 대장 엑셀과 주고받기 (이전·인수인계용) ----------------
def from_workbook(wb) -> dict:
    """예전 대장의 '부서별 담당자'·'배분 추가 규칙' 시트에서 설정을 읽는다."""
    return clean({**roster.read(wb), "rules": learning.read_rules(wb)})


def to_workbook(data: dict):
    """설정을 기존 시트 양식('부서별 담당자' + '배분 추가 규칙')의 새 엑셀로 만든다."""
    from openpyxl import Workbook

    data = clean(data)
    wb = Workbook()
    wb.remove(wb.active)
    roster.write(wb, data)
    learning.write_rules(wb, data["rules"])
    return wb


def summary(data: dict) -> dict:
    """설정 요약 (가져오기 확인 창 등에 표시)."""
    return {"channel": len(data["channel"]), "tasks": len(data["tasks"]),
            "members": sum(len(v) for v in data["members"].values()),
            "excluded": len(data["excluded"]), "custom": len(data["custom"]), "rules": len(data["rules"])}
