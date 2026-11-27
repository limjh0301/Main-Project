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


ATTACHMENT = """※ 9월 28일(월)까지 제출
 - 이메일 : test@example.com
기관 개요
 1) 설립근거 및 목적
 2) 연도별 재무상태
  - ①재무상태표
2. 최근 6년간(2021~2026) 감사 조치 관련
1) 국회 지적사항 및 조치내역
 - 결과보고서 별도 제출
2) 감사원 지적사항
3) 관련 기준 및 규정, 지침 등 근거 별첨
3. 소관 법령 목록
4. 복지포인트 지급 현황
 1) 연도별 지급 총액
 2) 산하기관 포함 제출
"""


def test_parse_attachment_splits_into_assignable_items():
    from extractor.parser import parse_attachment

    a = parse_attachment(ATTACHMENT)
    assert a.notes == ["※ 9월 28일(월)까지 제출", "- 이메일 : test@example.com"]
    assert a.items == [
        # 번호 없는 첫 제목(한글 자동 문단번호)은 1번 항목으로 보정
        "1-1) [기관 개요] 설립근거 및 목적",
        "1-2) [기관 개요] 연도별 재무상태\n- ①재무상태표",
        # 상위 항목의 기간 조건을 하위 행마다 붙이고, 조건성 하위 항목은 공통으로 합친다
        "2-1) [최근 6년간(2021~2026) 감사 조치 관련] 국회 지적사항 및 조치내역\n"
        "- 결과보고서 별도 제출\n(공통) 관련 기준 및 규정, 지침 등 근거 별첨",
        "2-2) [최근 6년간(2021~2026) 감사 조치 관련] 감사원 지적사항\n"
        "(공통) 관련 기준 및 규정, 지침 등 근거 별첨",
        "3. 소관 법령 목록",
        # 남는 하위 항목이 하나뿐이면 나누지 않는다
        "4. 복지포인트 지급 현황\n1) 연도별 지급 총액\n2) 산하기관 포함 제출",
    ]


def test_parse_attachment_treats_unnumbered_heading_before_item_1_as_title():
    from extractor.parser import parse_attachment

    a = parse_attachment("2026년도 국정감사 공통요구자료\n1. 기관 현황\n2. 예산 현황")
    assert a.notes == ["2026년도 국정감사 공통요구자료"]
    assert a.items == ["1. 기관 현황", "2. 예산 현황"]


def test_parse_attachment_auto_numbered_list_with_sections():
    from extractor.parser import parse_attachment

    text = (
        "공통 자료요청\n* 26.6월 말 기준으로 작성\n"
        "직제표 (연락처, 담당업무 포함)\n"
        "(최근3년간) 문서 수발신 목록\n* (순번, 일자, 제목)\n"
        "<연구기관>\n1. 기관평가 현황\n2. (최근5년간) 특허 현황\n"
        "<학교(과기원 등)>\n1. 등록금 집행현황\n6, (최근5년간) 산학협력단 회계\n"
    )
    a = parse_attachment(text)
    assert a.notes == ["공통 자료요청", "* 26.6월 말 기준으로 작성"]
    assert a.items == [
        # 한글 자동 번호(텍스트에 번호 없음)는 줄마다 항목으로 보고 순번을 매긴다
        "1. 직제표 (연락처, 담당업무 포함)",
        "2. (최근3년간) 문서 수발신 목록\n* (순번, 일자, 제목)",
        # 섹션마다 번호가 새로 시작하고 섹션명이 붙는다
        "1. [연구기관] 기관평가 현황",
        "2. [연구기관] (최근5년간) 특허 현황",
        "1. [학교(과기원 등)] 등록금 집행현황",
        "6. [학교(과기원 등)] (최근5년간) 산학협력단 회계",  # "6," 번호 오타
    ]
