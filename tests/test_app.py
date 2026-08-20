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
        data={"mode": "new", "pdfs": uploads},
        content_type="multipart/form-data",
    )
    assert res.status_code == 200
    doc_nos = [r["parsed"]["doc_no"] for r in res.get_json()["results"]]
    assert doc_nos == [f"000000000{i}" for i in range(5)]
