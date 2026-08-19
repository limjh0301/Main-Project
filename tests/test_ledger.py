import pytest

from extractor.ledger import (
    HEADER,
    LedgerFormatError,
    append_rows,
    create_ledger,
    open_ledger,
)

ROW = {
    "committee": "기획재정위원회",
    "request_date": "2024-01-01",
    "deadline": "2024.02.01",
    "doc_no": "0001234567",
    "member": "을지문덕",
    "party": "칼퇴원한당",
    "district": "조퇴도 원할시갑",
    "content": "1. 최근 5년간 직원 칼퇴 내역\n2. 유연근무제 운영 현황",
    "requester": "박삼관",
    "email": "admin@yogu.work",
}


def test_create_ledger_header():
    wb = create_ledger()
    ws = wb.active
    assert [ws.cell(row=1, column=i + 1).value for i in range(len(HEADER))] == HEADER


def test_append_one_row_per_request(tmp_path):
    wb = create_ledger()
    assert append_rows(wb, [ROW, ROW]) == 2

    path = tmp_path / "ledger.xlsx"
    wb.save(path)
    wb2 = open_ledger(str(path))
    append_rows(wb2, [ROW])
    ws = wb2.active
    assert ws.max_row == 4  # 헤더 + 3행 (요구서 3건)
    assert ws.cell(row=2, column=1).value == "기획재정위원회"
    assert ws.cell(row=2, column=8).value.startswith("1. 최근 5년간")
    # 수동 관리 항목(담당부서·제출여부·비고)은 비워 둔다
    assert ws.cell(row=2, column=11).value in ("", None)


def test_open_ledger_rejects_wrong_header(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["잘못된", "헤더"])
    path = tmp_path / "bad.xlsx"
    wb.save(path)
    with pytest.raises(LedgerFormatError):
        open_ledger(str(path))
