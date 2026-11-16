from openpyxl import load_workbook

from extractor import roster
from extractor.ledger import append_rows, create_ledger, next_row

NAMES = {"channel": {"기획실": "홍길동"}, "tasks": {"총무구매실|구매·계약": "김구매", "감사부|청탁금지": "박청렴"},
         "members": {"대외협력실": ["이협력"]}, "excluded": ["감사부|복무감사"],
         "custom": [{"dept": "감사부", "task": "청탁금지", "keywords": ["청탁금지", "김영란법"]}]}


def test_write_and_read_round_trip(tmp_path):
    wb = create_ledger()
    roster.write(wb, NAMES)
    path = tmp_path / "대장.xlsx"
    wb.save(path)
    wb2 = load_workbook(path)
    assert roster.read(wb2) == NAMES
    ws = wb2[roster.SHEET_NAME]
    assert [c.value for c in ws[1]] == roster.HEADER
    # 배분표의 업무는 담당자가 비어 있어도 모두 적어 두어 엑셀에서 바로 채울 수 있게 한다
    listed = {(r[1], r[3]) for r in ws.iter_rows(min_row=2, values_only=True) if r[2] in ("업무", "제외")}
    assert set(roster.tasks()) <= listed
    rows = {(r[1], r[3]): r for r in ws.iter_rows(min_row=2, values_only=True)}
    assert rows[("감사부", "복무감사")][2] == "제외"
    assert rows[("감사부", "청탁금지")][2:] == ("추가 업무", "청탁금지", "박청렴", "청탁금지, 김영란법")


def test_roster_sheet_does_not_disturb_ledger():
    wb = create_ledger()
    roster.write(wb, NAMES)
    append_rows(wb, [{"doc_no": "0000000001", "content": "[x]"}])
    assert next_row(wb) == 5 and wb.active.title != roster.SHEET_NAME


def test_sheet_uses_general_manager_label_and_reads_old_label():
    wb = create_ledger()
    roster.write(wb, NAMES)
    ws = wb[roster.SHEET_NAME]
    kinds = {r[2] for r in ws.iter_rows(min_row=2, values_only=True)}
    assert "총괄담당자" in kinds and "창구" not in kinds
    # 예전 대장의 '창구' 표기도 총괄담당자로 읽는다
    for row in ws.iter_rows(min_row=2):
        if row[2].value == "총괄담당자":
            row[2].value = "창구"
    assert roster.read(wb)["channel"] == {"기획실": "홍길동"}


def test_read_without_sheet_is_empty():
    assert roster.read(create_ledger()) == roster.empty()


def test_clean_rejects_non_text():
    got = roster.clean({"channel": {"기획실": 3, "예산실": " 윤 "}, "tasks": "x", "members": {"감사부": ["a", "", 1]}})
    assert got == {"channel": {"예산실": "윤"}, "tasks": {}, "members": {"감사부": ["a"]}, "excluded": [], "custom": []}
    got = roster.clean({"excluded": ["감사부|복무감사", 3, "x"], "custom": [
        {"dept": "감사부", "task": "청탁금지", "keywords": "청탁금지, 김영란법, 김"}, {"dept": "", "task": "x"}, "y"]})
    assert got["excluded"] == ["감사부|복무감사"]
    assert got["custom"] == [{"dept": "감사부", "task": "청탁금지", "keywords": ["청탁금지", "김영란법"]}]


def test_old_five_column_sheet_is_read():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.create_sheet(roster.SHEET_NAME)
    ws.append(["본부", "부서", "구분", "업무", "담당자"])
    ws.append(["기획본부", "기획실", "창구", "요청 취합·안내", "홍길동"])
    ws.append(["감사부", "감사부", "업무", "복무감사", "박감사"])
    got = roster.read(wb)
    assert got["channel"] == {"기획실": "홍길동"} and got["tasks"] == {"감사부|복무감사": "박감사"}
