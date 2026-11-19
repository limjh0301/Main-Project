import json
import os

from extractor import roster, settings

SAMPLE = {
    "channel": {"기획실": "가나다", "감사부": "라마바"},
    "tasks": {"감사부|복무감사": "사아자"},
    "members": {"기획실": ["차카타", "파하가"]},
    "excluded": ["감사부|반부패청렴"],
    "custom": [{"dept": "감사부", "task": "청탁금지", "keywords": ["김영란법", "청탁"]}],
    "rules": [{"keyword": "칼퇴", "dept": "인재개발실", "added": "2026-10-01", "basis": "정정 2건"}],
}


def test_load_defaults_when_missing_or_broken():
    assert not settings.exists()
    assert settings.load() == settings.empty() == {**roster.empty(), "rules": []}
    os.makedirs(settings.DATA_DIR)
    with open(settings.path(), "w", encoding="utf-8") as f:
        f.write("{깨진")
    assert settings.load() == settings.empty()


def test_save_and_load_round_trip():
    saved = settings.save(SAMPLE)
    assert settings.load() == saved
    assert saved["channel"] == SAMPLE["channel"] and saved["rules"] == SAMPLE["rules"]
    with open(settings.path(), encoding="utf-8") as f:
        assert json.load(f)["custom"] == SAMPLE["custom"]
    assert not os.path.exists(settings.path() + ".tmp")


def test_clean_rules_drops_invalid_and_duplicates():
    rules = [{"keyword": "칼", "dept": "x"}, {"keyword": "칼퇴", "dept": ""}, "x",
             {"keyword": "칼퇴", "dept": "인재개발실", "added": "어제"}, {"keyword": "칼퇴", "dept": "감사부"}]
    assert settings.clean_rules(rules) == [{"keyword": "칼퇴", "dept": "인재개발실", "added": "", "basis": ""}]
