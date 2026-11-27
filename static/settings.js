// 설정 화면 — 부서원 · 분장표 · 부서 구성 · 배분 추가 규칙.
// 화면에서는 사본(draft)을 고치고 '저장'할 때만 data/settings.json에 쓴다. 저장하면 열려 있는 결과 화면도 명단을 다시 읽는다.
(() => {
  const META = window.SETTINGS_META;
  const SAVED_KEY = "yogu:settings-saved"; // 결과 화면에 저장을 알리는 신호 (storage 이벤트)
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const $ = (sel) => document.querySelector(sel);
  const clone = (v) => JSON.parse(JSON.stringify(v));
  const splitList = (v) => [...new Set(String(v).split(/[,，、]/).map((x) => x.trim()).filter(Boolean))];

  let saved = null, draft = null, tab = "people", adding = null, editing = null;

  // ---------- 부서 구성 (조직개편) ----------
  // draft.org가 없으면 기본 구성. draft.merged: 없앤 부서 → 업무를 넘겨받은 부서("" = 없음)
  const DEFAULT_NAMES = META.defaultOrg.map((g) => g.name), EXTRA_COLORS = [6, 7, 8];
  const NA = "해당없음";
  function orgList() {
    let extra = 0;
    return (draft.org || META.defaultOrg).map((g, i) => ({ name: g.name, depts: g.depts, i,
      c: DEFAULT_NAMES.includes(g.name) ? DEFAULT_NAMES.indexOf(g.name) : EXTRA_COLORS[extra++ % EXTRA_COLORS.length] }));
  }
  const allDepts = () => orgList().flatMap((g) => g.depts);
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  function resolve(d) {
    const seen = new Set();
    while (own(draft.merged, d) && !seen.has(d)) { seen.add(d); d = draft.merged[d]; }
    return seen.has(d) ? "" : d;
  }
  function depts() {
    const out = [];
    for (const o of orgList()) for (const d of o.depts) out.push({ org: o, dept: d });
    const other = { name: "구성에 없는 부서", i: 99, c: 5 };
    for (const d of [...META.tasks.map((t) => resolve(t.dept)), ...draft.custom.map((c) => c.dept)]) {
      if (d && !out.some((x) => x.dept === d)) out.push({ org: other, dept: d });
    }
    return out;
  }
  const baseTasks = (d) => [...new Set(META.tasks.filter((t) => resolve(t.dept) === d).map((t) => t.task))];
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
    `<section class="st-d" data-dept="${esc(dept)}" data-q="${esc(q)}" style="--c:var(--o${org.c})"><div class="st-dh"><h3><i></i>${esc(dept)}</h3>${head}</div>${inner}</section>`;
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

  function deptOptions(cur, skip = "") {
    const groups = orgList();
    return `<option value=""${cur ? "" : " selected"} disabled>부서 선택</option>` +
      groups.map((o) => `<optgroup label="${esc(o.name)}">` + o.depts.filter((d) => d !== skip).map((d) => `<option${d === cur ? " selected" : ""}>${esc(d)}</option>`).join("") + "</optgroup>").join("") +
      (cur && !groups.some((o) => o.depts.includes(cur)) ? `<option selected>${esc(cur)}</option>` : "");
  }

  // ③ 부서 구성: 본부별 부서 — 본부 옮기기 · 이름 바꾸기 · 없애기(업무 넘기기) · 새 부서
  function groupOptions(cur) {
    return orgList().map((g) => `<option${g.name === cur ? " selected" : ""}>${esc(g.name)}</option>`).join("") +
      '<option value="__new">+ 새 본부…</option>';
  }
  function orgHtml() {
    const groups = orgList();
    const rowHtml = (g, d) => {
      const n = baseTasks(d).length + customOf(d).length, ppl = people(d).length;
      const info = `<span class="t3">업무 ${n} · 부서원 ${ppl}</span>`;
      let body;
      if (editing?.dept === d && editing.type === "rename") {
        body = `<input class="in" id="st-ren" value="${esc(d)}" aria-label="${esc(d)} 새 이름">
<button type="button" class="btn sm primary" data-act="do-rename" data-d="${esc(d)}">이름 바꾸기</button><button type="button" class="linkbtn" data-act="cancel-edit">취소</button>`;
      } else if (editing?.dept === d && editing.type === "delete") {
        body = `<span class="t3">업무·담당자를 넘겨받을 부서</span>
<span class="selw"><select class="in" id="st-del-to" aria-label="${esc(d)} 업무를 넘겨받을 부서"><option value="">없음 — 이 부서 업무 질의는 '확인 필요'로</option>${deptOptions("", d).replace(/<option value="" selected disabled>부서 선택<\/option>/, "")}</select></span>
<button type="button" class="btn sm danger" data-act="do-delete" data-d="${esc(d)}">없애기</button><button type="button" class="linkbtn" data-act="cancel-edit">취소</button>`;
      } else {
        body = `${info}<span class="selw sm"><select class="in" data-k="mv|${esc(d)}" aria-label="${esc(d)} 본부">${groupOptions(g.name)}</select></span>
<button type="button" class="linkbtn" data-act="rename" data-d="${esc(d)}">이름 변경</button><button type="button" class="linkbtn danger" data-act="delete" data-d="${esc(d)}">없애기</button>`;
      }
      return `<li class="st-org-r${editing?.dept === d ? " editing" : ""}" data-q="${esc(`${g.name} ${d}`)}"><b>${esc(d)}</b><span class="ctl">${body}</span></li>`;
    };
    const html = groups.map((g) => `<section class="st-d st-org" data-dept="" data-q="${esc(`${g.name} ${g.depts.join(" ")}`)}" style="--c:var(--o${g.c})">
<div class="st-dh"><h3><i></i>${esc(g.name)}</h3><button type="button" class="linkbtn" data-act="rename-group" data-g="${esc(g.name)}">본부 이름 변경</button></div>
<ul class="st-org-l">${g.depts.map((d) => rowHtml(g, d)).join("")}</ul></section>`).join("");
    const gone = Object.entries(draft.merged);
    const goneHtml = gone.length ? `<section class="st-d st-gone" data-q="${esc(gone.flat().join(" "))}"><div class="st-dh"><h3>없앤 부서</h3><span class="t3">이 부서로 배분되던 질의가 가는 곳</span></div><ul class="st-org-l">` +
      gone.map(([from, to]) => `<li class="st-org-r"><b>${esc(from)}</b><span class="ctl"><span class="t3">→ ${to ? esc(to) : "넘겨받은 부서 없음 (확인 필요)"}</span>` +
        `<button type="button" class="linkbtn" data-act="undelete" data-d="${esc(from)}">되살리기</button></span></li>`).join("") + "</ul></section>" : "";
    return `<div class="st-rule-add st-dept-add">
<input class="in" id="st-new-dept" placeholder="새 부서 이름 (예: 전략기획실)" aria-label="새 부서 이름">
<span class="selw"><select class="in" id="st-new-group" aria-label="새 부서 본부">${groupOptions(groups[0]?.name)}</select></span>
<button type="button" class="btn primary sm" data-act="add-dept">부서 추가</button></div>${html}${goneHtml}`;
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
    org: "조직개편 시 부서를 추가·이름 변경·통폐합합니다. 없앤 부서의 업무와 담당자 설정은 넘겨받은 부서로 옮겨집니다.",
  };
  function render() {
    $("#st-tab-help").textContent = HELP[tab];
    $("#st-n-rules").textContent = draft.rules.length || "";
    if (tab === "rules") { $("#st-body").innerHTML = rulesHtml(); filter(); return; }
    if (tab === "org") { $("#st-body").innerHTML = orgHtml(); filter(); return; }
    let html = "", last = null;
    for (const { org, dept } of depts()) {
      if (org.name !== last) { html += `<p class="st-o" style="--c:var(--o${org.c})">${esc(org.name)}</p>`; last = org.name; }
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
    document.querySelectorAll(".st-org").forEach((s) => {
      let any = false;
      s.querySelectorAll(".st-org-r").forEach((r) => { const ok = !t || r.dataset.q.includes(t); r.classList.toggle("hide", !ok); any ||= ok; });
      s.classList.toggle("hide", !any);
    });
  }

  // ---------- 부서 구성 고치기 ----------
  function ensureOrg() { if (!draft.org) draft.org = clone(META.defaultOrg); }
  function checkName(name, label = "부서") {
    if (!name) return `${label} 이름을 입력해 주세요`;
    if (name.includes("|")) return "이름에 | 기호는 쓸 수 없습니다";
    if (name === NA) return `'${NA}'는 쓸 수 없는 이름입니다`;
    if (label === "부서" && allDepts().includes(name)) return `'${name}'은(는) 이미 있는 부서입니다`;
    return "";
  }
  function groupFor(name) {
    ensureOrg();
    let g = draft.org.find((x) => x.name === name);
    if (!g) { g = { name, depts: [] }; draft.org.push(g); }
    return g;
  }
  function askGroup() {
    const name = (prompt("새 본부 이름을 입력하세요") || "").trim();
    if (!name) return "";
    if (orgList().some((g) => g.name === name)) return name;
    const err = checkName(name, "본부"); if (err) { toast(err); return ""; }
    return name;
  }
  function placeDept(dept, groupName) {
    ensureOrg();
    for (const g of draft.org) g.depts = g.depts.filter((x) => x !== dept);
    groupFor(groupName).depts.push(dept);
    draft.org = draft.org.filter((g) => g.depts.length);
  }
  // 없애거나 이름을 바꾼 부서의 설정(총괄·부서원·업무 담당자·제외·추가 업무·규칙)을 넘겨받는 부서로 옮긴다
  function moveSettings(from, to) {
    const pre = `${from}|`;
    if (to && draft.channel[from] && !draft.channel[to]) draft.channel[to] = draft.channel[from];
    delete draft.channel[from];
    if (to && people(from).length) draft.members[to] = [...new Set([...people(to), ...people(from)])];
    delete draft.members[from];
    for (const [k, v] of Object.entries(draft.tasks)) {
      if (!k.startsWith(pre)) continue;
      const nk = `${to}|${k.slice(pre.length)}`;
      if (to && !draft.tasks[nk]) draft.tasks[nk] = v;
      delete draft.tasks[k];
    }
    draft.excluded = [...new Set(draft.excluded.flatMap((k) => (k.startsWith(pre) ? (to ? [`${to}|${k.slice(pre.length)}`] : []) : [k])))];
    const custom = [];
    for (const c of draft.custom) {
      const x = c.dept === from ? (to ? { ...c, dept: to } : null) : c;
      if (x && !custom.some((y) => y.dept === x.dept && y.task === x.task)) custom.push(x);
    }
    draft.custom = custom;
    const before = draft.rules.length;
    draft.rules = draft.rules.flatMap((r) => (r.dept === from ? (to ? [{ ...r, dept: to }] : []) : [r]));
    for (const [k, v] of Object.entries(draft.merged)) if (v === from) draft.merged[k] = to;
    return before - draft.rules.length;
  }
  function renameDept(from) {
    const to = ($("#st-ren")?.value || "").trim();
    if (to === from) { editing = null; rerender(); return; }
    const err = checkName(to); if (err) { toast(err); $("#st-ren")?.focus(); return; }
    ensureOrg();
    for (const g of draft.org) g.depts = g.depts.map((x) => (x === from ? to : x));
    moveSettings(from, to);
    delete draft.merged[to];
    draft.merged[from] = to;
    editing = null; rerender();
    toast(`${from} → ${to}: 업무·담당자 설정을 옮겼습니다. 저장하면 다음 처리부터 반영됩니다`);
  }
  function deleteDept(from) {
    const to = $("#st-del-to")?.value || "";
    ensureOrg();
    for (const g of draft.org) g.depts = g.depts.filter((x) => x !== from);
    draft.org = draft.org.filter((g) => g.depts.length);
    const dropped = moveSettings(from, to);
    draft.merged[from] = to;
    editing = null; rerender();
    toast(to ? `${from}을(를) 없애고 업무·담당자를 ${to}(으)로 넘겼습니다` :
      `${from}을(를) 없앴습니다 — 이 부서 업무 질의는 '확인 필요'로 표시됩니다` + (dropped ? ` (규칙 ${dropped}개 삭제)` : ""));
  }
  function undelete(name) {
    if (allDepts().includes(name)) { delete draft.merged[name]; rerender(); return; }
    const home = META.defaultOrg.find((g) => g.depts.includes(name))?.name;
    const groups = orgList().map((g) => g.name);
    delete draft.merged[name];
    placeDept(name, groups.includes(home) ? home : groups[groups.length - 1]);
    rerender();
    toast(`${name}을(를) 되살렸습니다 — 넘겨준 담당자 설정은 넘겨받은 부서에 그대로 남아 있습니다`);
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
    else if (kind === "mv") {
      if (e.type !== "change") return;
      const g = v === "__new" ? askGroup() : v;
      if (g) placeDept(a, g);
      rerender(); return;
    }
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
      case "add-dept": {
        const name = $("#st-new-dept").value.trim();
        const err = checkName(name); if (err) { toast(err); $("#st-new-dept").focus(); return; }
        let g = $("#st-new-group").value;
        if (g === "__new") { g = askGroup(); if (!g) return; }
        delete draft.merged[name];
        placeDept(name, g);
        rerender("#st-new-dept");
        toast(`${g}에 ${name}을(를) 추가했습니다 — 분장표에서 업무를 추가하고 부서원 탭에서 사람을 넣으세요`); break;
      }
      case "rename": editing = { type: "rename", dept: d }; rerender("#st-ren"); break;
      case "delete": editing = { type: "delete", dept: d }; rerender("#st-del-to"); break;
      case "cancel-edit": editing = null; rerender(); break;
      case "do-rename": renameDept(d); break;
      case "do-delete": deleteDept(d); break;
      case "undelete": undelete(d); break;
      case "rename-group": {
        const from = b.dataset.g, to = (prompt(`'${from}'의 새 이름`, from) || "").trim();
        if (!to || to === from) return;
        if (orgList().some((g) => g.name === to)) { toast(`'${to}' 본부가 이미 있습니다`); return; }
        const err = checkName(to, "본부"); if (err) { toast(err); return; }
        ensureOrg(); draft.org.find((g) => g.name === from).name = to; rerender(); break;
      }
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
      saved = normalize(j.settings); draft = clone(saved); adding = null; editing = null;
      try { localStorage.setItem(SAVED_KEY, String(Date.now())); } catch (_) {}
      rerender();
      toast(fromResult ? "저장했습니다 — 결과 화면의 담당자 목록에도 반영됩니다" : "저장했습니다 — 다음 파일 처리부터 반영됩니다");
    } catch (err) { toast(err.message); updateBar(); }
  }

  let tt;
  function toast(m) { const el = $("#st-toast"); el.textContent = m; el.classList.add("on"); clearTimeout(tt); tt = setTimeout(() => el.classList.remove("on"), 2800); }
  function setTab(name) {
    tab = name; adding = null; editing = null;
    document.querySelectorAll(".tab").forEach((x) => { const on = x.dataset.tab === name; x.classList.toggle("on", on); x.setAttribute("aria-selected", on); });
    $("#st-q").placeholder = name === "rules" ? "키워드, 부서 검색" : name === "org" ? "본부, 부서 검색" : "부서, 이름, 업무 검색";
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
    if (e.target.id === "st-new-dept") { e.preventDefault(); document.querySelector('[data-act="add-dept"]')?.click(); }
    if (e.target.id === "st-ren") { e.preventDefault(); document.querySelector('[data-act="do-rename"]')?.click(); }
  });
  $("#st-q").addEventListener("input", filter);
  $("#st-save").addEventListener("click", saveAll);
  $("#st-revert").addEventListener("click", () => { draft = clone(saved); adding = null; editing = null; rerender(); });
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
