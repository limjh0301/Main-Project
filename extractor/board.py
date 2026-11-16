"""처리 결과 → 분배안 화면(보드) 데이터.

요구서마다 질의를 배분 단위로 나눠 배분하고(assign), 화면이 바로 그릴 수 있는 형태로 만든다.
담당자 이름은 넣지 않고 (부서, 업무)만 넣는다 — 화면이 명단(roster)으로 이름을 붙인다.
"""

import re

from extractor import assign, roster

_PERIOD = re.compile(r"^\(최근\s*(\d+)년간?\)\s*")


def _iso(value: str) -> str:
    m = re.match(r"^(\d{4})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})", value or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""


def _split_text(text: str) -> tuple[str, str, list[str]]:
    """(기간, 본문, 세부 요청). '(최근5년간) …' → '5년'은 따로, ' / '나 ' - '로 이어진 세부 요청은 목록으로."""
    main, *rest = text.split(" / ") if " / " in text else re.split(r"\s+-\s+", text)
    m = _PERIOD.match(main)
    period = f"{m.group(1)}년" if m else ""
    return period, main[m.end():] if m else main, [x.lstrip("-*· ").strip() for x in rest if x.strip()]


def questions(parsed: dict, attachments: list, title: str) -> list[dict]:
    """요구서 1건의 질의를 배분한다. 첨부 한글파일이 있으면 첨부 항목이 질의다."""
    if attachments:
        items = [item for a in attachments for item in a.items]
        return assign.plan(assign.attachment_items(items, title), use_siblings=False)
    _, qs = assign.request_items(parsed.get("items") or [])
    return assign.plan(qs, use_siblings=True)


def build(entries: list[dict], names: dict) -> dict:
    """entries: tag·parsed·title·questions·rows·duplicate·filename·method 를 가진 요구서 목록."""
    reqs, items, merged = [], [], 0
    for e in entries:
        p = e["parsed"]
        reqs.append({
            "tag": e["tag"], "doc": p.get("doc_no") or "", "member": p.get("member") or "",
            "label": f'{p["member"]} 의원' if p.get("member") else (e["title"] or e["filename"]),
            "title": e["title"] or e["filename"], "n": len(e["questions"]),
            "date": _iso(p.get("request_date", "")), "due": _iso(p.get("deadline", "")),
            "from": p.get("from_name", []), "rows": e["rows"], "duplicate": e["duplicate"],
            "filename": e["filename"], "method": e["method"],
        })
        by_key = {}
        for q in e["questions"]:
            period, main, rest = _split_text(q["text"])
            sec = re.match(r"^\[(.+?)\]\s*(.*)$", q["key"])
            item = {
                "id": f'{e["tag"]}|{q["key"]}', "req": e["tag"], "key": q["key"],
                "sec": sec.group(1) if sec else "", "no": sec.group(2) if sec else q["key"],
                "period": period, "main": main, "rest": rest, "dept": q["dept"], "task": q["task"],
                "amb": q["ambiguous"], "why": q["why"],
            }
            orig = by_key.get(q.get("dup_of"))
            if orig and orig["dept"] == item["dept"]:
                # 같은 요구서 안의 똑같은 질의는 원 질의에 합쳐 한 번만 보여 준다 (부서를 옮기면 함께 옮겨짐)
                orig.setdefault("same", []).append(q["key"])
                merged += 1
                continue
            by_key[q["key"]] = item
            items.append(item)
    return {
        "reqs": reqs, "items": items, "merged": merged, "roster": names,
        "org": [{"name": n, "depts": ds} for n, ds in assign.ORG],
        "fams": [{"name": n, "var": v, "depts": ds} for n, v, ds in assign.FAMILIES],
        "tasks": [{"dept": d, "task": t} for d, t in roster.tasks()],
    }
