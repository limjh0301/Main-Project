from datetime import date, datetime

import pytest

from extractor.ledger import (
    HEADER,
    HEADER_ROW,
    LedgerFormatError,
    append_rows,
    create_ledger,
    enrich_member_fields,
    existing_doc_nos,
    fill_deadline,
    next_row,
    open_ledger,
)

ROW = {
    "doc_no": "0001234567",
    "request_date": "2026-09-21",
    "deadline": "2026.09.28",
    "party": "칼퇴원한당",
    "member": "을지문덕",
    "requester": "박삼관",
    "content": "[직원 칼퇴 현황]\n1. 최근 5년간 직원 칼퇴 내역\n2. 유연근무제 운영 현황",
    "memo": "",
}


def _row(ws, r):
    return [ws.cell(row=r, column=c).value for c in range(1, len(HEADER) + 1)]


def test_create_ledger_layout():
    ws = create_ledger(year=2026).active
    assert ws.cell(row=1, column=1).value == "2026년도 국회 요구자료"
    assert _row(ws, HEADER_ROW) == HEADER
    assert HEADER[:2] == ["순번", "요구서 번호"]


def test_append_rows_continue_seq_and_keep_manual_columns(tmp_path):
    wb = create_ledger()
    assert append_rows(wb, [ROW, {**ROW, "doc_no": "0001234568"}]) == 2
    path = tmp_path / "ledger.xlsx"
    wb.save(path)

    wb2 = open_ledger(str(path))
    append_rows(wb2, [{**ROW, "doc_no": "0001234569"}])
    ws = wb2.active
    first = _row(ws, 4)
    assert first[:4] == [1, "0001234567", datetime(2026, 9, 21), datetime(2026, 9, 28)]
    assert first[4:8] == ["칼퇴원한당", "을지문덕", "박삼관", ROW["content"]]
    assert first[8] is None  # 제출일자는 직접 관리
    assert [ws.cell(row=r, column=1).value for r in (4, 5, 6)] == [1, 2, 3]
    assert ws.cell(row=4, column=3).number_format == "mm-dd-yy"
    assert ws.auto_filter.ref.endswith("6")
    assert existing_doc_nos(wb2) == {"0001234567", "0001234568", "0001234569"}


def _user_style_ledger(tmp_path):
    """기관 관리대장처럼: 제목 1행, 머리글 3행, 기록 2건, 그 아래 순번만 미리 채운 빈 행."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "기관명"
    ws["A1"] = "2026년도 국회 요구자료"
    for c, name in enumerate(["순번", "요구서 번호", *HEADER[2:]], start=1):
        ws.cell(row=3, column=c, value=name)
    for r, (seq, doc) in enumerate([(1, "0007804149"), (2, "0007806571")], start=4):
        ws.cell(row=r, column=1, value=seq)
        ws.cell(row=r, column=2, value=doc)
        ws.cell(row=r, column=8, value="[업무보고 관련]\n1. 자료").font = Font(name="맑은 고딕", size=9)
        ws.cell(row=r, column=9, value=datetime(2026, 7, 2))
    for r in range(6, 20):
        ws.cell(row=r, column=1, value=r - 3)  # 미리 매겨 둔 순번
    ws.cell(row=1048000, column=1).font = Font(bold=True)  # 서식만 아래쪽 끝까지
    ws.auto_filter.ref = "A3:J19"
    path = tmp_path / "기관.xlsx"
    wb.save(path)
    return path


def test_append_to_user_ledger_after_last_record(tmp_path):
    wb = open_ledger(str(_user_style_ledger(tmp_path)))
    assert next_row(wb) == 6
    append_rows(wb, [ROW])
    ws = wb["기관명"]
    assert _row(ws, 6)[:2] == [3, "0001234567"]
    assert ws.cell(row=6, column=8).font.size == 9  # 위 기록 행 서식을 따름
    assert ws.cell(row=5, column=9).value == datetime(2026, 7, 2)  # 기존 기록 보존
    assert ws.auto_filter.ref == "A3:J19"


def test_header_with_spacing_differences_is_accepted(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append([h.replace(" ", "") for h in HEADER])
    path = tmp_path / "nospace.xlsx"
    wb.save(path)
    assert next_row(open_ledger(str(path))) == 2


def test_open_ledger_rejects_wrong_header(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["요구서번호", "소관위원회", "요구일자"])  # 예전 관리대장 양식
    path = tmp_path / "old.xlsx"
    wb.save(path)
    with pytest.raises(LedgerFormatError):
        open_ledger(str(path))


def test_fill_deadline_only_empty_cells():
    wb = create_ledger()
    append_rows(wb, [ROW, {**ROW, "doc_no": "2", "deadline": ""}])
    assert fill_deadline(wb, 4, 5, date(2026, 10, 2)) == 1
    ws = wb.active
    assert [ws.cell(row=r, column=4).value for r in (4, 5)] == [date(2026, 9, 28), date(2026, 10, 2)]


def test_enrich_member_fields():
    data = {"member": "황희", "party": "", "committee": "", "district": ""}
    enrich_member_fields(data)
    assert data["party"] == "더불어민주당"
    assert data["committee"] == "국토교통위원회"
    assert data["district"] == "서울 양천구갑"

    unknown = {"member": "을지문덕", "party": "칼퇴원한당", "committee": "", "district": ""}
    enrich_member_fields(unknown)
    assert unknown["party"] == "칼퇴원한당"  # 명단에 없으면 파싱값 유지
