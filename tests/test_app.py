import io
from datetime import datetime

import pytest

import app as app_module


@pytest.fixture
def client(monkeypatch):
    # PDF 추출 대신 저장된 파일 내용을 그대로 텍스트로 돌려주는 가짜 추출기
    def fake_extract(path, force_ocr=False):
        with open(path, encoding="utf-8") as f:
            return f.read(), "text-layer"

    monkeypatch.setattr(app_module, "extract_text", fake_extract)
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_korean_filenames_do_not_collide(client):
    # 한글 파일명은 secure_filename이 전부 지워 같은 이름으로 겹치던 회귀 버그 검증:
    # 5개 파일이 각각의 내용으로 5건 처리되어야 한다
    uploads = [
        (io.BytesIO(f"요구서번호 : 000000000{i}".encode()), f"요구서(의원실{'가나다라마'[i]}).pdf")
        for i in range(5)
    ]
    res = client.post(
        "/process",
        data={"mode": "new", "docs": uploads},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    doc_nos = [r["parsed"]["doc_no"] for r in res.get_json()["results"]]
    assert doc_nos == [f"000000000{i}" for i in range(5)]


def _post(client, uploads):
    return client.post("/process", data={"mode": "new", "docs": uploads}, content_type="multipart/form-data")


def _download(client, body):
    from openpyxl import load_workbook

    res = client.get(body["download_url"])
    assert res.status_code == 200
    return load_workbook(io.BytesIO(res.data)).active


ATTACHMENT_PARAGRAPHS = ["※ 9월 28일(월)까지 제출", "기관 개요", " 1) 설립근거", " 2) 주요 연혁", "2. 사업 현황"]


def test_hwp_attachment_links_to_request_by_doc_no(client, make_hwpx):
    pdf = (io.BytesIO("요구서번호 : 0007999174\n1. 다음의 자료를 요청합니다 - 첨부 파일 참고".encode()), "질의서.pdf")
    other = (io.BytesIO("요구서번호 : 0001112223\n1. 별도 요구".encode()), "다른질의서.pdf")
    hwpx = make_hwpx("0007999174_공통요구자료.hwpx", ATTACHMENT_PARAGRAPHS)
    res = _post(client, [other, pdf, (open(hwpx, "rb"), hwpx.name)])
    assert res.status_code == 200
    body = res.get_json()
    assert body["row_count"] == 2  # 요구서 1건 = 1행
    linked = body["results"][1]
    assert linked["attachments"] == [hwpx.name]
    assert [i.split("\n")[0] for i in linked["items"]] == [
        "1-1) [기관 개요] 설립근거", "1-2) [기관 개요] 주요 연혁", "2. 사업 현황",
    ]

    ws = _download(client, body)
    assert [ws.cell(row=r, column=2).value for r in (4, 5)] == ["0001112223", "0007999174"]
    assert ws.max_row == 5
    # 질의 내역은 한 칸에 줄바꿈으로
    # 질의서 첫 항목이 제목, 첨부 항목이 질의 내역
    assert ws.cell(row=5, column=8).value.split("\n") == [
        "[다음의 자료를 요청합니다]",
        "1-1) [기관 개요] 설립근거", "1-2) [기관 개요] 주요 연혁", "2. 사업 현황",
    ]
    assert ws.cell(row=5, column=10).value == "[첨부 안내]\n※ 9월 28일(월)까지 제출"


def test_hwp_without_matching_request_is_recorded_alone(client, make_hwpx):
    hwpx = make_hwpx("0005556667_요구자료.hwpx", ["1. 기관 현황", "2. 예산 현황"])
    res = _post(client, [(open(hwpx, "rb"), hwpx.name)])
    assert res.status_code == 200
    body = res.get_json()
    assert body["results"][0]["method"] == "hwp"
    assert body["results"][0]["parsed"]["doc_no"] == "0005556667"
    assert body["results"][0]["items"] == ["1. 기관 현황", "2. 예산 현황"]
    assert body["row_count"] == 1


def test_unreadable_hwp_returns_error(client):
    res = _post(client, [(io.BytesIO(b"broken"), "깨진파일.hwp")])
    assert res.status_code == 422
    assert "깨진파일.hwp" in res.get_json()["error"]


@pytest.mark.parametrize(
    "filename, deadline, expected",
    [
        ("0007999174_자료요구서_260921.pdf", "2026.09.28", "2026-09-21"),
        ("0007999174_자료요구서_261001.pdf", "2026.09.28", ""),  # 제출기한보다 늦으면 요구일자가 아님
        ("0007999174_자료요구서_261341.pdf", "", ""),  # 날짜가 아님
        ("0007999174.pdf", "", ""),  # 요구서번호 끝자리를 날짜로 오인하지 않음
        ("질의서.pdf", "2026.09.28", ""),
    ],
)
def test_request_date_from_filename(filename, deadline, expected):
    assert app_module._request_date_from_name(filename, deadline) == expected


def test_request_date_falls_back_to_filename_only_when_missing(client):
    no_date = (io.BytesIO("요구서번호 : 0007999174\n제출기한 : 2026.09.28".encode()), "0007999174_자료요구서_260921.pdf")
    with_date = (
        io.BytesIO("요구서번호 : 0001112223\n요구일자 : 2026. 9. 15\n제출기한 : 2026.09.28".encode()),
        "0001112223_자료요구서_260921.pdf",
    )
    body = _post(client, [no_date, with_date]).get_json()
    assert [r["parsed"]["request_date"] for r in body["results"]] == ["2026-09-21", "2026-09-15"]
    ws = _download(client, body)
    assert ws.cell(row=4, column=3).value == datetime(2026, 9, 21)


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("0007999174_황정아의원_자료요구서_260921.pdf", "황정아"),
        ("0007999174_송기헌_자료요구서_260921.pdf", "송기헌"),
        ("0007999174_김현_자료요구서.pdf", "김현"),  # 두 글자 이름
        ("0007999174_허영미_자료요구서.pdf", ""),  # 명단에 없는 '허영미'를 '허영'으로 오인하지 않음
        ("0007999174_공통요구자료.hwp", ""),
    ],
)
def test_member_from_filename(filename, expected):
    assert app_module._member_from_name(filename) == expected


def test_fill_from_name_keeps_text_values_first():
    parsed = {"doc_no": "0001112223", "request_date": "", "member": "", "deadline": "2026.09.28"}
    out = app_module._fill_from_name(parsed, "0007999174_황정아의원_자료요구서_260921.pdf")
    assert out["doc_no"] == "0001112223"  # 본문 값 우선
    assert (out["request_date"], out["member"]) == ("2026-09-21", "황정아")
    assert out["from_name"] == ["request_date", "member"]


def test_filename_fills_missing_fields_and_member_lookup(client, make_hwpx):
    pdf = (io.BytesIO("1. 기관 현황 자료".encode()), "0007999174_황정아의원_자료요구서_260921.pdf")
    hwpx = make_hwpx("0005556667_송기헌_공통요구자료_260915.hwpx", ["1. 기관 현황"])
    body = _post(client, [pdf, (open(hwpx, "rb"), hwpx.name)]).get_json()
    p, h = (r["parsed"] for r in body["results"])
    assert (p["doc_no"], p["request_date"], p["member"]) == ("0007999174", "2026-09-21", "황정아")
    assert p["committee"] == "과학기술정보방송통신위원회"  # 의원 명단에서 소관위원회 보완
    assert (h["doc_no"], h["request_date"], h["member"]) == ("0005556667", "2026-09-15", "송기헌")
    assert h["from_name"] == ["doc_no", "request_date", "member"]


def test_date_input_fills_target_row(client, make_hwpx):
    with_deadline = (io.BytesIO("요구서번호 : 0001112223\n제출기한 : 2026.09.28\n1. 별도 요구".encode()), "a.pdf")
    no_deadline = make_hwpx("0005556667_공통요구자료.hwpx", ["1. 기관 현황", "2. 예산 현황"])
    body = _post(client, [with_deadline, (open(no_deadline, "rb"), no_deadline.name)]).get_json()
    target = body["results"][1]
    assert target["rows"] == [5, 5] and not target["parsed"]["deadline"]

    rid = body["download_url"].rsplit("/", 1)[1]
    res = client.post(f"/dates/{rid}", json={"updates": [
        {"rows": target["rows"], "deadline": "2026-10-02", "request_date": "2026-09-21"}]})
    assert res.status_code == 200 and res.get_json()["filled"] == 2
    ws = _download(client, body)
    assert [ws.cell(row=r, column=4).value for r in (4, 5)] == [datetime(2026, 9, 28), datetime(2026, 10, 2)]
    assert ws.cell(row=5, column=3).value == datetime(2026, 9, 21)


@pytest.mark.parametrize("deadline", ["2026.10.02", "2026-02-30", ""])
def test_date_input_rejects_bad_dates(client, deadline):
    body = _post(client, [(io.BytesIO("1. 요구".encode()), "a.pdf")]).get_json()
    rid = body["download_url"].rsplit("/", 1)[1]
    res = client.post(f"/dates/{rid}", json={"updates": [{"rows": [4, 4], "deadline": deadline}]})
    assert res.status_code == 400


def test_date_input_unknown_result(client):
    assert client.post("/dates/abc123", json={"updates": []}).status_code == 404


def test_very_long_request_is_cut_to_excel_cell_limit():
    items = [f"{i}. " + "가" * 500 for i in range(1, 80)]  # 약 4만 자
    row, got, _ = app_module._build_row({"items": items}, [])
    assert got == items
    assert len(row["content"]) == app_module.EXCEL_CELL_LIMIT
    assert row["content"].endswith("원본 확인)")


@pytest.mark.parametrize(
    "items, content",
    [
        # 요구목록 "1. 제목" 아래 세부 질의가 다시 1번부터: 제목을 [ ]로, 세부 내용은 줄을 나눔
        (["1. 병가 운영 현황 ※ 대상: 연구회 ※ 기간: 25년1월~", "1. 관련 규정 - 병가 사유 - 지급 기준", "2. 사용 현황"],
         "[병가 운영 현황]\n※ 대상: 연구회\n※ 기간: 25년1월~\n1. 관련 규정\n- 병가 사유\n- 지급 기준\n2. 사용 현황"),
        (["1. 국정감사 공통자료요구의 건"], "[국정감사 공통자료요구의 건]"),
        # 1. 2. 3. 이 이어지면 제목 없이 그대로
        (["1. 업무보고 자료", "2. 예산 설명자료"], "1. 업무보고 자료\n2. 예산 설명자료"),
        ([], "(요구내용 미추출 — 원본 확인 필요)"),
    ],
)
def test_content_title_and_lines(items, content):
    assert app_module._build_row({"items": items}, [])[0]["content"] == content


def test_standalone_attachment_title_from_filename(client, make_hwpx):
    hwpx = make_hwpx("0005556667_송기헌의원_공통요구자료_260915.hwpx", ["1. 기관 현황"])
    body = _post(client, [(open(hwpx, "rb"), hwpx.name)]).get_json()
    ws = _download(client, body)
    assert ws.cell(row=4, column=8).value == "[공통요구자료]\n1. 기관 현황"


def test_existing_ledger_skips_recorded_requests(client, tmp_path):
    from extractor.ledger import append_rows, create_ledger

    wb = create_ledger()
    append_rows(wb, [{"doc_no": "0001112223", "content": "[기존]"}])
    path = tmp_path / "대장.xlsx"
    wb.save(path)
    pdfs = [(io.BytesIO(f"요구서번호 : {n}\n1. 요구".encode()), f"{n}.pdf") for n in ("0001112223", "0004445556")]
    res = client.post("/process", data={"mode": "existing", "excel": (open(path, "rb"), "대장.xlsx"), "docs": pdfs},
                      content_type="multipart/form-data")
    body = res.get_json()
    assert [r["duplicate"] for r in body["results"]] == [True, False]
    assert (body["row_count"], body["skipped"]) == (1, 1)
    assert body["results"][1]["rows"] == [5, 5]
    ws = _download(client, body)
    assert [ws.cell(row=r, column=1).value for r in (4, 5)] == [1, 2]
    assert [ws.cell(row=r, column=2).value for r in (4, 5)] == ["0001112223", "0004445556"]


def test_board_payload_with_roster_from_ledger(client, tmp_path, make_hwpx):
    from extractor import roster
    from extractor.ledger import create_ledger

    wb = create_ledger()
    roster.write(wb, {"channel": {"감사부": "김감사"}, "tasks": {}, "members": {}})
    path = tmp_path / "대장.xlsx"
    wb.save(path)
    pdf = (io.BytesIO("요구서번호 : 0001112223\n1. 병가 현황\n1. 복무점검 실시 현황\n2. 법률자문 현황".encode()), "a.pdf")
    hwpx = make_hwpx("0005556667_공통요구자료.hwpx", ["1. 직제표", "<학교(과기원 등)>", "1. 학생 현황"])
    res = client.post("/process", data={"mode": "existing", "excel": (open(path, "rb"), "대장.xlsx"),
                                        "docs": [pdf, (open(hwpx, "rb"), hwpx.name)]},
                      content_type="multipart/form-data")
    b = res.get_json()["board"]
    assert b["roster"]["channel"] == {"감사부": "김감사"}
    assert [(r["tag"], r["title"], r["n"]) for r in b["reqs"]] == [
        ("0001112223", "병가 현황", 2), ("0005556667", "공통요구자료", 2)]
    assert [(i["id"], i["dept"]) for i in b["items"]] == [
        ("0001112223|1", "감사부"), ("0001112223|2", "총무구매실"),
        ("0005556667|1", "기획실"), ("0005556667|[학교(과기원 등)] 1", "해당없음")]


def test_roster_endpoint_writes_sheet_into_result(client):
    from extractor import roster

    body = _post(client, [(io.BytesIO("1. 요구".encode()), "a.pdf")]).get_json()
    rid = body["download_url"].rsplit("/", 1)[1]
    res = client.post(f"/roster/{rid}", json={"channel": {"기획실": "홍길동"}, "tasks": {}, "members": {}})
    assert res.status_code == 200
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(client.get(body["download_url"]).data))
    assert roster.read(wb)["channel"] == {"기획실": "홍길동"}
    assert client.post(f"/roster/{rid}", json=[1]).status_code == 400


def test_board_items_link_previous_questions(client, tmp_path):
    from extractor.ledger import append_rows, create_ledger

    wb = create_ledger()
    append_rows(wb, [{"doc_no": "0001112223", "request_date": "2025-09-18", "member": "을지문덕",
                      "content": "[2025 공통]\n1. (최근3년간) 예산서, 결산서"}])
    path = tmp_path / "대장.xlsx"
    wb.save(path)
    pdf = (io.BytesIO("요구서번호 : 0004445556\n1. (최근5년간) 예산서, 결산서".encode()), "b.pdf")
    res = client.post("/process", data={"mode": "existing", "excel": (open(path, "rb"), "대장.xlsx"), "docs": [pdf]},
                      content_type="multipart/form-data")
    prev = res.get_json()["board"]["items"][0]["prev"]
    assert prev[0]["doc"] == "0001112223" and prev[0]["kind"] == "기간만 다름" and prev[0]["date"] == "2025-09-18"


@pytest.fixture
def local_ledger(tmp_path, monkeypatch):
    from extractor.ledger import append_rows, create_ledger

    monkeypatch.setitem(app_module.app.config, "LOCAL_MODE", True)
    wb = create_ledger()
    append_rows(wb, [{"doc_no": "0001112223", "content": "[기존]"}])
    path = tmp_path / "대장.xlsx"
    wb.save(path)
    return path


def _post_local(client, path, **kw):
    pdf = (io.BytesIO("요구서번호 : 0004445556\n1. 요구".encode()), "b.pdf")
    return client.post("/process", data={"mode": "local", "local_path": f'"{path}"', "docs": [pdf]},
                       content_type="multipart/form-data", **kw)


def test_local_mode_hidden_on_server(client, tmp_path):
    assert "PC의 대장에 바로 저장" not in client.get("/").get_data(as_text=True)
    assert _post_local(client, tmp_path / "x.xlsx").status_code == 403


def test_local_mode_saves_into_pc_ledger_with_backup(client, local_ledger):
    from openpyxl import load_workbook

    assert "PC의 대장에 바로 저장" in client.get("/").get_data(as_text=True)
    body = _post_local(client, local_ledger).get_json()
    assert body["local"] == {"path": str(local_ledger)}
    rid = body["download_url"].rsplit("/", 1)[1]
    assert load_workbook(local_ledger).active.max_row == 4  # 저장 전에는 원래 대장 그대로

    res = client.post(f"/save-local/{rid}", json={})
    assert res.status_code == 200
    assert [c.value for c in load_workbook(local_ledger).active["B"][3:5]] == ["0001112223", "0004445556"]
    backup = local_ledger.with_name("대장_백업.xlsx")
    assert load_workbook(backup).active.max_row == 4
    assert client.post(f"/save-local/{rid}", json={}).status_code == 200  # 날짜 등을 더 고친 뒤 다시 저장 가능
    assert load_workbook(backup).active.max_row == 4  # 백업은 처리 전 원본 그대로


def test_local_save_refuses_when_ledger_changed(client, local_ledger):
    import os

    rid = _post_local(client, local_ledger).get_json()["download_url"].rsplit("/", 1)[1]
    st = os.stat(local_ledger)
    os.utime(local_ledger, (st.st_atime, st.st_mtime + 5))  # 처리 뒤 엑셀에서 저장한 상황
    assert client.post(f"/save-local/{rid}", json={}).status_code == 409


def test_local_mode_only_from_this_pc(client, local_ledger):
    res = _post_local(client, local_ledger, environ_base={"REMOTE_ADDR": "10.0.0.5"})
    assert res.status_code == 403


def test_local_mode_rejects_bad_path(client, local_ledger):
    assert _post_local(client, local_ledger.with_name("없는파일.xlsx")).status_code == 400
