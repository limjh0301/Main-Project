from extractor.parser import parse_request

SAMPLE = """국 회 요 구 자 료

요구서번호 : 0001234567
소관위원회 : 기획재정위원회
요구의원 : 을지문덕 의원(칼퇴원한당, 조퇴도 원할시갑)
요구일자 : 2024. 1. 1.
제출기한 : 2024. 2. 1. 까지
요구자 : 박삼관 보좌관
이메일 : admin@yogu.work

아래 자료를 제출하여 주시기 바랍니다.

1. 최근 5년간 직원 칼퇴 내역 및 부서별 초과근무 시간 집계 자료 일체를
포함한 상세 내역 (연도별, 월별 구분)
2. 최근 3년간 유연근무제 운영 현황

붙임 : 없음.  끝.
"""


def test_parse_fields():
    parsed = parse_request(SAMPLE)
    assert parsed.doc_no == "0001234567"
    assert parsed.committee == "기획재정위원회"
    assert parsed.member == "을지문덕"
    assert parsed.party == "칼퇴원한당"
    assert parsed.district == "조퇴도 원할시갑"
    assert parsed.request_date == "2024-01-01"
    assert parsed.deadline == "2024.02.01"
    assert parsed.requester == "박삼관"
    assert parsed.email == "admin@yogu.work"


def test_multiline_item_not_truncated():
    parsed = parse_request(SAMPLE)
    # PDF 줄바꿈으로 잘린 문장이 이어붙어야 한다
    assert parsed.items[0] == (
        "1. 최근 5년간 직원 칼퇴 내역 및 부서별 초과근무 시간 집계 자료 일체를 "
        "포함한 상세 내역 (연도별, 월별 구분)"
    )
    assert parsed.items[1] == "2. 최근 3년간 유연근무제 운영 현황"


def test_items_stop_at_boilerplate():
    parsed = parse_request("1. 실제 요구자료 항목입니다\n붙임 : 없음. 끝.")
    assert parsed.items == ["1. 실제 요구자료 항목입니다"]


def test_empty_text():
    parsed = parse_request("")
    assert parsed.doc_no == ""
    assert parsed.items == []
