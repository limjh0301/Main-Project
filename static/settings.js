// 설정 화면 — 부서원 · 분장표 · 배분 추가 규칙.
// 화면에서는 사본(draft)을 고치고 '저장'할 때만 data/settings.json에 쓴다. 저장하면 열려 있는 결과 화면도 명단을 다시 읽는다.
(() => {
  const META = window.SETTINGS_META;
  const SAVED_KEY = "yogu:settings-saved"; // 결과 화면에 저장을 알리는 신호 (storage 이벤트)
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const $ = (sel) => document.querySelector(sel);
  const clone = (v) => JSON.parse(JSON.stringify(v));
  const splitList = (v) => [...new Set(String(v).split(/[,，、]/).map((x) => x.trim()).filter(Boolean))];

  let saved = null, draft = null, tab = "people", adding = null;

  // ---------- 부서·업무·사람 ----------
  function depts() {
    const out = [];
    for (const o of META.org) for (const d of o.depts) out.push({ org: o, dept: d });
    const other = META.org[META.org.length - 1];
    for (const t of [...META.tasks, ...draft.custom]) if (!out.some((x) => x.dept === t.dept)) out.push({ org: other, dept: t.dept });
    return out;
  }
  const baseTasks = (d) => META.tasks.filter((t) => t.dept === d).map((t) => t.task);
  const isExcluded = (d, t) => draft.excluded.includes(`${d}|${t}`);
  const customOf = (d) => draft.custom.filter((c) => c.dept === d);
  const activeTasks = (d) => [...baseTasks(d).filter((t) => !isExcluded(d, t)), ...customOf(d).map((c) => c.task)];
  const worker = (d, t) => draft.tasks[`${d}|${t}`] || "";
  const people = (d) => draft.members[d] || [];

  // 부서원 목록 하나로 관리한다: 예전 설정의 총괄담당자·업무 담당자도 부서원 목록에 넣어 둔다
  function normalize(cfg) {
    const all = new Set([...Object.keys(cfg.channel), ...Object.keys(cfg.members), ...Object.keys(cfg.tasks).map((k) => k.split("|")[0])]);
    for (const d of all) {
      const names = [cfg.channel[d], ...(cfg.members[d] || []),
        ...Object.entries(cfg.tasks).filter(([k]) => k.split("|")[0] === d).map(([, v]) => v)];
      const list = [...new Set(names.filter(Boolean))];
      if (list.length) cfg.members[d] = list;
    }
    return cfg;
  }

  // ---------- 그리기 ----------
  const card = (org, dept, q, head, inner) =>
    `<section class="st-d" data-dept="${esc(dept)}" data-q="${esc(q)}" style="--c:var(--o${org.i})"><div class="st-dh"><h3><i></i>${esc(dept)}</h3>${head}</div>${inner}</section>`;
  const sel = (k, cur, label, options, cls = "") =>
    `<span class="selw"><select class="in${cls}" data-k="${esc(k)}" aria-label="${esc(label)}">${options}</select></span>`;

  // ① 부서원: 총괄담당자 + 부서원 목록
  function peopleHtml(org, dept) {
    const ms = people(dept), ch = draft.channel[dept] || "";
    const chOpts = `<option value=""${ch ? "" : " selected"}>없음</option>` + ms.map((n) => `<option${n === ch ? " selected" : ""}>${esc(n)}</option>`).join("");
    const chips = ms.map((n) => `<span class="chip${n === ch ? " lead" : ""}">${esc(n)}${n === ch ? '<b class="t3">총괄</b>' : ""}` +
      `<button type="button" class="x" data-act="del-member" data-d="${esc(dept)}" data-n="${esc(n)}" aria-label="${esc(n)} 빼기" title="부서원에서 빼기">×</button></span>`).join("");
    const inner = `<div class="st-r"><span class="lab strong">총괄담당자 <span class="t3">요청 취합·안내</span></span>${sel(`ch|${dept}`, ch, `${dept} 총괄담당자`, chOpts)}</div>
<div class="st-line"><span class="lab">부서원</span><span class="chips">${chips || '<span class="t3">없음</span>'}</span></div>
<div class="st-addm"><input class="in" data-addm="${esc(dept)}" placeholder="이름 입력 후 Enter (쉼표로 여러 명)" aria-label="${esc(dept)} 부서원 추가">
<button type="button" class="btn sm" data-act="add-member" data-d="${esc(dept)}">추가</button></div>`;
    return card(org, dept, `${org.name} ${dept} ${ms.join(" ")}`, `<span class="t3">${ms.length}명</span>`, inner);
  }

  // ② 분장표: 업무마다 담당자 (항상 부서원 전체 목록) · 업무 제외/추가
  function workerOptions(dept, cur) {
    const ch = draft.channel[dept], ms = people(dept);
    const list = cur && !ms.includes(cur) ? [cur, ...ms] : ms;
    return `<option value=""${cur ? "" : " selected"}>${ch ? `총괄담당자 (${esc(ch)})` : "미정 (총괄담당자)"}</option>` +
      list.map((n) => `<option${n === cur ? " selected" : ""}>${esc(n)}</option>`).join("");
  }
  function tasksHtml(org, dept) {
    const base = baseTasks(dept), off = base.filter((t) => isExcluded(dept, t)), custom = customOf(dept);
    const row = (t, extra = "", action = "") => `<tr><td class="tn">${extra || esc(t)}</td>` +
      `<td>${sel(`w|${dept}|${t}`, worker(dept, t), `${dept} ${t} 담당자`, workerOptions(dept, worker(dept, t)), worker(dept, t) ? " set" : "")}</td><td class="act">${action}</td></tr>`;
    const rows = base.filter((t) => !isExcluded(dept, t)).map((t) => row(t, "",
      `<button type="button" class="linkbtn" data-act="exclude" data-d="${esc(dept)}" data-t="${esc(t)}" title="이 업무로는 배분하지 않음">제외</button>`));
    for (const c of custom) {
      rows.push(row(c.task, `<span class="chip added">${esc(c.task)}</span><input class="in kw" data-k="${esc(`ck|${dept}|${c.task}`)}" value="${esc(c.keywords.join(", "))}" placeholder="키워드 (쉼표로 구분)" aria-label="${esc(c.task)} 키워드">`,
        `<button type="button" class="linkbtn danger" data-act="del-custom" data-d="${esc(dept)}" data-t="${esc(c.task)}">삭제</button>`));
    }
    const parts = [];
    if (rows.length) parts.push(`<table class="st-map"><thead><tr><th>업무</th><th>담당자</th><th></th></tr></thead><tbody>${rows.join("")}</tbody></table>`);
    if (off.length) {
      parts.push(`<div class="st-line"><span class="lab">제외한 업무</span><span class="chips">${off.map((t) =>
        `<span class="chip off">${esc(t)}<button type="button" class="restore" data-act="restore" data-d="${esc(dept)}" data-t="${esc(t)}">되살리기</button></span>`).join("")}</span></div>`);
    }
    if (adding && adding.dept === dept) {
      parts.push(`<div class="st-add"><input class="in" data-new="task" value="${esc(adding.task || "")}" placeholder="업무 이름 (예: 청탁금지)" aria-label="추가할 업무 이름">` +
        `<input class="in" data-new="keywords" value="${esc(adding.keywords || "")}" placeholder="키워드, 쉼표로 구분 (예: 청탁금지, 김영란법)" aria-label="추가할 업무 키워드">` +
        `<button type="button" class="btn sm primary" data-act="do-add">추가</button><button type="button" class="linkbtn" data-act="cancel-add">취소</button></div>`);
    } else {
      parts.push(`<div class="st-line"><button type="button" class="linkbtn" data-act="open-add" data-d="${esc(dept)}">+ 업무 추가</button></div>`);
    }
    const n = activeTasks(dept).length, done = activeTasks(dept).filter((t) => worker(dept, t)).length;
    const head = people(dept).length ? `<span class="t3">담당자 지정 ${done}/${n}</span>`
      : `<span class="t3">부서원이 없습니다 — <button type="button" class="linkbtn" data-act="go-people">부서원 탭</button>에서 먼저 입력하세요</span>`;
    const q = `${org.name} ${dept} ${base.join(" ")} ${custom.map((c) => `${c.task} ${c.keywords.join(" ")}`).join(" ")} ${people(dept).join(" ")}`;
    return card(org, dept, q, head, parts.join(""));
  }

  function deptOptions(cur) {
    return `<option value=""${cur ? "" : " selected"} disabled>부서 선택</option>` +
      META.org.map((o) => `<optgroup label="${esc(o.name)}">` + o.depts.map((d) => `<option${d === cur ? " selected" : ""}>${esc(d)}</option>`).join("") + "</optgroup>").join("") +
      (cur && !META.org.some((o) => o.depts.includes(cur)) ? `<option selected>${esc(cur)}</option>` : "");
  }
  function rulesHtml() {
    const rows = draft.rules.map((r, i) => `<tr data-q="${esc(`${r.keyword} ${r.dept} ${r.basis}`)}">
<td><input class="in" data-k="rk|${i}" value="${esc(r.keyword)}" placeholder="키워드" aria-label="${i + 1}번 규칙 키워드"></td>
<td>${sel(`rd|${i}`, r.dept, `${i + 1}번 규칙 부서`, deptOptions(r.dept))}</td>
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
    people: "부서마다 부서원과 총괄담당자를 입력합니다. 분장표와 결과 화면의 담당자 목록이 이 명단으로 채워집니다.",
    tasks: "업무마다 담당자를 고르면 그 업무로 배분된 질의에 자동으로 채워집니다. 고르지 않으면 총괄담당자가 들어갑니다.",
    rules: "질의에 키워드가 들어 있으면 기본 규칙보다 먼저 지정한 부서로 배분합니다.",
  };
  function render() {
    $("#st-tab-help").textContent = HELP[tab];
    $("#st-n-rules").textContent = draft.rules.length || "";
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
  function rerender(focusSel) {
    const y = window.scrollY;
    render(); updateBar(); window.scrollTo(0, y);
    if (focusSel) document.querySelector(focusSel)?.focus({ preventScroll: true });
  }
  // 입력하는 즉시 draft에 반영 (다시 그려도 입력이 지워지지 않는다)
  function onInput(e) {
    const el = e.target;
    if (el.dataset.new && adding) { adding[el.dataset.new] = el.value; return; }
    if (!el.dataset.k) return;
    const [kind, a, b] = el.dataset.k.split("|"), v = el.value.trim();
    if (kind === "ch") { if (v) draft.channel[a] = v; else delete draft.channel[a]; }
    else if (kind === "w") { if (v) draft.tasks[`${a}|${b}`] = v; else delete draft.tasks[`${a}|${b}`]; }
    else if (kind === "ck") { const c = draft.custom.find((x) => x.dept === a && x.task === b); if (c) c.keywords = splitList(v); }
    else if (kind === "rk") draft.rules[+a].keyword = v;
    else if (kind === "rd") draft.rules[+a].dept = v;
    // 총괄담당자를 바꾸면 '총괄' 표시를 새로 그리고, 업무 담당자를 바꾸면 지정 수만 고친다 (포커스 유지)
    if (e.type === "change" && kind === "ch") { rerender(); return; }
    if (e.type === "change" && kind === "w") {
      el.classList.toggle("set", !!v);
      const head = el.closest(".st-d")?.querySelector(".st-dh > .t3"), ts = activeTasks(a);
      if (head && people(a).length) head.textContent = `담당자 지정 ${ts.filter((t) => worker(a, t)).length}/${ts.length}`;
    }
    updateBar();
  }
  function addMembers(dept) {
    const box = document.querySelector(`[data-addm="${CSS.escape(dept)}"]`), names = splitList(box?.value || "");
    if (!names.length) { box?.focus(); return; }
    const before = people(dept);
    draft.members[dept] = [...new Set([...before, ...names])];
    const dup = names.filter((n) => before.includes(n));
    rerender(`[data-addm="${CSS.escape(dept)}"]`);
    if (dup.length) toast(`${dup.join(", ")}: 이미 있는 부서원입니다`);
  }
  function removeMember(dept, name) {
    const owned = Object.entries(draft.tasks).filter(([k, v]) => k.split("|")[0] === dept && v === name).map(([k]) => k);
    if (owned.length && !confirm(`${name}님이 맡은 업무 ${owned.length}개가 미지정(총괄담당자)으로 바뀝니다. 빼시겠습니까?`)) return;
    for (const k of owned) delete draft.tasks[k];
    draft.members[dept] = people(dept).filter((n) => n !== name);
    if (!draft.members[dept].length) delete draft.members[dept];
    if (draft.channel[dept] === name) delete draft.channel[dept];
    rerender();
  }
  function onClick(e) {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    const d = b.dataset.d, t = b.dataset.t;
    switch (b.dataset.act) {
      case "add-member": addMembers(d); break;
      case "del-member": removeMember(d, b.dataset.n); break;
      case "go-people": setTab("people"); $("#st-q").value = b.closest(".st-d").dataset.dept; filter(); break;
      case "exclude": draft.excluded.push(`${d}|${t}`); delete draft.tasks[`${d}|${t}`]; rerender(); break;
      case "restore": draft.excluded = draft.excluded.filter((k) => k !== `${d}|${t}`); rerender(); break;
      case "del-custom":
        draft.custom = draft.custom.filter((c) => !(c.dept === d && c.task === t)); delete draft.tasks[`${d}|${t}`]; rerender(); break;
      case "open-add": adding = { dept: d }; rerender(`.st-d[data-dept="${CSS.escape(d)}"] [data-new="task"]`); break;
      case "cancel-add": adding = null; rerender(); break;
      case "do-add": {
        const task = (adding.task || "").trim(), dept = adding.dept;
        if (!task) { toast("업무 이름을 입력해 주세요"); document.querySelector('[data-new="task"]')?.focus(); return; }
        if (task.includes("|")) { toast("업무 이름에 | 기호는 쓸 수 없습니다"); return; }
        if (baseTasks(dept).includes(task) || customOf(dept).some((c) => c.task === task)) { toast(`${dept}에 이미 있는 업무입니다`); return; }
        draft.custom.push({ dept, task, keywords: splitList(adding.keywords || "") });
        adding = null; rerender(); toast(`${dept}에 '${task}' 업무를 추가했습니다 — 담당자를 고르고 저장하세요`); break;
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
      saved = normalize(j.settings); draft = clone(saved); adding = null;
      try { localStorage.setItem(SAVED_KEY, String(Date.now())); } catch (_) {}
      rerender();
      toast(fromResult ? "저장했습니다 — 결과 화면의 담당자 목록에도 반영됩니다" : "저장했습니다 — 다음 파일 처리부터 반영됩니다");
    } catch (err) { toast(err.message); updateBar(); }
  }

  let tt;
  function toast(m) { const el = $("#st-toast"); el.textContent = m; el.classList.add("on"); clearTimeout(tt); tt = setTimeout(() => el.classList.remove("on"), 2800); }
  function setTab(name) {
    tab = name; adding = null;
    document.querySelectorAll(".tab").forEach((x) => { const on = x.dataset.tab === name; x.classList.toggle("on", on); x.setAttribute("aria-selected", on); });
    $("#st-q").placeholder = name === "rules" ? "키워드, 부서 검색" : "부서, 이름, 업무 검색";
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
    if (e.key !== "Enter" || e.isComposing) return;
    if (e.target.dataset.addm) { e.preventDefault(); addMembers(e.target.dataset.addm); }
    if (e.target.dataset.new) { e.preventDefault(); document.querySelector('[data-act="do-add"]')?.click(); }
    if (e.target.id === "st-rule-kw") { e.preventDefault(); document.querySelector('[data-act="add-rule"]')?.click(); }
  });
  $("#st-q").addEventListener("input", filter);
  $("#st-save").addEventListener("click", saveAll);
  $("#st-revert").addEventListener("click", () => { draft = clone(saved); adding = null; rerender(); });
  window.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); if (dirty()) saveAll(); } });
  window.addEventListener("beforeunload", (e) => { if (dirty()) { e.preventDefault(); e.returnValue = ""; } });

  (async () => {
    try {
      const res = await fetch("/api/settings");
      saved = normalize((await res.json()).settings); draft = clone(saved);
      rerender();
    } catch (_) { $("#st-body").innerHTML = '<p class="err">설정을 불러오지 못했습니다. 프로그램을 다시 실행해 주세요.</p>'; }
  })();
})();
