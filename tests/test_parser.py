from extractor.parser import parse_request

SAMPLE = """국 회 요 구 자 료

문서번호 : 기재위 제2026-153호
수신 : 기획재정부 세제실

위원회 : 기획재정위원회
요구위원 : 홍길동 의원
요구일자 : 2026. 8. 15.
제출기한 : 2026. 8. 25. 까지

아래 자료를 제출하여 주시기 바랍니다.

1. 2024~2026년 연도별 국세 감면 현황
2. 최근 3년간 조세특례제한법 개정 연혁

붙임 : 없음.  끝.
"""


def test_parse_fields():
    parsed = parse_request(SAMPLE)
    assert parsed.doc_no == "기재위 제2026-153호"
    assert parsed.committee == "기획재정위원회"
    assert parsed.member == "홍길동"
    assert parsed.request_date == "2026-08-15"
    assert parsed.deadline == "2026-08-25"
    assert parsed.department == "기획재정부 세제실"


def test_parse_items():
    parsed = parse_request(SAMPLE)
    assert parsed.items == [
        "2024~2026년 연도별 국세 감면 현황",
        "최근 3년간 조세특례제한법 개정 연혁",
    ]


def test_items_exclude_boilerplate():
    parsed = parse_request("○ 붙임 문서를 참고하세요\n1. 실제 요구자료 항목입니다")
    assert parsed.items == ["실제 요구자료 항목입니다"]


def test_empty_text():
    parsed = parse_request("")
    assert parsed.doc_no == ""
    assert parsed.items == []
