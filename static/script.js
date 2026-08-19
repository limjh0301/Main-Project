const MAX_PDF = 5;

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
    excelSection.style.display = radio.value === "existing" && radio.checked ? "" : "none";
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

// PDF 선택
pdfDrop.addEventListener("click", () => pdfInput.click());
pdfInput.addEventListener("change", () => addPdfs(pdfInput.files));
setupDrag(pdfDrop, addPdfs);

function addPdfs(files) {
  for (const file of files) {
    if (!/\.pdf$/i.test(file.name)) {
      showStatus(`PDF 파일이 아닙니다: ${file.name}`, true);
      continue;
    }
    if (pdfFiles.some((f) => f.name === file.name && f.size === file.size)) continue;
    if (pdfFiles.length >= MAX_PDF) {
      showStatus(`PDF는 최대 ${MAX_PDF}개까지 선택할 수 있습니다.`, true);
      break;
    }
    pdfFiles.push(file);
  }
  pdfInput.value = "";
  renderPdfList();
}

function renderPdfList() {
  pdfList.innerHTML = "";
  pdfFiles.forEach((file, idx) => {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = `📄 ${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "✕";
    del.addEventListener("click", () => {
      pdfFiles.splice(idx, 1);
      renderPdfList();
    });
    li.append(name, del);
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
    showStatus("요구서 PDF 파일을 선택해 주세요.", true);
    return;
  }

  const data = new FormData();
  data.append("mode", mode);
  if (document.getElementById("force-ocr").checked) data.append("force_ocr", "on");
  if (mode === "existing") data.append("excel", excelFile);
  pdfFiles.forEach((f) => data.append("pdfs", f));

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

function renderResult(json) {
  document.getElementById("result-summary").textContent =
    `총 ${json.results.length}개 요구서에서 ${json.total_rows}건의 접수 내역을 관리대장에 추가했습니다.`;

  const filesBox = document.getElementById("result-files");
  filesBox.innerHTML = "";
  const fields = [
    ["committee", "소관위원회"],
    ["request_date", "요구일자"],
    ["deadline", "제출기한"],
    ["doc_no", "요구서번호"],
    ["member", "요구의원/기관"],
    ["party", "정당"],
    ["district", "지역구"],
    ["requester", "요구자"],
    ["email", "요구자 이메일"],
  ];

  for (const r of json.results) {
    const div = document.createElement("div");
    div.className = "result-file";

    const h3 = document.createElement("h3");
    h3.textContent = `📄 ${r.filename} — ${r.row_count}건`;
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = r.method === "ocr" ? "OCR 추출" : "텍스트 추출";
    h3.appendChild(badge);
    div.appendChild(h3);

    const table = document.createElement("table");
    for (const [key, label] of fields) {
      const value = r.parsed[key];
      if (!value) continue;
      const tr = document.createElement("tr");
      const th = document.createElement("th");
      th.textContent = label;
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(th, td);
      table.appendChild(tr);
    }
    if (r.parsed.items.length > 0) {
      const tr = document.createElement("tr");
      const th = document.createElement("th");
      th.textContent = "자료 요구내용";
      const td = document.createElement("td");
      r.parsed.items.forEach((item, i) => {
        if (i > 0) td.appendChild(document.createElement("br"));
        td.appendChild(document.createTextNode(item));
      });
      tr.append(th, td);
      table.appendChild(tr);
    }
    div.appendChild(table);
    filesBox.appendChild(div);
  }

  const link = document.getElementById("download-link");
  link.href = `${json.download_url}?name=${encodeURIComponent(json.download_name)}`;
  resultBox.hidden = false;
  resultBox.scrollIntoView({ behavior: "smooth" });
}
