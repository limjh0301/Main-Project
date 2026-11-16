from datetime import date

from extractor import export

ROWS = [
    {"dept": "총무구매실", "worker": "김구매", "doc": "0001", "member": "을지문덕", "title": "공통", "key": "10",
     "text": "관용차량 운영", "due": "2026-10-02", "done": False, "src": "", "note": ""},
    {"dept": "기획실", "worker": "홍길동", "doc": "0001", "member": "을지문덕", "title": "공통", "key": "2",
     "text": "직제표\n- 연락처 포함", "due": "2026-10-02", "done": True, "src": "2025.09.18 「공통」 (0000)", "note": ""},
    {"dept": "기획실", "worker": "홍길동", "doc": "0001", "member": "을지문덕", "title": "공통", "key": "[연구기관] 3",
     "text": "기관평가", "due": "2026-10-02", "done": False, "src": "", "note": "확인 필요"},
    {"dept": "해당없음", "worker": "", "doc": "0001", "member": "", "title": "공통", "key": "[학교] 1",
     "text": "학생 현황", "due": "", "done": False, "src": "", "note": "〈학교〉 섹션 — 우리 기관 비해당"},
]


def _values(ws, start):
    return [[c.value for c in row] for row in ws.iter_rows(min_row=start)]


def test_build_sheets_order_and_summary():
    wb = export.build(ROWS, {"기획실": "홍총괄"}, today=date(2026, 9, 25))
    assert wb.sheetnames == ["분장내역", "부서별 요약", "해당없음"]
    ws = wb["분장내역"]
    assert ws["A1"].value == "국회 요구자료 업무 분장내역 (2026.09.25 기준)"
    rows = _values(ws, 4)
    # 부서 순(기획실 → 총무구매실), 같은 부서는 질의 번호 순
    assert [(r[0], r[5]) for r in rows] == [("기획실", "2"), ("기획실", "[연구기관] 3"), ("총무구매실", "10")]
    assert rows[0][7] == date(2026, 10, 2) and rows[0][8] == "기제출" and rows[0][9].startswith("출처 2025.09.18")
    assert rows[1][9] == "확인 필요"
    summary = _values(wb["부서별 요약"], 2)
    assert summary[0] == ["기획실", "홍총괄", 2, 1, 1, date(2026, 10, 2), "홍길동"]
    assert summary[-1][:5] == ["합계", None, 3, 2, 1]
    assert _values(wb["해당없음"], 2)[0][2:] == ["[학교] 1", "학생 현황", "〈학교〉 섹션 — 우리 기관 비해당"]


def test_clean_drops_bad_rows():
    rows, channel = export.clean({"rows": [{"dept": "기획실", "text": "x", "done": "yes"}, {"dept": "", "text": "y"}, 3],
                                  "channel": {"기획실": "홍", "": "x"}})
    assert len(rows) == 1 and rows[0]["done"] is False and channel == {"기획실": "홍"}
