import io

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
    return load_workbook(io.BytesIO(res.data))["관리대장"]


ATTACHMENT_PARAGRAPHS = ["※ 9월 28일(월)까지 제출", "기관 개요", " 1) 설립근거", " 2) 주요 연혁", "2. 사업 현황"]


def test_hwp_attachment_links_to_request_by_doc_no(client, make_hwpx):
    pdf = (io.BytesIO("요구서번호 : 0007999174\n1. 다음의 자료를 요청합니다 - 첨부 파일 참고".encode()), "질의서.pdf")
    other = (io.BytesIO("요구서번호 : 0001112223\n1. 별도 요구".encode()), "다른질의서.pdf")
    hwpx = make_hwpx("0007999174_공통요구자료.hwpx", ATTACHMENT_PARAGRAPHS)
    res = _post(client, [other, pdf, (open(hwpx, "rb"), hwpx.name)])
    assert res.status_code == 200
    body = res.get_json()
    assert body["row_count"] == 4  # 다른 질의서 1행 + 첨부 항목 3행
    linked = body["results"][1]
    assert linked["attachments"] == [hwpx.name]
    assert [i.split("\n")[0] for i in linked["items"]] == [
        "1-1) [기관 개요] 설립근거", "1-2) [기관 개요] 주요 연혁", "2. 사업 현황",
    ]

    ws = _download(client, body)
    assert [ws.cell(row=r, column=1).value for r in range(2, 6)] == [
        "0001112223", "0007999174", "0007999174", "0007999174",
    ]
    assert ws.cell(row=3, column=13).value == "[첨부 안내]\n※ 9월 28일(월)까지 제출"
    assert ws.cell(row=4, column=13).value in ("", None)  # 안내는 첫 행에만


def test_hwp_without_matching_request_is_recorded_alone(client, make_hwpx):
    hwpx = make_hwpx("0005556667_요구자료.hwpx", ["1. 기관 현황", "2. 예산 현황"])
    res = _post(client, [(open(hwpx, "rb"), hwpx.name)])
    assert res.status_code == 200
    body = res.get_json()
    assert body["results"][0]["method"] == "hwp"
    assert body["results"][0]["parsed"]["doc_no"] == "0005556667"
    assert body["row_count"] == 2


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
    assert ws.cell(row=2, column=3).value == "2026-09-21"
