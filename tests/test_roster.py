from openpyxl import load_workbook

from extractor import roster
from extractor.ledger import append_rows, create_ledger, next_row

NAMES = {"channel": {"기획실": "홍길동"}, "tasks": {"총무구매실|구매·계약": "김구매"}, "members": {"대외협력실": ["이협력"]}}


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
    listed = {(r[1], r[3]) for r in ws.iter_rows(min_row=2, values_only=True) if r[2] == "업무"}
    assert set(roster.tasks()) <= listed


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
    assert got == {"channel": {"예산실": "윤"}, "tasks": {}, "members": {"감사부": ["a"]}}
