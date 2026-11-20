from extractor import roster


def test_clean_rejects_non_text():
    got = roster.clean({"channel": {"기획실": 3, "예산실": " 윤 "}, "tasks": "x", "members": {"감사부": ["a", "", 1]}})
    assert got == {"channel": {"예산실": "윤"}, "tasks": {}, "members": {"감사부": ["a"]}, "excluded": [], "custom": [],
                   "org": None, "merged": {}}
    got = roster.clean({"excluded": ["감사부|복무감사", 3, "x"], "custom": [
        {"dept": "감사부", "task": "청탁금지", "keywords": "청탁금지, 김영란법, 김"}, {"dept": "", "task": "x"}, "y"]})
    assert got["excluded"] == ["감사부|복무감사"]
    assert got["custom"] == [{"dept": "감사부", "task": "청탁금지", "keywords": ["청탁금지", "김영란법"]}]


def test_tasks_lists_table_departments_only():
    pairs = roster.tasks()
    assert ("감사부", "복무감사") in pairs and all(d and d != "해당없음" for d, _ in pairs)
    assert len(pairs) == len(set(pairs))


def test_special_cases_are_not_departments():
    depts = {d for d, _ in roster.tasks()}
    assert not any("국방부" in d or "인사이트" in d or d.startswith("(") for d in depts)


def test_resolver_follows_merges_and_detects_deleted():
    resolve = roster.resolver({"가팀": "나팀", "나팀": "다팀", "라팀": "", "마팀": "바팀", "바팀": "마팀"})
    assert [resolve(d) for d in ("가팀", "나팀", "라팀", "마팀", "기획실")] == ["다팀", "다팀", "", "", "기획실"]


def test_tasks_follow_merged_departments():
    merged = {"시설자산실": "총무구매실", "안전보건실": ""}
    pairs = roster.tasks(merged)
    assert ("총무구매실", "자산 관리") in pairs
    assert not any(d in ("시설자산실", "안전보건실") for d, _ in pairs)


def test_clean_org_and_merged():
    got = roster.clean({"org": [{"name": "기획본부", "depts": ["기획실", "기획실", "", "a|b"]},
                                {"name": "새 본부", "depts": ["기획실", "새팀"]}, {"name": "빈 본부", "depts": []}, "x"],
                        "merged": {"윤리경영실": "감사부", "옛팀": "", "같은팀": "같은팀", "x": 3}})
    assert got["org"] == [{"name": "기획본부", "depts": ["기획실"]}, {"name": "새 본부", "depts": ["새팀"]}]
    assert got["merged"] == {"윤리경영실": "감사부", "옛팀": ""}
    assert roster.clean({"org": []})["org"] is None  # 비면 기본 구성


def test_org_colors_keep_default_groups_and_cycle_new_ones():
    groups = roster.org({"org": [{"name": "새 본부", "depts": ["새팀"]}, {"name": "감사부", "depts": ["감사부"]},
                                 {"name": "또 새 본부", "depts": ["또팀"]}]})
    assert [(g["name"], g["i"], g["c"]) for g in groups] == [("새 본부", 0, 6), ("감사부", 1, 3), ("또 새 본부", 2, 7)]
    assert [g["name"] for g in roster.org()][0] == "기획본부"
