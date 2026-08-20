"""국회 요구자료 목록화 시스템.

의정자료전자유통시스템에서 받은 요구서 PDF를 업로드하면 텍스트를 추출(OCR 포함)하고,
필요한 항목을 파싱해 엑셀 관리대장에 자동으로 누적한다.
업로드 파일과 결과 엑셀은 처리 후 임시 폴더에서 관리되며 서버에 영구 저장하지 않는다.
"""

import os
import re
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from flask import Flask, jsonify, render_template, request, send_file

from extractor.ledger import (
    CONTENT_LABEL,
    LedgerFormatError,
    UI_FIELDS,
    append_rows,
    create_ledger,
    enrich_member_fields,
    open_ledger,
)
from extractor.parser import parse_request
from extractor.pdf_text import extract_text, ocr_available

PORT = 5000
URL = f"http://127.0.0.1:{PORT}"
MAX_PDF_COUNT = 5
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
RESULT_TTL_SECONDS = 30 * 60  # 결과 엑셀 보관 시간
CLEANUP_INTERVAL_SECONDS = 5 * 60  # 만료 파일 청소 최소 간격
DEFAULT_BASE_NAME = "요구자료관리대장"

# 결과 파일명 날짜 접미사: 형식과 제거용 정규식은 항상 함께 수정할 것
_DATE_SUFFIX_FORMAT = "%y%m%d"
_DATE_SUFFIX_RE = re.compile(r"_\d{6}$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

RESULT_DIR = os.path.join(tempfile.gettempdir(), "yogu-results")
os.makedirs(RESULT_DIR, exist_ok=True)

_last_cleanup = 0.0


def _dated_name(base_name: str) -> str:
    """이전 날짜 접미사를 떼고 오늘 날짜 접미사를 붙인 결과 파일명을 만든다."""
    base = _DATE_SUFFIX_RE.sub("", base_name)
    return f"{base}_{date.today():{_DATE_SUFFIX_FORMAT}}.xlsx"


def _cleanup_results() -> None:
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < CLEANUP_INTERVAL_SECONDS:
        return
    _last_cleanup = now
    for name in os.listdir(RESULT_DIR):
        path = os.path.join(RESULT_DIR, name)
        try:
            if now - os.path.getmtime(path) > RESULT_TTL_SECONDS:
                os.remove(path)
        except OSError:
            pass


@app.get("/")
def index():
    return render_template(
        "index.html",
        ocr_available=ocr_available(),
        max_pdf=MAX_PDF_COUNT,
        ui_fields=UI_FIELDS,
        content_label=CONTENT_LABEL,
    )


@app.post("/process")
def process():
    mode = request.form.get("mode", "new")
    force_ocr = request.form.get("force_ocr") == "on"
    pdf_files = [f for f in request.files.getlist("pdfs") if f and f.filename]

    if not pdf_files:
        return jsonify({"error": "요구서 PDF 파일을 선택해 주세요."}), 400
    if len(pdf_files) > MAX_PDF_COUNT:
        return jsonify({"error": f"PDF는 최대 {MAX_PDF_COUNT}개까지 선택할 수 있습니다."}), 400
    for f in pdf_files:
        if not f.filename.lower().endswith(".pdf"):
            return jsonify({"error": f"PDF 파일이 아닙니다: {f.filename}"}), 400

    _cleanup_results()

    with tempfile.TemporaryDirectory() as workdir:
        # 관리대장 준비: 기존 파일 사용 또는 새로 생성
        if mode == "existing":
            excel_file = request.files.get("excel")
            if not excel_file or not excel_file.filename:
                return jsonify({"error": "기존 엑셀 관리대장 파일을 선택해 주세요."}), 400
            if not excel_file.filename.lower().endswith((".xlsx", ".xlsm")):
                return jsonify({"error": "엑셀 파일(.xlsx)만 선택할 수 있습니다."}), 400
            excel_path = os.path.join(workdir, "ledger.xlsx")
            excel_file.save(excel_path)
            try:
                wb = open_ledger(excel_path)
            except LedgerFormatError as e:
                return jsonify({"error": str(e)}), 400
            except Exception:
                return jsonify({"error": "엑셀 파일을 열 수 없습니다. 파일이 손상되었는지 확인해 주세요."}), 400
            base_name = os.path.splitext(os.path.basename(excel_file.filename))[0]
        else:
            wb = create_ledger()
            base_name = DEFAULT_BASE_NAME

        # 업로드 파일을 모두 저장한 뒤, 추출(OCR 포함)은 병렬로 수행
        # 원본 파일명 대신 순번으로 저장한다 — 한글 파일명은 secure_filename이
        # 전부 지워 서로 같은 이름이 되고, 뒤 파일이 앞 파일을 덮어쓴다
        pdf_paths = []
        for i, f in enumerate(pdf_files):
            pdf_path = os.path.join(workdir, f"upload-{i}.pdf")
            f.save(pdf_path)
            pdf_paths.append(pdf_path)

        try:
            with ThreadPoolExecutor(max_workers=len(pdf_paths)) as pool:
                extracted = list(
                    pool.map(lambda p: extract_text(p, force_ocr=force_ocr), pdf_paths)
                )
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 422

        results = []
        rows = []
        for f, (text, method) in zip(pdf_files, extracted):
            # 요구의원이 국회의원 현황 명단에 있으면 소관위원회·정당·지역구를 명단 값으로 채운다
            parsed = enrich_member_fields(parse_request(text).to_dict())
            rows.append(_build_row(parsed))
            results.append({
                "filename": f.filename,
                "method": method,
                "parsed": parsed,
            })

        append_rows(wb, rows)

        result_id = uuid.uuid4().hex
        out_path = os.path.join(RESULT_DIR, f"{result_id}.xlsx")
        wb.save(out_path)

    return jsonify({
        "results": results,
        "download_url": f"/download/{result_id}",
        "download_name": _dated_name(base_name),
    })


def _build_row(parsed: dict) -> dict:
    """요구서 1건을 관리대장 1행으로 만든다. 요구내용 항목은 줄바꿈으로 합친다."""
    items = parsed.get("items") or []
    content = "\n".join(items) if items else "(요구내용 미추출 — 원본 확인 필요)"
    return {**parsed, "content": content}


@app.get("/download/<result_id>")
def download(result_id: str):
    if not all(c in "0123456789abcdef" for c in result_id):
        return jsonify({"error": "잘못된 요청입니다."}), 400
    path = os.path.join(RESULT_DIR, f"{result_id}.xlsx")
    if not os.path.isfile(path):
        return jsonify({"error": "결과 파일이 만료되었거나 존재하지 않습니다. 다시 처리해 주세요."}), 404
    name = request.args.get("name", f"{DEFAULT_BASE_NAME}.xlsx")
    if not name.lower().endswith(".xlsx"):
        name += ".xlsx"
    return send_file(path, as_attachment=True, download_name=name)


if __name__ == "__main__":
    import socket
    import threading
    import webbrowser

    # 포트가 이미 사용 중인지 먼저 확인해 명확한 안내를 준다
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if sock.connect_ex(("127.0.0.1", PORT)) == 0:
            print()
            print(f"[안내] 포트 {PORT}에서 이미 서버가 실행 중입니다.")
            print(f"       브라우저에서 {URL} 으로 바로 접속하세요.")
            webbrowser.open(URL)
            raise SystemExit(0)

    # 서버가 뜬 직후 기본 브라우저로 접속 페이지를 자동으로 연다
    threading.Timer(0.5, lambda: webbrowser.open(URL)).start()
    app.run(host="0.0.0.0", port=PORT, debug=False)
