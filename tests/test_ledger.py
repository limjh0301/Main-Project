import pytest

from extractor.ledger import (
    HEADER,
    LedgerFormatError,
    append_rows,
    create_ledger,
    open_ledger,
)

ROW = {
    "request_date": "2026-08-15",
    "committee": "기획재정위원회",
    "member": "홍길동",
    "doc_no": "기재위 제2026-153호",
    "item": "국세 감면 현황",
    "deadline": "2026-08-25",
    "department": "기획재정부",
    "source_file": "요구서.pdf",
}


def test_create_ledger_header():
    wb = create_ledger()
    ws = wb.active
    assert [ws.cell(row=1, column=i + 1).value for i in range(len(HEADER))] == HEADER


def test_append_rows_serials(tmp_path):
    wb = create_ledger()
    assert append_rows(wb, [ROW, ROW]) == [1, 2]

    # 저장 후 다시 열어 이어붙이면 연번이 이어져야 한다
    path = tmp_path / "ledger.xlsx"
    wb.save(path)
    wb2 = open_ledger(str(path))
    assert append_rows(wb2, [ROW]) == [3]
    ws = wb2.active
    assert ws.cell(row=4, column=1).value == 3
    assert ws.cell(row=4, column=6).value == "국세 감면 현황"


def test_open_ledger_rejects_wrong_header(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["잘못된", "헤더"])
    path = tmp_path / "bad.xlsx"
    wb.save(path)
    with pytest.raises(LedgerFormatError):
        open_ledger(str(path))
