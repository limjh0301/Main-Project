from datetime import datetime

from extractor import history
from extractor.ledger import append_rows, create_ledger, records

PAST = [
    {"doc_no": "0007000001", "request_date": "2025-09-18", "member": "을지문덕", "submitted": "2025-09-25",
     "content": "[2025 국정감사 공통요구자료]\n1. (최근3년간) 예산서, 결산서\n2. 직제표\n"
                "3. 기술이전 건수·기술료 수입 추이\n- 연도별\n4. 법인카드 사용내역(최근 3년간)"},
    {"doc_no": "0007000002", "request_date": "2025-10-01", "member": "", "submitted": "",
     "content": "직원 칼퇴 현황"},
]


def test_split_questions_keeps_detail_lines_with_question():
    title, qs = history.split_questions(PAST[0]["content"])
    assert title == "2025 국정감사 공통요구자료"
    assert qs == ["(최근3년간) 예산서, 결산서", "직제표", "기술이전 건수·기술료 수입 추이 - 연도별",
                  "법인카드 사용내역(최근 3년간)"]


def test_leading_notes_are_not_questions():
    assert history.split_questions("[병가 현황]\n※ 대상: 연구회\n1. 병가 규정\n- 조문\n2. 사용 현황") == (
        "병가 현황", ["병가 규정 - 조문", "사용 현황"])


def test_match_kinds():
    idx = history.Index(PAST)
    assert idx.match("1. (최근3년간) 예산서, 결산서")[0]["kind"] == "동일"
    assert idx.match("(최근5년간) 예산서 결산서")[0]["kind"] == "기간만 다름"
    assert idx.match("직제표")[0]["kind"] == "동일"  # 짧아도 동일하면 이어 준다
    similar = idx.match("(최근5년간) 특허·기술이전(기술료) 실적")
    assert similar and similar[0]["kind"].startswith("유사") and similar[0]["doc"] == "0007000001"
    assert similar[0]["title"] == "2025 국정감사 공통요구자료" and similar[0]["submitted"] == "2025-09-25"
    assert idx.match("연구실 안전사고 발생 현황") == []


def test_match_returns_each_request_once():
    idx = history.Index(PAST + [{**PAST[0], "doc_no": "0007000003"}])
    got = idx.match("(최근3년간) 예산서, 결산서", limit=5)
    assert [g["doc"] for g in got] == ["0007000001", "0007000003"]


def test_empty_index():
    assert history.Index([]).match("직제표") == []


def test_records_from_ledger():
    wb = create_ledger()
    append_rows(wb, [{"doc_no": "0007000001", "request_date": "2025-09-18", "member": "을지문덕",
                      "content": PAST[0]["content"]}])
    wb.active.cell(row=4, column=9, value=datetime(2025, 9, 25))  # 제출일자는 직접 적는 칸
    assert records(wb) == [{"doc_no": "0007000001", "request_date": "2025-09-18", "deadline": "", "member": "을지문덕",
                            "content": PAST[0]["content"], "submitted": "2025-09-25"}]
