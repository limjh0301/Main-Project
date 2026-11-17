const CONFIG = window.APP_CONFIG;
const MAX_PDF = CONFIG.maxPdf;
const MAX_HWP = CONFIG.maxHwp;

const form = document.getElementById("process-form");
const excelSection = document.getElementById("excel-section");
const excelDrop = document.getElementById("excel-drop");
const excelDropText = document.getElementById("excel-drop-text");
const excelInput = document.getElementById("excel-input");
const pdfDrop = document.getElementById("pdf-drop");
const pdfInput = document.getElementById("pdf-input");
const pdfList = document.getElementById("pdf-list");
const statusBox = document.getElementById("status");
const board = document.getElementById("board");
const submitBtn = document.getElementById("submit-btn");

let excelFile = null;
let pdfFiles = [];

const localPath = document.getElementById("local-path");
const PANELS = { local: "local-section", existing: "excel-section", new: "new-section" };
const LOCAL_PATH_KEY = "yogu:local-path";

// 모드 전환: 선택한 방식의 안내·입력 영역만 보인다
document.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    for (const [mode, id] of Object.entries(PANELS)) {
      const panel = document.getElementById(id);
      if (panel) panel.hidden = radio.value !== mode;
    }
  });
});
try { localPath.value = localStorage.getItem(LOCAL_PATH_KEY) || ""; } catch (_) {}
// 탐색기 '경로로 복사'는 앞뒤에 따옴표가 붙는다
const cleanPath = (v) => v.trim().replace(/^"(.*)"$/, "$1");

// 엑셀 선택
excelDrop.addEventListener("click", () => excelInput.click());
excelDrop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); excelInput.click(); } });
excelInput.addEventListener("change", () => setExcel(excelInput.files[0]));
setupDrag(excelDrop, (files) => setExcel(files[0]));

function setExcel(file) {
  if (!file) return;
  if (!/\.(xlsx|xlsm)$/i.test(file.name)) {
    showStatus("엑셀 파일(.xlsx)만 선택할 수 있습니다.", true);
    return;
  }
  excelFile = file;
  excelDrop.classList.add("has-file");
  excelDropText.textContent = `${file.name} 선택됨 — 다른 파일을 고르려면 다시 클릭`;
}

// 요구서 PDF · 첨부 한글파일 선택
pdfDrop.addEventListener("click", () => pdfInput.click());
pdfDrop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pdfInput.click(); } });
pdfInput.addEventListener("change", () => addPdfs(pdfInput.files));
setupDrag(pdfDrop, addPdfs);

const isHwp = (file) => /\.hwpx?$/i.test(file.name);

function addPdfs(files) {
  for (const file of files) {
    if (!/\.(pdf|hwpx?)$/i.test(file.name)) {
      showStatus(`PDF·한글 파일이 아닙니다: ${file.name}`, true);
      continue;
    }
    if (pdfFiles.some((f) => f.name === file.name && f.size === file.size)) continue;
    const sameType = pdfFiles.filter((f) => isHwp(f) === isHwp(file)).length;
    const limit = isHwp(file) ? MAX_HWP : MAX_PDF;
    if (sameType >= limit) {
      showStatus(`${isHwp(file) ? "한글 파일" : "PDF"}은 최대 ${limit}개까지 선택할 수 있습니다.`, true);
      continue;
    }
    pdfFiles.push(file);
  }
  pdfInput.value = "";
  renderPdfList();
}

// textContent 기반 요소 생성 (사용자 입력을 HTML로 해석하지 않음)
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}

function renderPdfList() {
  pdfList.innerHTML = "";
  pdfFiles.forEach((file, idx) => {
    const li = el("li");
    const del = el("button", "빼기");
    del.type = "button";
    del.setAttribute("aria-label", `${file.name} 목록에서 빼기`);
    del.addEventListener("click", () => {
      pdfFiles.splice(idx, 1);
      renderPdfList();
    });
    li.append(el("span", isHwp(file) ? "한글" : "PDF", "kind"), el("span", file.name, "name"),
      el("span", `${(file.size / 1024).toFixed(0)} KB`, "size"), del);
    pdfList.appendChild(li);
  });
  pdfDrop.classList.toggle("has-file", pdfFiles.length > 0);
}

function setupDrag(zone, onDrop) {
  ["dragenter", "dragover"].forEach((ev) =>
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      zone.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    zone.addEventListener(ev, (e) => {
      e.preventDefault();
      zone.classList.remove("dragover");
    })
  );
  zone.addEventListener("drop", (e) => onDrop(e.dataTransfer.files));
}

// 제출
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const mode = document.querySelector('input[name="mode"]:checked').value;

  if (mode === "existing" && !excelFile) {
    showStatus("기존 엑셀 관리대장 파일을 선택해 주세요.", true);
    return;
  }
  if (mode === "local" && !cleanPath(localPath.value)) {
    showStatus("대장 파일 경로를 입력해 주세요.", true);
    localPath.focus();
    return;
  }
  if (pdfFiles.length === 0) {
    showStatus("요구서 PDF 또는 첨부 한글파일을 선택해 주세요.", true);
    return;
  }

  const data = new FormData();
  data.append("mode", mode);
  if (document.getElementById("force-ocr").checked) data.append("force_ocr", "on");
  if (mode === "existing") data.append("excel", excelFile);
  if (mode === "local") {
    data.append("local_path", cleanPath(localPath.value));
    try { localStorage.setItem(LOCAL_PATH_KEY, cleanPath(localPath.value)); } catch (_) {}
  }
  pdfFiles.forEach((f) => data.append("docs", f));

  submitBtn.disabled = true;
  board.hidden = true;
  showStatus("파일을 처리하는 중입니다. OCR이 필요한 경우 수 분이 걸릴 수 있습니다…", false);

  try {
    const res = await fetch("/process", { method: "POST", body: data });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || "처리 중 오류가 발생했습니다.");
    renderResult(json);
    statusBox.hidden = true;
  } catch (err) {
    showStatus(err.message, true);
  } finally {
    submitBtn.disabled = false;
  }
});

// 새 파일 없이 대장만으로 마감 현황 보기
document.getElementById("status-btn").addEventListener("click", async () => {
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const data = new FormData();
  data.append("mode", mode);
  if (mode === "existing") {
    if (!excelFile) { showStatus("현황을 볼 관리대장 엑셀 파일을 선택해 주세요.", true); return; }
    data.append("excel", excelFile);
  } else if (mode === "local") {
    if (!cleanPath(localPath.value)) { showStatus("대장 파일 경로를 입력해 주세요.", true); localPath.focus(); return; }
    data.append("local_path", cleanPath(localPath.value));
  } else {
    showStatus("새 대장에는 아직 기록이 없습니다. 기존 대장을 선택해 주세요.", true);
    return;
  }
  try {
    const res = await fetch("/status", { method: "POST", body: data });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || "현황을 불러오지 못했습니다.");
    statusBox.hidden = true;
    window.Dash.show(json, mode === "local" ? cleanPath(localPath.value).split(/[\\/]/).pop() : excelFile.name);
  } catch (err) {
    showStatus(err.message, true);
  }
});

function showStatus(message, isError) {
  statusBox.hidden = false;
  statusBox.textContent = message;
  statusBox.className = `status ${isError ? "error" : "info"}`;
}

// 처리 결과는 분배안 보드(board.js)가 그린다
function renderResult(json) {
  window.Board.show(json);
}
