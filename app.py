"""국회 요구자료 목록화 시스템.

의정자료전자유통시스템에서 받은 요구서 PDF를 업로드하면 텍스트를 추출(OCR 포함)하고,
필요한 항목을 파싱해 엑셀 관리대장에 자동으로 누적한다. 질의 항목을 정리한 한글(HWP/HWPX)
첨부파일을 함께 올리면 해당 질의서에 연결해 첨부의 항목을 질의 내역으로 기록한다.
요구서 1건 = 관리대장 1행이며, 질의 내역은 한 셀에 줄바꿈으로 넣는다.
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
    fill_deadline,
    member_names,
    next_row,
    open_ledger,
)
from extractor.hwp_text import HWP_EXTENSIONS, HwpReadError, extract_hwp_text
from extractor.parser import ParsedRequest, parse_attachment, parse_request
from extractor.pdf_text import extract_text, ocr_available

PORT = 5000
URL = f"http://127.0.0.1:{PORT}"
MAX_PDF_COUNT = 5
MAX_HWP_COUNT = 5
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
RESULT_TTL_SECONDS = 30 * 60  # 결과 엑셀 보관 시간
CLEANUP_INTERVAL_SECONDS = 5 * 60  # 만료 파일 청소 최소 간격
DEFAULT_BASE_NAME = "요구자료관리대장"
EXCEL_CELL_LIMIT = 32767  # 엑셀 한 셀에 들어가는 최대 글자 수

# 결과 파일명 날짜 접미사: 형식과 제거용 정규식은 항상 함께 수정할 것
_DATE_SUFFIX_FORMAT = "%y%m%d"
_DATE_SUFFIX_RE = re.compile(r"_\d{6}$")
# 의정자료전자유통시스템 첨부파일명은 요구서번호(10자리)로 시작한다
_DOC_NO_IN_NAME = re.compile(r"(?<!\d)\d{10}(?!\d)")
# 질의서 PDF 파일명은 요구일자(YYMMDD)로 끝난다 — 질의서 본문에는 요구일자가 인쇄되지 않는다
_REQUEST_DATE_IN_NAME = re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})$")
# 파일명에서 본문에 없는 값을 채우는 항목 — 본문 값이 있으면 본문 값을 쓴다
NAME_FIELDS = ("doc_no", "request_date", "member")
_member_in_name: re.Pattern | None = None

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
        max_hwp=MAX_HWP_COUNT,
        ui_fields=UI_FIELDS,
        content_label=CONTENT_LABEL,
    )


@app.post("/process")
def process():
    mode = request.form.get("mode", "new")
    force_ocr = request.form.get("force_ocr") == "on"
    uploads = [f for f in request.files.getlist("docs") if f and f.filename]

    if not uploads:
        return jsonify({"error": "요구서 PDF 또는 첨부 한글파일을 선택해 주세요."}), 400
    pdf_files, hwp_files = [], []
    for f in uploads:
        name = f.filename.lower()
        if name.endswith(".pdf"):
            pdf_files.append(f)
        elif name.endswith(HWP_EXTENSIONS):
            hwp_files.append(f)
        else:
            return jsonify({"error": f"PDF·한글 파일이 아닙니다: {f.filename}"}), 400
    if len(pdf_files) > MAX_PDF_COUNT:
        return jsonify({"error": f"PDF는 최대 {MAX_PDF_COUNT}개까지 선택할 수 있습니다."}), 400
    if len(hwp_files) > MAX_HWP_COUNT:
        return jsonify({"error": f"한글 파일은 최대 {MAX_HWP_COUNT}개까지 선택할 수 있습니다."}), 400

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

        # 원본 파일명 대신 순번으로 저장한다 — 한글 파일명은 secure_filename이
        # 전부 지워 서로 같은 이름이 되고, 뒤 파일이 앞 파일을 덮어쓴다
        def save(f, idx):
            path = os.path.join(workdir, f"upload-{idx}{os.path.splitext(f.filename)[1].lower()}")
            f.save(path)
            return path

        pdf_paths = [save(f, i) for i, f in enumerate(pdf_files)]
        hwp_paths = [save(f, len(pdf_files) + i) for i, f in enumerate(hwp_files)]

        # PDF 추출(OCR 포함)은 병렬로 수행
        extracted = []
        if pdf_paths:
            try:
                with ThreadPoolExecutor(max_workers=len(pdf_paths)) as pool:
                    extracted = list(
                        pool.map(lambda p: extract_text(p, force_ocr=force_ocr), pdf_paths)
                    )
            except RuntimeError as e:
                return jsonify({"error": str(e)}), 422

        attachments = []
        for f, path in zip(hwp_files, hwp_paths):
            try:
                attachments.append(parse_attachment(extract_hwp_text(path)))
            except HwpReadError as e:
                return jsonify({"error": f"{f.filename}: {e}"}), 422

        # 본문에 없는 요구서번호·요구일자·요구의원은 파일명으로 채우고, 요구의원이 국회의원 현황
        # 명단에 있으면 소관위원회·정당·지역구를 명단 값으로 채운다
        parsed_list = [
            enrich_member_fields(_fill_from_name(parse_request(text).to_dict(), f.filename))
            for f, (text, _) in zip(pdf_files, extracted)
        ]

        linked = [[] for _ in pdf_files]
        standalone = []
        for f, att in zip(hwp_files, attachments):
            idx = _match_request(f.filename, parsed_list)
            (linked[idx] if idx is not None else standalone).append((f, att))

        # 질의서에 연결되지 않은 첨부는 파일명의 요구서번호·요구일자·요구의원으로 별도 기록한다
        entries = [(f, method, parsed, linked[i])
                   for i, (f, parsed, (_, method)) in enumerate(zip(pdf_files, parsed_list, extracted))]
        for f, att in standalone:
            parsed = enrich_member_fields(_fill_from_name(ParsedRequest().to_dict(), f.filename))
            entries.append((f, "hwp", parsed, [(f, att)]))

        rows, results = [], []
        first_row = next_row(wb)
        for f, method, parsed, atts in entries:
            row, items = _build_row(parsed, [a for _, a in atts])
            rows.append(row)
            results.append({
                # 제출기한을 나중에 입력받아 이 행에 채운다 (API는 행 범위를 받음)
                "rows": [first_row + len(rows) - 1] * 2,
                "filename": f.filename,
                "method": method,
                "parsed": parsed,
                "attachments": [af.filename for af, _ in atts],
                "items": items,
            })

        append_rows(wb, rows)

        result_id = uuid.uuid4().hex
        out_path = os.path.join(RESULT_DIR, f"{result_id}.xlsx")
        wb.save(out_path)

    return jsonify({
        "results": results,
        "row_count": len(rows),
        "download_url": f"/download/{result_id}",
        "download_name": _dated_name(base_name),
    })


def _fill_from_name(parsed: dict, filename: str) -> dict:
    """본문에서 못 찾은 요구서번호·요구일자·요구의원을 파일명에서 채운다.

    채운 항목은 parsed["from_name"]에 남겨 결과 화면에서 '파일명' 표시를 한다.
    """
    found = {
        "doc_no": (m.group() if (m := _DOC_NO_IN_NAME.search(filename)) else ""),
        "request_date": _request_date_from_name(filename, parsed.get("deadline", "")),
        "member": _member_from_name(filename),
    }
    parsed["from_name"] = [k for k in NAME_FIELDS if not parsed.get(k) and found[k]]
    for k in parsed["from_name"]:
        parsed[k] = found[k]
    return parsed


def _member_from_name(filename: str) -> str:
    """파일명에서 국회의원 현황 명단의 의원명을 찾는다.

    '김현'이 '김현정'에 걸리지 않도록 이름 앞뒤가 다른 한글 글자가 아닐 때만 인정한다
    (뒤에 '의원'·'위원'이 붙는 것은 허용).
    """
    global _member_in_name
    if _member_in_name is None:
        names = "|".join(map(re.escape, member_names()))
        _member_in_name = re.compile(rf"(?<![가-힣])({names})(?=의원|위원|[^가-힣]|$)")
    m = _member_in_name.search(os.path.splitext(filename)[0])
    return m.group(1) if m else ""


def _request_date_from_name(filename: str, deadline: str) -> str:
    """파일명 끝의 YYMMDD를 요구일자(YYYY-MM-DD)로 읽는다. 날짜가 아니거나 제출기한보다 늦으면 빈 값."""
    m = _REQUEST_DATE_IN_NAME.search(os.path.splitext(filename)[0])
    if not m:
        return ""
    try:
        d = date(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return ""
    if deadline and f"{d:%Y.%m.%d}" > deadline:
        return ""
    return d.isoformat()


def _match_request(filename: str, parsed_list: list[dict]) -> int | None:
    """첨부 한글파일이 어느 질의서의 첨부인지 찾는다. 못 찾으면 None."""
    m = _DOC_NO_IN_NAME.search(filename)
    if m:
        return next((i for i, p in enumerate(parsed_list) if p["doc_no"] == m.group()), None)
    # 파일명에 요구서번호가 없으면 "첨부 파일 참고"류 질의서가 하나뿐일 때만 연결한다
    refs = [i for i, p in enumerate(parsed_list) if any("첨부" in item for item in p["items"])]
    if len(refs) == 1:
        return refs[0]
    return 0 if len(parsed_list) == 1 else None


_TRUNCATED = "\n… (엑셀 한 칸 글자 수 한도로 이하 생략 — 원본 확인)"


def _build_row(parsed: dict, attachments: list) -> tuple[dict, list[str]]:
    """요구서 1건을 관리대장 1행으로 만든다. 질의 내역은 한 셀에 줄바꿈으로 넣는다.

    첨부 한글파일이 있으면 첨부의 항목이 질의 내역이 되고, 첨부 앞머리의 안내
    (제출기한·제출방법 등)는 비고에 적는다. (행, 질의 목록)을 반환한다.
    """
    memo = ""
    if attachments:
        items = [item for a in attachments for item in a.items]
        notes = "\n".join(n for a in attachments for n in a.notes)
        if items and notes:
            memo = f"[첨부 안내]\n{notes}"
        content = "\n".join(items) or notes or "(첨부 항목 미추출 — 원본 확인 필요)"
    else:
        items = parsed.get("items") or []
        content = "\n".join(items) or "(요구내용 미추출 — 원본 확인 필요)"
    if len(content) > EXCEL_CELL_LIMIT:
        content = content[: EXCEL_CELL_LIMIT - len(_TRUNCATED)] + _TRUNCATED
    return {**parsed, "content": content, "memo": memo}, items


_DEADLINE_INPUT = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


@app.post("/deadline/<result_id>")
def set_deadline(result_id: str):
    """결과 화면에서 직접 입력한 제출기한을 결과 엑셀의 해당 행(빈 칸만)에 적는다."""
    path = _result_path(result_id)
    if not path:
        return jsonify({"error": "결과 파일이 만료되었거나 존재하지 않습니다. 다시 처리해 주세요."}), 404
    updates = (request.get_json(silent=True) or {}).get("deadlines") or []
    from openpyxl import load_workbook

    wb, filled = load_workbook(path), 0
    for u in updates:
        m = _DEADLINE_INPUT.match(str(u.get("deadline", "")))
        rows = u.get("rows")
        if not m or not (isinstance(rows, list) and len(rows) == 2 and all(isinstance(r, int) for r in rows)):
            return jsonify({"error": "제출기한 형식이 올바르지 않습니다."}), 400
        try:
            date(*map(int, m.groups()))
        except ValueError:
            return jsonify({"error": "없는 날짜입니다."}), 400
        filled += fill_deadline(wb, rows[0], rows[1], ".".join(m.groups()))
    wb.save(path)
    return jsonify({"filled": filled})


def _result_path(result_id: str) -> str | None:
    if not result_id or not all(c in "0123456789abcdef" for c in result_id):
        return None
    path = os.path.join(RESULT_DIR, f"{result_id}.xlsx")
    return path if os.path.isfile(path) else None


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
