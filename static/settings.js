// 설정 화면 — 부서별 담당자 · 업무 추가/제외 · 배분 추가 규칙.
// 화면에서는 사본(draft)을 고치고 '저장'할 때만 data/settings.json에 쓴다. 저장하면 열려 있는 결과 화면도 명단을 다시 읽는다.
(() => {
  const META = window.SETTINGS_META;
  const SEP = "\u0001";
  const SAVED_KEY = "yogu:settings-saved"; // 결과 화면에 저장을 알리는 신호 (storage 이벤트)
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const $ = (sel) => document.querySelector(sel);
  const clone = (v) => JSON.parse(JSON.stringify(v));
  const splitList = (v) => [...new Set(String(v).split(/[,，、]/).map((x) => x.trim()).filter(Boolean))];

  let saved = null, draft = null, tab = "people", adding = null;

  // ---------- 부서·업무 ----------
  function depts() {
    const out = [];
    for (const o of META.org) for (const d of o.depts) out.push({ org: o, dept: d });
    const other = { name: "기타", i: META.org.length - 1 };
    for (const t of [...META.tasks, ...draft.custom]) if (!out.some((x) => x.dept === t.dept)) out.push({ org: other, dept: t.dept });
    return out;
  }
  const baseTasks = (d) => META.tasks.filter((t) => t.dept === d).map((t) => t.task);
  const isExcluded = (d, t) => draft.excluded.includes(`${d}|${t}`);
  const activeTasks = (d) => [...baseTasks(d).filter((t) => !isExcluded(d, t)), ...draft.custom.filter((c) => c.dept === d).map((c) => c.task)];
  const worker = (d, t) => draft.tasks[`${d}|${t}`] || "";

  // ---------- 그리기 ----------
  const inp = (k, v, label, ph = "미정", cls = "") =>
    `<input class="in${cls ? " " + cls : ""}" data-k="${esc(k)}" value="${esc(v)}" placeholder="${esc(ph)}" aria-label="${esc(label)}">`;
  const card = (org, dept, q, inner) =>
    `<section class="st-d" data-dept="${esc(dept)}" data-q="${esc(q)}" style="--c:var(--o${org.i})"><h3><i></i>${esc(dept)}</h3>${inner}</section>`;

  function peopleHtml(org, dept) {
    // 같은 사람이 맡은 업무를 한 줄로 묶어, 사람이 바뀌면 한 번에 고치게 한다
    const groups = new Map();
    for (const t of activeTasks(dept)) {
      const w = worker(dept, t);
      if (!groups.has(w)) groups.set(w, []);
      groups.get(w).push(t);
    }
    const rows = [`<div class="st-r"><span class="lab strong">총괄담당자 <span class="t3">요청 취합·안내</span></span>${inp(`ch|${dept}`, draft.channel[dept] || "", `${dept} 총괄담당자`, "없음")}</div>`];
    for (const [w, ts] of groups) {
      rows.push(`<div class="st-r"><span class="chips">${ts.map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</span>` +
        `${inp(`w|${dept}|${ts.join(SEP)}`, w, `${dept} ${ts.join(", ")} 담당자`)}</div>`);
    }
    rows.push(`<div class="st-r"><span class="lab">그 밖의 부서원 <span class="t3">쉼표로 구분</span></span>${inp(`m|${dept}`, (draft.members[dept] || []).join(", "), `${dept} 그 밖의 부서원`, "예: 홍길동, 김철수", "wide")}</div>`);
    const people = [draft.channel[dept], ...activeTasks(dept).map((t) => worker(dept, t)), ...(draft.members[dept] || [])];
    return card(org, dept, `${org.name} ${dept} ${people.join(" ")} ${activeTasks(dept).join(" ")}`, rows.join(""));
  }

  function tasksHtml(org, dept) {
    const base = baseTasks(dept), on = base.filter((t) => !isExcluded(dept, t)), off = base.filter((t) => isExcluded(dept, t));
    const custom = draft.custom.filter((c) => c.dept === dept);
    const rows = [];
    if (on.length) {
      rows.push(`<div class="st-line"><span class="lab">배분표 업무</span><span class="chips">${on.map((t) =>
        `<span class="chip">${esc(t)}<button type="button" class="x" data-act="exclude" data-d="${esc(dept)}" data-t="${esc(t)}" aria-label="${esc(t)} 업무 제외" title="배분에서 제외">×</button></span>`).join("")}</span></div>`);
    }
    if (off.length) {
      rows.push(`<div class="st-line"><span class="lab">제외한 업무</span><span class="chips">${off.map((t) =>
        `<span class="chip off">${esc(t)}<button type="button" class="restore" data-act="restore" data-d="${esc(dept)}" data-t="${esc(t)}">되살리기</button></span>`).join("")}</span></div>`);
    }
    for (const c of custom) {
      rows.push(`<div class="st-r st-custom"><span class="chips"><span class="chip added">${esc(c.task)}<button type="button" class="x" data-act="del-custom" data-d="${esc(dept)}" data-t="${esc(c.task)}" aria-label="${esc(c.task)} 추가 업무 삭제" title="추가 업무 삭제">×</button></span>` +
        `${inp(`ck|${dept}|${c.task}`, c.keywords.join(", "), `${c.task} 키워드`, "키워드 (쉼표로 구분)", "kw")}</span>` +
        `${inp(`w|${dept}|${c.task}`, worker(dept, c.task), `${dept} ${c.task} 담당자`, "담당자")}</div>`);
    }
    if (adding && adding.dept === dept) {
      rows.push(`<div class="st-add"><input class="in" data-new="task" value="${esc(adding.task || "")}" placeholder="업무 이름 (예: 청탁금지)" aria-label="추가할 업무 이름">` +
        `<input class="in" data-new="keywords" value="${esc(adding.keywords || "")}" placeholder="키워드, 쉼표로 구분 (예: 청탁금지, 김영란법)" aria-label="추가할 업무 키워드">` +
        `<input class="in" data-new="worker" value="${esc(adding.worker || "")}" placeholder="담당자" aria-label="추가할 업무 담당자">` +
        `<button type="button" class="btn sm primary" data-act="do-add">추가</button><button type="button" class="linkbtn" data-act="cancel-add">취소</button></div>`);
    } else {
      rows.push(`<div class="st-line"><button type="button" class="linkbtn" data-act="open-add" data-d="${esc(dept)}">+ 업무 추가</button></div>`);
    }
    return card(org, dept, `${org.name} ${dept} ${base.join(" ")} ${custom.map((c) => `${c.task} ${c.keywords.join(" ")}`).join(" ")}`, rows.join(""));
  }

  function deptOptions(cur) {
    return `<option value=""${cur ? "" : " selected"} disabled>부서 선택</option>` +
      META.org.map((o) => `<optgroup label="${esc(o.name)}">` + o.depts.map((d) => `<option${d === cur ? " selected" : ""}>${esc(d)}</option>`).join("") + "</optgroup>").join("") +
      (cur && !META.org.some((o) => o.depts.includes(cur)) ? `<option selected>${esc(cur)}</option>` : "");
  }
  function rulesHtml() {
    const rows = draft.rules.map((r, i) => `<tr data-q="${esc(`${r.keyword} ${r.dept} ${r.basis}`)}">
<td>${inp(`rk|${i}`, r.keyword, `${i + 1}번 규칙 키워드`, "키워드")}</td>
<td><span class="selw"><select class="in" data-k="rd|${i}" aria-label="${i + 1}번 규칙 부서">${deptOptions(r.dept)}</select></span></td>
<td class="t3 mono">${esc(r.added || "—")}</td><td class="t3">${esc(r.basis || "")}</td>
<td><button type="button" class="linkbtn danger" data-act="del-rule" data-i="${i}">삭제</button></td></tr>`).join("");
    return `<div class="st-rule-add">
<input class="in" id="st-rule-kw" placeholder="키워드 (2글자 이상, 예: 칼퇴)" aria-label="새 규칙 키워드">
<span class="selw"><select class="in" id="st-rule-dept" aria-label="새 규칙 부서">${deptOptions("")}</select></span>
<button type="button" class="btn primary sm" data-act="add-rule">규칙 추가</button></div>
<table class="st-rules"><thead><tr><th>키워드</th><th>배분 부서</th><th>추가일</th><th>근거</th><th></th></tr></thead>
<tbody>${rows || `<tr class="empty"><td colspan="5">추가한 규칙이 없습니다. 결과 화면에서 '규칙 추가' 제안을 승인하거나 여기서 직접 추가하세요.</td></tr>`}</tbody></table>`;
  }

  const HELP = {
    people: "업무 담당자를 넣으면 분배안에 자동으로 채워집니다. 비워 두면 총괄담당자가 들어갑니다.",
    tasks: "× 를 누르면 그 업무로는 배분하지 않습니다. 일회성 업무는 키워드와 함께 추가하세요.",
    rules: "질의에 키워드가 들어 있으면 기본 규칙보다 먼저 지정한 부서로 배분합니다.",
    io: "설정은 저장할 때마다 직전 내용을 백업합니다 (최근 20개).",
  };
  let backupList = null;
  const fmtSize = (n) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`);
  function ioHtml() {
    const list = backupList === null ? '<p class="t3">백업 목록을 불러오는 중…</p>'
      : backupList.length ? `<ul class="bk">${backupList.map((b) => `<li><span class="mono">${esc(b.time)}</span><span class="t3">${fmtSize(b.size)}</span>` +
        `<button type="button" class="btn sm" data-act="restore-backup" data-name="${esc(b.name)}">이 설정으로 되돌리기</button></li>`).join("")}</ul>`
      : '<p class="t3">아직 백업이 없습니다. 설정을 저장하면 직전 내용이 여기에 쌓입니다.</p>';
    return `<div class="io-grid">
<section class="io"><h3>기존 대장에서 가져오기</h3><p class="t3">관리대장(.xlsx)의 '부서별 담당자'·'배분 추가 규칙' 시트를 읽어 현재 설정을 바꿉니다. 바꾸기 전에 내용을 확인합니다.</p>
<button type="button" class="btn" data-act="pick-import">대장 파일 선택…</button></section>
<section class="io"><h3>엑셀로 내보내기</h3><p class="t3">저장된 설정을 기존 시트 양식 그대로 엑셀로 받습니다. 인수인계하거나 다른 PC로 옮길 때 쓰세요.</p>
<a class="btn" href="/api/settings/export" data-act="export">엑셀로 받기</a></section>
</div>
<section class="io"><h3>백업에서 되돌리기</h3>${list}</section>`;
  }
  async function loadBackups() {
    try { backupList = (await (await fetch("/api/settings/backups")).json()).backups; } catch (_) { backupList = []; }
    if (tab === "io") render();
  }
  function render() {
    $("#st-tab-help").textContent = HELP[tab];
    $("#st-n-rules").textContent = draft.rules.length || "";
    $("#st-q").hidden = tab === "io";
    if (tab === "io") { $("#st-body").innerHTML = ioHtml(); return; }
    if (tab === "rules") { $("#st-body").innerHTML = rulesHtml(); filter(); return; }
    let html = "", last = null;
    for (const { org, dept } of depts()) {
      if (org.name !== last) { html += `<p class="st-o" style="--c:var(--o${org.i})">${esc(org.name)}</p>`; last = org.name; }
      html += tab === "people" ? peopleHtml(org, dept) : tasksHtml(org, dept);
    }
    $("#st-body").innerHTML = html;
    filter();
  }
  function filter() {
    const t = $("#st-q").value.trim();
    document.querySelectorAll(".st-d").forEach((s) => s.classList.toggle("hide", !!t && !s.dataset.q.includes(t) && !(adding && adding.dept === s.dataset.dept)));
    document.querySelectorAll(".st-o").forEach((o) => {
      let n = o.nextElementSibling, any = false;
      while (n && n.classList.contains("st-d")) { any ||= !n.classList.contains("hide"); n = n.nextElementSibling; }
      o.classList.toggle("hide", !any);
    });
    document.querySelectorAll(".st-rules tbody tr[data-q]").forEach((r) => r.classList.toggle("hide", !!t && !r.dataset.q.includes(t)));
  }

  // ---------- 고치기 ----------
  const dirty = () => JSON.stringify(draft) !== JSON.stringify(saved);
  function updateBar() {
    const d = dirty();
    $("#st-save").disabled = !d; $("#st-revert").disabled = !d;
    $("#st-state").textContent = d ? "저장하지 않은 변경이 있습니다" : "저장된 설정";
    $("#st-savebar").classList.toggle("dirty", d);
  }
  // 입력하는 즉시 draft에 반영 (다시 그려도 입력이 지워지지 않는다)
  function onInput(e) {
    const el = e.target;
    if (el.dataset.new && adding) { adding[el.dataset.new] = el.value; return; }
    if (!el.dataset.k) return;
    const [kind, a, b] = el.dataset.k.split("|"), v = el.value.trim();
    if (kind === "ch") { if (v) draft.channel[a] = v; else delete draft.channel[a]; }
    else if (kind === "m") { const list = splitList(v); if (list.length) draft.members[a] = list; else delete draft.members[a]; }
    else if (kind === "w") for (const t of b.split(SEP)) { if (v) draft.tasks[`${a}|${t}`] = v; else delete draft.tasks[`${a}|${t}`]; }
    else if (kind === "ck") { const c = draft.custom.find((x) => x.dept === a && x.task === b); if (c) c.keywords = splitList(v); }
    else if (kind === "rk") draft.rules[+a].keyword = v;
    else if (kind === "rd") draft.rules[+a].dept = v;
    updateBar();
  }
  function rerender(focusSel) { render(); updateBar(); if (focusSel) document.querySelector(focusSel)?.focus(); }
  function onClick(e) {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    const d = b.dataset.d, t = b.dataset.t;
    switch (b.dataset.act) {
      case "exclude": draft.excluded.push(`${d}|${t}`); delete draft.tasks[`${d}|${t}`]; rerender(); break;
      case "restore": draft.excluded = draft.excluded.filter((k) => k !== `${d}|${t}`); rerender(); break;
      case "del-custom":
        draft.custom = draft.custom.filter((c) => !(c.dept === d && c.task === t)); delete draft.tasks[`${d}|${t}`]; rerender(); break;
      case "open-add": adding = { dept: d }; rerender(`.st-d[data-dept="${CSS.escape(d)}"] [data-new="task"]`); break;
      case "cancel-add": adding = null; rerender(); break;
      case "do-add": {
        const task = (adding.task || "").trim(), dept = adding.dept;
        if (!task) { toast("업무 이름을 입력해 주세요"); document.querySelector('[data-new="task"]')?.focus(); return; }
        if (baseTasks(dept).includes(task) || draft.custom.some((c) => c.dept === dept && c.task === task)) { toast(`${dept}에 이미 있는 업무입니다`); return; }
        draft.custom.push({ dept, task, keywords: splitList(adding.keywords || "") });
        if ((adding.worker || "").trim()) draft.tasks[`${dept}|${task}`] = adding.worker.trim();
        adding = null; rerender(); toast(`${dept}에 '${task}' 업무를 추가했습니다 — 저장하면 반영됩니다`); break;
      }
      case "add-rule": {
        const kw = $("#st-rule-kw").value.trim(), dept = $("#st-rule-dept").value;
        if (kw.length < 2) { toast("키워드는 2글자 이상 입력해 주세요"); $("#st-rule-kw").focus(); return; }
        if (!dept) { toast("배분할 부서를 골라 주세요"); $("#st-rule-dept").focus(); return; }
        if (draft.rules.some((r) => r.keyword === kw)) { toast(`'${kw}' 규칙이 이미 있습니다`); return; }
        draft.rules.unshift({ keyword: kw, dept, added: new Date().toLocaleDateString("sv-SE"), basis: "직접 추가" });
        rerender("#st-rule-kw"); break;
      }
      case "del-rule": draft.rules.splice(+b.dataset.i, 1); rerender(); break;
      case "pick-import": $("#st-import").click(); break;
      case "export":
        if (dirty()) toast("저장하지 않은 변경은 빠집니다 — 저장된 설정을 내보냅니다");
        break;
      case "restore-backup": restoreBackup(b.dataset.name, b.closest("li").querySelector(".mono").textContent); break;
    }
  }

  async function saveAll() {
    const bad = draft.rules.find((r) => r.keyword.length < 2 || !r.dept);
    if (bad) { setTab("rules"); toast("키워드(2글자 이상)와 부서가 모두 있어야 규칙을 저장할 수 있습니다"); return; }
    $("#st-save").disabled = true;
    try {
      const res = await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft) });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(j.error || "저장하지 못했습니다.");
      saved = j.settings; draft = clone(saved); adding = null;
      $("#st-first").hidden = true;
      try { localStorage.setItem(SAVED_KEY, String(Date.now())); } catch (_) {}
      rerender(); loadBackups();
      toast(fromResult ? "저장했습니다 — 결과 화면의 담당자 목록에도 반영됩니다" : "저장했습니다 — 다음 파일 처리부터 반영됩니다");
    } catch (err) { toast(err.message); updateBar(); }
  }

  // ---------- 가져오기·되돌리기 ----------
  const counts = (m) => `총괄담당자 ${m.channel}명 · 업무 담당 ${m.tasks}건 · 부서원 ${m.members}명 · 제외 업무 ${m.excluded}개 · 추가 업무 ${m.custom}개 · 추가 규칙 ${m.rules}개`;
  async function importFile(file) {
    const fd = new FormData(); fd.append("excel", file);
    try {
      const res = await fetch("/api/settings/import", { method: "POST", body: fd });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(j.error || "가져오지 못했습니다.");
      const msg = `「${file.name}」에서 가져올 내용\n${counts(j.summary)}\n\n현재 설정\n${counts(j.current)}\n\n` +
        `현재 설정을 가져온 내용으로 덮어씁니다 (현재 설정은 백업에 남습니다).` + (dirty() ? "\n저장하지 않은 변경도 사라집니다." : "") + " 계속할까요?";
      if (!confirm(msg)) return;
      const r2 = await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(j.settings) });
      const j2 = await r2.json().catch(() => ({}));
      if (!r2.ok) throw new Error(j2.error || "저장하지 못했습니다.");
      afterReplace(j2.settings, "대장에서 설정을 가져왔습니다");
    } catch (err) { toast(err.message); }
  }
  async function restoreBackup(name, when) {
    if (!confirm(`${when} 백업으로 되돌릴까요? 현재 설정은 백업에 남습니다.` + (dirty() ? "\n저장하지 않은 변경은 사라집니다." : ""))) return;
    try {
      const res = await fetch("/api/settings/restore", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(j.error || "되돌리지 못했습니다.");
      afterReplace(j.settings, `${when} 설정으로 되돌렸습니다`);
    } catch (err) { toast(err.message); }
  }
  function afterReplace(next, message) {
    saved = next; draft = clone(next); adding = null;
    $("#st-first").hidden = true;
    try { localStorage.setItem(SAVED_KEY, String(Date.now())); } catch (_) {}
    rerender(); loadBackups(); toast(message);
  }

  let tt;
  function toast(m) { const el = $("#st-toast"); el.textContent = m; el.classList.add("on"); clearTimeout(tt); tt = setTimeout(() => el.classList.remove("on"), 2800); }
  function setTab(name) {
    tab = name; adding = null;
    document.querySelectorAll(".tab").forEach((x) => { const on = x.dataset.tab === name; x.classList.toggle("on", on); x.setAttribute("aria-selected", on); });
    $("#st-q").placeholder = name === "rules" ? "키워드, 부서 검색" : "부서, 이름, 업무 검색";
    if (name === "io") loadBackups();
    render();
  }

  // 결과 화면에서 열었으면 돌아가는 버튼을 보인다 (결과 화면은 다른 탭에 그대로 열려 있다)
  const fromResult = new URLSearchParams(location.search).get("from") === "result";
  if (fromResult) {
    $("#st-back").hidden = false;
    $("#st-back").addEventListener("click", (e) => {
      if (dirty() && !confirm("저장하지 않은 변경이 있습니다. 그래도 돌아갈까요?")) { e.preventDefault(); return; }
      if (window.opener && !window.opener.closed) { e.preventDefault(); window.opener.focus(); window.close(); }
    });
  }

  document.querySelectorAll(".tab").forEach((x) => x.addEventListener("click", () => setTab(x.dataset.tab)));
  $("#st-body").addEventListener("input", onInput);
  $("#st-body").addEventListener("change", onInput);
  $("#st-body").addEventListener("click", onClick);
  $("#st-body").addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    if (e.target.dataset.new) { e.preventDefault(); document.querySelector('[data-act="do-add"]')?.click(); }
    if (e.target.id === "st-rule-kw") { e.preventDefault(); document.querySelector('[data-act="add-rule"]')?.click(); }
  });
  $("#st-q").addEventListener("input", filter);
  $("#st-first").addEventListener("click", onClick);
  $("#st-import").addEventListener("change", (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) importFile(f); });
  $("#st-save").addEventListener("click", saveAll);
  $("#st-revert").addEventListener("click", () => { draft = clone(saved); adding = null; rerender(); });
  window.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); if (dirty()) saveAll(); } });
  window.addEventListener("beforeunload", (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });

  (async () => {
    try {
      const res = await fetch("/api/settings");
      const j = await res.json();
      saved = j.settings; draft = clone(saved);
      $("#st-first").hidden = j.exists; // 처음 실행: 기존 대장에서 가져오기 안내
      rerender();
    } catch (_) { $("#st-body").innerHTML = '<p class="err">설정을 불러오지 못했습니다. 프로그램을 다시 실행해 주세요.</p>'; }
  })();
})();
