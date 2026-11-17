import json
import os

from extractor import learning, roster, settings

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


def test_backup_created_before_each_save_and_limited(monkeypatch):
    settings.save(SAMPLE)
    assert settings.backups() == []  # 첫 저장 전에는 백업할 파일이 없다
    settings.save({**SAMPLE, "channel": {}})
    (b,) = settings.backups()
    with open(os.path.join(settings.backup_dir(), b["name"]), encoding="utf-8") as f:
        assert json.load(f)["channel"] == SAMPLE["channel"]  # 저장 직전 내용
    monkeypatch.setattr(settings, "BACKUP_KEEP", 3)
    for i in range(5):
        settings.save({**SAMPLE, "channel": {"기획실": f"이름{i}"}})
    assert len(settings.backups()) == 3
    assert len(os.listdir(settings.backup_dir())) == 3


def test_restore_backup():
    settings.save(SAMPLE)
    settings.save({**SAMPLE, "channel": {}})
    name = settings.backups()[0]["name"]
    assert settings.restore(name)["channel"] == SAMPLE["channel"]
    assert settings.load()["channel"] == SAMPLE["channel"]
    for bad in ("../settings.json", "settings_000000_000000.json", ""):
        try:
            settings.restore(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_import_from_ledger_sheets():
    from extractor.ledger import create_ledger

    wb = create_ledger()
    roster.write(wb, SAMPLE)
    learning.write_rules(wb, SAMPLE["rules"])
    got = settings.from_workbook(wb)
    assert got == settings.clean(SAMPLE)
    assert settings.summary(got) == {"channel": 2, "tasks": 1, "members": 2, "excluded": 1, "custom": 1, "rules": 1}
    assert settings.from_workbook(create_ledger()) == settings.empty()


def test_export_workbook_round_trip(tmp_path):
    from openpyxl import load_workbook

    path = tmp_path / "설정.xlsx"
    settings.to_workbook(SAMPLE).save(path)
    wb = load_workbook(path)
    assert wb.sheetnames == [roster.SHEET_NAME, learning.RULE_SHEET]
    assert [c.value for c in wb[roster.SHEET_NAME][1]] == roster.HEADER
    assert settings.from_workbook(wb) == settings.clean(SAMPLE)
