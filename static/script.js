const CONFIG = window.APP_CONFIG;
const MAX_PDF = CONFIG.maxPdf;
const MAX_HWP = CONFIG.maxHwp;
const PREVIEW_ITEMS = 8; // 첨부 항목이 많을 때 결과 미리보기에 보여줄 행 수

const form = document.getElementById("process-form");
const excelSection = document.getElementById("excel-section");
const excelDrop = document.getElementById("excel-drop");
const excelDropText = document.getElementById("excel-drop-text");
const excelInput = document.getElementById("excel-input");
const pdfDrop = document.getElementById("pdf-drop");
const pdfInput = document.getElementById("pdf-input");
const pdfList = document.getElementById("pdf-list");
const statusBox = document.getElementById("status");
const resultBox = document.getElementById("result");
const submitBtn = document.getElementById("submit-btn");

let excelFile = null;
let pdfFiles = [];

// 모드 전환: 새 관리대장 생성 시 엑셀 선택 영역 숨김
document.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    excelSection.style.display = radio.value === "existing" ? "" : "none";
  });
});

// 엑셀 선택
excelDrop.addEventListener("click", () => excelInput.click());
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
  excelDropText.textContent = `✔ ${file.name}`;
}

// 요구서 PDF · 첨부 한글파일 선택
pdfDrop.addEventListener("click", () => pdfInput.click());
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
    const del = el("button", "✕");
    del.type = "button";
    del.addEventListener("click", () => {
      pdfFiles.splice(idx, 1);
      renderPdfList();
    });
    li.append(el("span", `${isHwp(file) ? "📎" : "📄"} ${file.name} (${(file.size / 1024).toFixed(0)} KB)`), del);
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
  if (pdfFiles.length === 0) {
    showStatus("요구서 PDF 또는 첨부 한글파일을 선택해 주세요.", true);
    return;
  }

  const data = new FormData();
  data.append("mode", mode);
  if (document.getElementById("force-ocr").checked) data.append("force_ocr", "on");
  if (mode === "existing") data.append("excel", excelFile);
  pdfFiles.forEach((f) => data.append("docs", f));

  submitBtn.disabled = true;
  resultBox.hidden = true;
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

function showStatus(message, isError) {
  statusBox.hidden = false;
  statusBox.textContent = message;
  statusBox.className = `status ${isError ? "error" : "info"}`;
}

const METHOD_LABEL = { ocr: "OCR 추출", hwp: "한글 첨부" };

function renderResult(json) {
  document.getElementById("result-summary").textContent =
    `요구서 ${json.results.length}건, 관리대장 ${json.row_count}행을 추가했습니다.`;

  const filesBox = document.getElementById("result-files");
  filesBox.innerHTML = "";

  for (const r of json.results) {
    const h3 = el("h3", `📄 ${r.filename}`);
    h3.appendChild(el("span", METHOD_LABEL[r.method] || "텍스트 추출", "badge"));

    const table = el("table");
    const addRow = (label, td) => {
      const tr = el("tr");
      tr.append(el("th", label), td);
      table.appendChild(tr);
    };
    for (const { key, label } of CONFIG.fields) {
      if (r.parsed[key]) addRow(label, el("td", r.parsed[key]));
    }
    if (r.attachments.length > 0) {
      addRow("첨부", el("td", `📎 ${r.attachments.join(", ")} — ${r.items.length}개 항목을 각각 1행으로 기록`));
    }
    if (r.items.length > 0) {
      // 첨부 항목은 여러 줄이라 첫 줄만 미리 보여준다
      const td = el("td");
      r.items.slice(0, PREVIEW_ITEMS).forEach((item, i) => {
        if (i > 0) td.appendChild(document.createElement("br"));
        td.appendChild(document.createTextNode(r.attachments.length ? item.split("\n")[0] : item));
      });
      if (r.items.length > PREVIEW_ITEMS) {
        td.appendChild(document.createElement("br"));
        td.appendChild(el("span", `… 외 ${r.items.length - PREVIEW_ITEMS}개 항목 (엑셀에서 확인)`, "muted"));
      }
      addRow(CONFIG.contentLabel, td);
    }

    const div = el("div", "", "result-file");
    div.append(h3, table);
    filesBox.appendChild(div);
  }

  const link = document.getElementById("download-link");
  link.href = `${json.download_url}?name=${encodeURIComponent(json.download_name)}`;
  resultBox.hidden = false;
  resultBox.scrollIntoView({ behavior: "smooth" });
}
