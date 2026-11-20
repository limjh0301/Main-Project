from extractor import assign


def _one(text, context="", title="", siblings=True):
    return assign.assign([{"text": text, "context": context, "title": title}], use_siblings=siblings)[0]


def test_keyword_then_detail_keyword():
    q = _one("병가 사용 관련 복무점검·감사 실시 현황")
    assert (q["cat"], q["dept"], q["task"]) == ("H4", "감사부", "복무감사")
    assert q["why"] == "‘복무점검’ 키워드" and not q["ambiguous"]


def test_default_route_without_detail_keyword():
    q = _one("최근 5년간 법률자문 현황 및 의견서")
    assert (q["dept"], q["why"]) == ("총무구매실", "")


def test_unclassified_goes_to_default_dept_as_ambiguous():
    q = _one("기타 요청 사항 일체")
    assert q["ambiguous"] and q["dept"] == assign.DEFAULT_DEPT and q["how"] == "미분류"


def test_title_only_match_is_ambiguous_with_guess():
    q = _one("관련 자료 일체", title="법률자문 관련")
    assert q["ambiguous"] and q["why"] == "추정: 총무구매실"


def test_supercomputer_request_pulls_generic_items():
    qs = assign.assign([{"text": t, "context": "", "title": ""} for t in (
        "국가 슈퍼컴퓨터 6호기 구축 지연 사유", "슈퍼컴퓨터 5호기 누리온 가동률", "관련 예산 집행 현황")])
    assert [q["dept"] for q in qs] == ["국가슈퍼컴퓨팅본부"] * 3


def test_request_items_split_title_and_cut_contact_notes():
    title, qs = assign.request_items([
        "1. 병가 및 질병휴직 운영 현황 ※ 대상: 연구회",
        "1. 기관별 병가 규정",
        "2. 병가 사용 현황 ※ 성명 등 개인정보는 비식별 처리 ※자료 제출 관련 문의 김OO 비서관(010-0000-0000)",
    ])
    assert title == "병가 및 질병휴직 운영 현황"
    assert [(q["key"], q["text"]) for q in qs] == [("1", "기관별 병가 규정"), ("2", "병가 사용 현황")]


def test_attachment_items_sections_and_subitems():
    qs = assign.attachment_items([
        "1. 직제표",
        "3. [연구기관] 연구윤리 위반 현황\n- 연도별",
        "2-1) [[학교(과기원 등)] 학생 현황] 재학생 수",
        "1-2) [기관 개요] 주요 연혁",
    ])
    assert [(q["key"], q["section"], q["context"]) for q in qs] == [
        ("1", "", ""), ("[연구기관] 3", "연구기관", ""),
        ("[학교(과기원 등)] 2-1", "학교(과기원 등)", "학생 현황"), ("1-2", "", "기관 개요")]
    assert qs[1]["text"] == "연구윤리 위반 현황 / - 연도별"


def test_plan_marks_other_sections_and_duplicates():
    qs = assign.plan(assign.attachment_items([
        "1. 퇴직자 재취업 현황", "2. [학교(과기원 등)] 학생 현황", "3. [연구기관] 퇴직자 재취업 현황"]), use_siblings=False)
    assert qs[1]["dept"] == assign.NA_DEPT
    assert qs[2]["dup_of"] == "1"


def test_no_staff_names_in_routing_table():
    # 담당자 이름은 대장의 '부서별 담당자' 시트에만 둔다 — 배분표는 (카테고리, 키워드, 부서, 업무)
    assert all(len(row) == 4 for row in assign.TABLE)


def test_excluded_task_falls_to_next_row_or_default():
    q = assign.assign([{"text": "병가 사용 관련 복무점검·감사 실시 현황"}], excluded={"감사부|복무감사"})[0]
    assert (q["dept"], q["task"]) == ("인재개발실", "승진·징계·인사 발령·휴직")  # 징계·복무의 기본 담당


def test_all_rows_excluded_is_ambiguous():
    rows = {f"{d}|{t}" for c, _, d, t in assign.TABLE if c == "L1"}
    q = assign.assign([{"text": "법률자문 현황"}], excluded=rows)[0]
    assert q["ambiguous"] and q["dept"] == assign.DEFAULT_DEPT


def test_added_task_keywords_win():
    custom = [{"dept": "감사부", "task": "청탁금지", "keywords": ["김영란법"]}]
    q = assign.assign([{"text": "김영란법 위반 신고 현황"}], custom=custom)[0]
    assert (q["dept"], q["task"], q["why"], q["ambiguous"]) == ("감사부", "청탁금지", "‘김영란법’ 추가 업무", False)



def _route_one(text, **kw):
    from extractor import assign

    it = assign.assign([{"text": text}], use_siblings=False, **kw)[0]
    return it["dept"], it["task"], it["ambiguous"], it["why"]


def test_special_cases_go_to_check_with_note():
    assert _route_one("탄약 보관 현황") == ("기획실", "", True, "특수 사례 — 국방부 보안과제 책임자에게 직접 확인")
    assert _route_one("데이터 인사이트 발간 현황")[2:] == (True, "특수 사례 — 데이터 인사이트 저자에게 확인")


def test_merged_and_deleted_departments():
    from extractor import roster

    assert _route_one("유형자산 대장")[:2] == ("시설자산실", "자산 관리")
    # 조직개편: 시설자산실 업무를 총무구매실이 넘겨받음
    assert _route_one("유형자산 대장", resolve=roster.resolver({"시설자산실": "총무구매실"}))[:3] == ("총무구매실", "자산 관리", False)
    # 넘겨받은 부서 없이 없앤 경우 → 확인 필요
    assert _route_one("유형자산 대장", resolve=roster.resolver({"시설자산실": ""})) == ("기획실", "", True, "없앤 부서(시설자산실)의 업무")
    # 기본 부서(기획실) 이름이 바뀌면 확인 필요 질의도 새 이름으로
    assert _route_one("탄약 보관 현황", resolve=roster.resolver({"기획실": "전략기획실"}))[0] == "전략기획실"
