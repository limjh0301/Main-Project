from extractor import roster


def test_clean_rejects_non_text():
    got = roster.clean({"channel": {"기획실": 3, "예산실": " 윤 "}, "tasks": "x", "members": {"감사부": ["a", "", 1]}})
    assert got == {"channel": {"예산실": "윤"}, "tasks": {}, "members": {"감사부": ["a"]}, "excluded": [], "custom": []}
    got = roster.clean({"excluded": ["감사부|복무감사", 3, "x"], "custom": [
        {"dept": "감사부", "task": "청탁금지", "keywords": "청탁금지, 김영란법, 김"}, {"dept": "", "task": "x"}, "y"]})
    assert got["excluded"] == ["감사부|복무감사"]
    assert got["custom"] == [{"dept": "감사부", "task": "청탁금지", "keywords": ["청탁금지", "김영란법"]}]


def test_tasks_lists_table_departments_only():
    pairs = roster.tasks()
    assert ("감사부", "복무감사") in pairs and all(d and d != "해당없음" for d, _ in pairs)
    assert len(pairs) == len(set(pairs))
