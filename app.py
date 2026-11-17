"""국회 요구자료 목록화 시스템.

의정자료전자유통시스템에서 받은 요구서 PDF를 업로드하면 텍스트를 추출(OCR 포함)하고,
필요한 항목을 파싱해 엑셀 관리대장에 자동으로 누적한다. 질의 항목을 정리한 한글(HWP/HWPX)
첨부파일을 함께 올리면 해당 질의서에 연결해 첨부의 항목을 질의 내역으로 기록한다.
요구서 1건 = 관리대장 1행이며, 질의 내역은 한 셀에 줄바꿈으로 넣는다.
PC 전용 프로그램이다(127.0.0.1에서만 접속). 관리대장은 PC의 엑셀 파일에 바로 이어 쓰고,
업로드 파일과 결과 엑셀은 처리 후 임시 폴더에서만 관리한다.
"""

import json
import os
import re
import shutil
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from flask import Flask, jsonify, render_template, request, send_file

from extractor.ledger import (
    LedgerFormatError,
    append_rows,
    create_ledger,
    enrich_member_fields,
    existing_doc_nos,
    records,
    fill_dates,
    member_names,
    next_row,
    open_ledger,
)
import io

from extractor import board, export, history, learning, roster, settings, status
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
    )


@app.get("/settings")
def settings_page():
    """설정 화면 — 담당자 명단·업무 추가/제외·배분 추가 규칙 (파일을 처리하지 않아도 바로 들어올 수 있다)."""
    return render_template("settings.html", meta={
        "org": board.org(), "tasks": [{"dept": d, "task": t} for d, t in roster.tasks()]})


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
        elif mode == "local":
            local_path = _local_ledger_path(request.form.get("local_path", ""))
            if not local_path:
                return jsonify({"error": "대장 파일 경로를 확인해 주세요. 있는 엑셀 파일(.xlsx)의 전체 경로여야 합니다."}), 400
            try:
                wb = open_ledger(local_path)
            except LedgerFormatError as e:
                return jsonify({"error": str(e)}), 400
            except Exception:
                return jsonify({"error": "대장 파일을 열 수 없습니다. 파일이 손상되었는지 확인해 주세요."}), 400
            base_name = os.path.splitext(os.path.basename(local_path))[0]
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

        rows, results, board_entries = [], [], []
        first_row, recorded = next_row(wb), existing_doc_nos(wb)
        past = history.Index(records(wb))  # 이번에 적기 전의 대장 기록 = 이전 질의
        # 담당자 명단·업무 추가/제외·추가 규칙은 앱 설정(data/settings.json)에서, 배분 이력은 대장에서 읽는다
        cfg = settings.load()
        log, rules = learning.read_log(wb), cfg["rules"]
        learner = learning.Learner(log, rules)
        names = {k: v for k, v in cfg.items() if k != "rules"}
        for i, (f, method, parsed, atts) in enumerate(entries):
            att_list = [a for _, a in atts]
            row, items, title = _build_row(parsed, att_list, f.filename)
            # 이미 대장에 있는 요구서는 다시 적지 않는다 (같은 파일을 두 번 올려도 안전)
            duplicate = bool(parsed["doc_no"]) and parsed["doc_no"] in recorded
            if not duplicate:
                rows.append(row)
                recorded.add(parsed["doc_no"])
            results.append({
                "duplicate": duplicate,
                # 제출기한을 나중에 입력받아 이 행에 채운다 (API는 행 범위를 받음)
                "rows": None if duplicate else [first_row + len(rows) - 1] * 2,
                "filename": f.filename,
                "method": method,
                "parsed": parsed,
                "attachments": [af.filename for af, _ in atts],
                "items": items,
            })
            tag = parsed["doc_no"] or f"파일{i + 1}"
            board_entries.append({
                "tag": tag if all(e["tag"] != tag for e in board_entries) else f"{tag}#{i + 1}",
                "parsed": parsed, "title": title, "filename": f.filename, "method": method,
                "rows": results[-1]["rows"], "duplicate": duplicate,
                # 이미 대장에 있는 요구서는 배분도 이미 했을 것이므로 질의를 다시 배분하지 않는다
                "questions": [] if duplicate else board.questions(parsed, att_list, title, learner, names),
            })

        append_rows(wb, rows)

        result_id = uuid.uuid4().hex
        out_path = os.path.join(RESULT_DIR, f"{result_id}.xlsx")
        wb.save(out_path)
        if mode == "local":
            # 저장 직전에 대장이 그사이 바뀌지 않았는지 확인하려고 처리 시점의 수정 시각을 남긴다
            with open(_meta_path(result_id), "w", encoding="utf-8") as f:
                json.dump({"path": local_path, "mtime": os.path.getmtime(local_path)}, f, ensure_ascii=False)

    return jsonify({
        "results": results,
        "row_count": len(rows),
        "skipped": sum(r["duplicate"] for r in results),
        "download_url": f"/download/{result_id}",
        "download_name": _dated_name(base_name),
        "board": board.build(board_entries, names, past, {
            "stats": learning.stats(log), "suggestions": learning.suggestions(log, rules)}),
        "local": {"path": local_path} if mode == "local" else None,
    })


def _local_ledger_path(raw: str) -> str:
    """PC의 대장 경로 검증: 이미 있는 .xlsx/.xlsm 파일의 절대 경로만 받는다."""
    path = os.path.abspath(os.path.expanduser(raw.strip().strip('"')))
    return path if path.lower().endswith((".xlsx", ".xlsm")) and os.path.isfile(path) else ""


def _meta_path(result_id: str) -> str:
    return os.path.join(RESULT_DIR, f"{result_id}.json")


@app.post("/save-local/<result_id>")
def save_local(result_id: str):
    """결과 대장(날짜 반영 후)을 PC의 원래 대장 파일에 덮어쓴다. 직전 내용은 _백업.xlsx로 남긴다."""
    path = _result_path(result_id)
    if not path or not os.path.isfile(_meta_path(result_id)):
        return jsonify({"error": "결과 파일이 만료되었거나 존재하지 않습니다. 다시 처리해 주세요."}), 404
    with open(_meta_path(result_id), encoding="utf-8") as f:
        meta = json.load(f)
    target = meta["path"]
    if not os.path.isfile(target) or os.path.getmtime(target) != meta["mtime"]:
        return jsonify({"error": "처리한 뒤에 대장 파일이 바뀌었습니다(엑셀에서 저장했거나 다른 사람이 수정). "
                                 "덮어쓰지 않았으니 다시 처리해 주세요."}), 409
    stem, ext = os.path.splitext(target)
    backup, tmp = f"{stem}_백업{ext}", f"{stem}.저장중{ext}"
    try:
        if not meta.get("backed_up"):  # 백업은 이번 처리 전의 원본 한 번만 (다시 저장해도 원본 백업 유지)
            shutil.copy2(target, backup)
        shutil.copyfile(path, tmp)
        os.replace(tmp, target)  # 한 번에 바꿔 써서 저장 도중 끊겨도 대장이 반쯤 쓰인 채로 남지 않게 한다
    except PermissionError:
        if os.path.exists(tmp):
            os.remove(tmp)
        return jsonify({"error": "대장 파일이 엑셀에서 열려 있어 저장하지 못했습니다. 엑셀에서 닫고 다시 눌러 주세요."}), 423
    meta.update(mtime=os.path.getmtime(target), backed_up=True)  # 날짜·명단을 더 고친 뒤 다시 저장할 수 있게
    with open(_meta_path(result_id), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return jsonify({"saved": target, "backup": backup})


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
# 요구목록 첫 항목 "1. 제목" 뒤에 붙은 세부 내용("- …", "※ …")은 줄을 나눠 적는다
_SUB_LINE = re.compile(r"\s+(?=-\s|※)")
_NUMBERED = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*(.+)$", re.S)


def _build_row(parsed: dict, attachments: list, filename: str = "") -> tuple[dict, list[str], str]:
    """요구서 1건을 관리대장 1행으로 만든다. (행, 질의 목록, 요구 제목)을 반환한다.

    자료요구서 제목 및 내용 칸은 관리대장 작성 관행대로 "[제목]" 다음 줄부터 질의를
    줄바꿈으로 적는다. 첨부 한글파일이 있으면 첨부의 항목이 질의가 되고, 첨부 앞머리의
    안내(제출기한·제출방법 등)는 비고에 적는다.
    """
    title, body = _split_title(parsed.get("items") or [])
    memo = ""
    if attachments:
        items = [item for a in attachments for item in a.items]
        notes = "\n".join(n for a in attachments for n in a.notes)
        if items and notes:
            memo = f"[첨부 안내]\n{notes}"
        body = items or ([notes] if notes else ["(첨부 항목 미추출 — 원본 확인 필요)"])
        title = title or _title_from_name(filename, parsed)
    else:
        items = parsed.get("items") or []
        body = body if (title or body) else ["(요구내용 미추출 — 원본 확인 필요)"]
    lines = ([f"[{title}]"] if title else []) + [_SUB_LINE.sub("\n", line) for line in body]
    content = "\n".join(lines)
    if len(content) > EXCEL_CELL_LIMIT:
        content = content[: EXCEL_CELL_LIMIT - len(_TRUNCATED)] + _TRUNCATED
    return {**parsed, "content": content, "memo": memo}, items, title


def _split_title(items: list[str]) -> tuple[str, list[str]]:
    """요구목록의 첫 항목 "1. 제목"을 제목으로 떼어 낸다.

    전자유통시스템 요구목록은 "1. 제목" 아래에 세부 질의가 다시 1번부터 붙거나,
    항목이 하나뿐이다. 그렇지 않으면(1. 2. 3. … 이 이어지면) 제목 없이 항목을 그대로 쓴다.
    """
    if not items:
        return "", []
    m = _NUMBERED.match(items[0])
    restarts = len(items) == 1 or re.match(r"^\s*1\s*[.)]", items[1])
    if not m or not restarts:
        return "", items
    head, *rest = _SUB_LINE.split(m.group(2).strip(), maxsplit=1)
    return head.strip(), rest + items[1:]


def _title_from_name(filename: str, parsed: dict) -> str:
    """질의서 없이 들어온 첨부의 제목: 파일명에서 요구서번호·날짜·의원명을 뺀 나머지."""
    stem = os.path.splitext(filename)[0]
    for part in (parsed.get("doc_no"), parsed.get("member")):
        if part:
            stem = re.sub(re.escape(part) + r"(?:의원실|의원)?", " ", stem)
    stem = _REQUEST_DATE_IN_NAME.sub(" ", stem)
    return re.sub(r"[\s_\-]+", " ", stem).strip()


_DATE_INPUT = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DATE_FIELDS = ("request_date", "deadline")


@app.post("/dates/<result_id>")
def set_dates(result_id: str):
    """결과 화면에서 입력·수정한 접수일자·제출기한을 결과 엑셀의 해당 행에 적는다."""
    path = _result_path(result_id)
    if not path:
        return jsonify({"error": "결과 파일이 만료되었거나 존재하지 않습니다. 다시 처리해 주세요."}), 404
    updates = (request.get_json(silent=True) or {}).get("updates") or []
    parsed_updates = []
    for u in updates:
        rows = u.get("rows") if isinstance(u, dict) else None
        if not (isinstance(rows, list) and len(rows) == 2 and all(isinstance(r, int) for r in rows)):
            return jsonify({"error": "행 정보가 올바르지 않습니다."}), 400
        values = {}
        for key in _DATE_FIELDS:
            if key not in u:
                continue
            m = _DATE_INPUT.match(str(u[key]))
            try:
                values[key] = date(*map(int, m.groups())) if m else None
            except ValueError:
                values[key] = None
            if values[key] is None:
                return jsonify({"error": "날짜 형식이 올바르지 않습니다."}), 400
        parsed_updates.append((rows, values))
    from openpyxl import load_workbook

    wb, filled = load_workbook(path), 0
    for (first, last), values in parsed_updates:
        filled += sum(fill_dates(wb, first, last, key, value) for key, value in values.items())
    wb.save(path)
    return jsonify({"filled": filled})


@app.get("/api/settings")
def get_settings():
    """앱 설정(담당자 명단·업무 추가/제외·배분 추가 규칙)."""
    return jsonify({"settings": settings.load(), "exists": settings.exists()})


@app.post("/api/settings")
def put_settings():
    """설정을 저장한다. 보낸 항목만 바꾸고 나머지는 그대로 둔다 (예: 결과 화면은 명단만 보냄)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "설정 형식이 올바르지 않습니다."}), 400
    current = settings.load()
    merged = {k: data[k] if k in data else v for k, v in current.items()}
    return jsonify({"settings": settings.save(merged)})


@app.post("/api/settings/rules")
def add_setting_rule():
    """승인한 '키워드 → 부서' 규칙을 설정에 더한다 (같은 키워드는 새 부서로 바꿈). 다음 처리부터 적용."""
    data = request.get_json(silent=True) or {}
    keyword, dept = _text(data.get("keyword"), 40), _text(data.get("dept"), 40)
    if len(keyword) < 2 or not dept:
        return jsonify({"error": "키워드(2글자 이상)와 부서가 필요합니다."}), 400
    cfg = settings.load()
    rules = [r for r in cfg["rules"] if r["keyword"] != keyword]
    rules.append({"keyword": keyword, "dept": dept, "added": date.today().isoformat(),
                  "basis": _text(data.get("basis"), 200)})
    return jsonify({"rules": settings.save({**cfg, "rules": rules})["rules"]})


@app.post("/api/settings/import")
def import_settings():
    """기존 대장의 '부서별 담당자'·'배분 추가 규칙' 시트를 읽어 보여 준다. 저장은 화면에서 확인한 뒤 /api/settings로."""
    from openpyxl import load_workbook

    f = request.files.get("excel")
    if not f or not f.filename.lower().endswith((".xlsx", ".xlsm")):
        return jsonify({"error": "대장 엑셀 파일(.xlsx)을 선택해 주세요."}), 400
    try:
        wb = load_workbook(f.stream, read_only=False)
    except Exception:
        return jsonify({"error": "엑셀 파일을 열 수 없습니다. 파일이 손상되었는지 확인해 주세요."}), 400
    if roster.SHEET_NAME not in wb.sheetnames and learning.RULE_SHEET not in wb.sheetnames:
        return jsonify({"error": f"'{roster.SHEET_NAME}'·'{learning.RULE_SHEET}' 시트가 없는 파일입니다."}), 400
    data = settings.from_workbook(wb)
    return jsonify({"settings": data, "summary": settings.summary(data), "current": settings.summary(settings.load())})


@app.get("/api/settings/export")
def export_settings():
    """현재 설정을 기존 시트 양식('부서별 담당자'·'배분 추가 규칙') 엑셀로 내려준다 (인수인계용)."""
    buf = io.BytesIO()
    settings.to_workbook(settings.load()).save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"담당자설정_{date.today():%y%m%d}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.get("/api/settings/backups")
def list_setting_backups():
    return jsonify({"backups": settings.backups()})


@app.post("/api/settings/restore")
def restore_settings():
    """백업 파일의 설정으로 되돌린다 (되돌리기 직전 설정도 백업됨)."""
    try:
        restored = settings.restore(_text((request.get_json(silent=True) or {}).get("name"), 80))
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    return jsonify({"settings": restored})


@app.post("/export")
def export_assignments():
    """결과 화면에서 최종 확인한 업무 분장내역을 엑셀로 내려준다 (서버에 저장하지 않음)."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "분장내역 형식이 올바르지 않습니다."}), 400
    rows, channel = export.clean(data)
    if not rows:
        return jsonify({"error": "내보낼 질의가 없습니다."}), 400
    buf = io.BytesIO()
    export.build(rows, channel).save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"업무분장내역_{date.today():%y%m%d}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/status")
def ledger_status():
    """새 파일 없이 관리대장만으로 마감 현황을 본다 (기존 대장 업로드 또는 PC의 대장)."""
    from openpyxl import load_workbook

    mode = request.form.get("mode", "existing")
    try:
        if mode == "local":
            path = _local_ledger_path(request.form.get("local_path", ""))
            if not path:
                return jsonify({"error": "대장 파일 경로를 확인해 주세요."}), 400
            wb = open_ledger(path)
        else:
            excel_file = request.files.get("excel")
            if not excel_file or not excel_file.filename.lower().endswith((".xlsx", ".xlsm")):
                return jsonify({"error": "관리대장 엑셀 파일을 선택해 주세요."}), 400
            wb = load_workbook(excel_file.stream)  # 양식 검증은 status.build 안의 records()가 한다
    except LedgerFormatError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        return jsonify({"error": "엑셀 파일을 열 수 없습니다. 파일이 손상되었는지 확인해 주세요."}), 400
    try:
        return jsonify(status.build(wb))
    except LedgerFormatError as e:
        return jsonify({"error": str(e)}), 400


@app.get("/status/<result_id>")
def result_status(result_id: str):
    """방금 처리한 결과 대장의 마감 현황."""
    path = _result_path(result_id)
    if not path:
        return jsonify({"error": "결과 파일이 만료되었거나 존재하지 않습니다. 다시 처리해 주세요."}), 404
    from openpyxl import load_workbook

    return jsonify(status.build(load_workbook(path)))


def _text(v, limit: int = 2000) -> str:
    return v.strip()[:limit] if isinstance(v, str) else ""


@app.post("/log/<result_id>")
def save_log(result_id: str):
    """질의별 모델 배분·확정 부서를 결과 대장의 '배분 이력' 시트에 적는다 (정확도·규칙 제안의 재료)."""
    path = _result_path(result_id)
    if not path:
        return jsonify({"error": "결과 파일이 만료되었거나 존재하지 않습니다. 다시 처리해 주세요."}), 404
    entries = (request.get_json(silent=True) or {}).get("entries")
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        return jsonify({"error": "배분 이력 형식이 올바르지 않습니다."}), 400
    entries = [{k: _text(e.get(k), 40 if k != "text" else 2000) for k in ("doc", "key", "text", "model", "final")}
               for e in entries]
    from openpyxl import load_workbook

    wb = load_workbook(path)
    n = learning.write_log(wb, entries)
    wb.save(path)
    return jsonify({"written": n})


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
    app.run(host="127.0.0.1", port=PORT, debug=False)  # 이 PC에서만 접속 (PC 전용 프로그램)
