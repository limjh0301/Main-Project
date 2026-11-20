// 분배안 보드 — 처리 결과를 부서별로 묶어 보여 주고, 부서·담당자·기제출·날짜를 고치게 한다.
// 질의별 수정(부서·담당자·기제출)은 이 브라우저에만, 날짜는 대장에 저장된다. 담당자 명단은 설정 화면(/settings)에서 고친다.
(() => {
  const NA = "해당없음";
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (d) => (d ? d.replaceAll("-", ".") : "미정");
  const keyText = (k) => { const m = String(k).match(/^\[(.+?)\]\s*(.*)$/); return m ? `${m[1]} ${m[2]}` : `${k}번`; };
  const $ = (sel) => root.querySelector(sel);
  // 받침에 맞는 조사: josa("병가", "이", "가") → "병가가", josa("감사부", "으로", "로") → "감사부로"
  function josa(word, withFinal, withoutFinal) {
    const c = word.charCodeAt(word.length - 1) - 0xac00;
    if (c < 0 || c > 11171) return `${word}${withFinal}(${withoutFinal})`;
    const fin = c % 28;
    const useFinal = withFinal === "으로" ? fin !== 0 && fin !== 8 : fin !== 0; // ㄹ받침(8)은 '로'
    return word + (useFinal ? withFinal : withoutFinal);
  }

  let root, D, R, S, KEY, resultId, downloadHref, local, filter = "all";

  // ---------- 상태 ----------
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (_) {} };
  // 본부: 부서를 본부별로 묶고 본부 색(--o{i})으로 구분한다. 목록에 없는 부서는 마지막 묶음(그 밖의 부서)
  const orgOf = (d) => D.org.find((o) => o.depts.includes(d)) || D.org[D.org.length - 1];
  const rank = (d) => { const o = orgOf(d), i = o.depts.indexOf(d); return o.i * 1000 + (i < 0 ? 500 : i); };
  const deptOf = (it) => S.dept[it.id] || it.dept;
  const moved = (it) => deptOf(it) !== it.dept;
  const chan = (d) => R.channel[d] || "";
  const taskWorker = (d, task) => R.tasks[`${d}|${task}`] || "";
  // 부서의 업무 = 배분표 업무(제외한 것 빼고) + 담당자 설정에서 추가한 업무
  const deptTasks = (d, src = R) => [
    ...D.tasks.filter((t) => t.dept === d && !(src.excluded || []).includes(`${d}|${t.task}`)).map((t) => t.task),
    ...(src.custom || []).filter((c) => c.dept === d).map((c) => c.task),
  ];
  // 부서원 = 총괄담당자 + 그 부서 업무 담당자 + 명단에 추가한 부서원
  function members(d) {
    const ppl = deptTasks(d).map((t) => taskWorker(d, t));
    return [...new Set([chan(d), ...ppl, ...(R.members[d] || [])].filter(Boolean))];
  }
  // 담당자: 질의별로 고른 사람 > (부서를 옮겼으면) 새 부서 총괄담당자·유일한 부서원 > 업무 담당자 > 총괄담당자
  function baseWorker(it) {
    if (moved(it)) { const d = deptOf(it), ms = members(d); return chan(d) || (ms.length === 1 ? ms[0] : ""); }
    return taskWorker(it.dept, it.task) || chan(it.dept);
  }
  const workerOf = (it) => S.wk[it.id] ?? baseWorker(it);
  const changed = (it) => moved(it) || S.wk[it.id] !== undefined;
  const reqOf = (tag) => D.reqs.find((r) => r.tag === tag);
  const dateOf = (r, f) => (S.dates[r.tag] || {})[f] ?? r[f];
  const live = () => D.reqs.filter((r) => !r.duplicate);
  // 이전 질의 표시: "2026.07.13 송기헌 의원 「제목」"
  const prevLabel = (h) => `${fmt(h.date)} ${h.member ? `${h.member} 의원 ` : ""}「${h.title || h.doc}」`;

  // ---------- 그리기 ----------
  function deptOptions(cur) {
    return D.org.map((o) => `<optgroup label="${esc(o.name)}">` +
      o.depts.map((d) => `<option${d === cur ? " selected" : ""}>${esc(d)}</option>`).join("") + "</optgroup>").join("") +
      (D.org.some((o) => o.depts.includes(cur)) || cur === NA ? "" : `<option selected>${esc(cur)}</option>`) +
      `<optgroup label="기타"><option value="${NA}"${cur === NA ? " selected" : ""}>해당없음</option></optgroup>`;
  }
  function workerOptions(d, w) {
    const ms = members(d); if (w && !ms.includes(w)) ms.unshift(w);
    return ms.map((m) => `<option${m === w ? " selected" : ""}>${esc(m)}</option>`).join("") +
      `<option value=""${w ? "" : " selected"}>미정</option><option value="__new">직접 입력…</option>`;
  }
  function rowHtml(it) {
    const d = deptOf(it), isNA = d === NA, done = !!S.done[it.id] && !isNA, w = workerOf(it), k = esc(keyText(it.key));
    const notes = [];
    if (done) notes.push('<span class="tag">기제출 자료로 갈음</span>' + (S.src[it.id] ? ` <span class="t3">출처 ${esc(S.src[it.id])}</span>` : ""));
    if (moved(it)) notes.push(`<span class="moved">부서 변경 · 원래 ${esc(it.dept)}</span>`);
    else if (S.wk[it.id] !== undefined) notes.push(`<span class="moved">담당자 변경 · 원래 ${esc(baseWorker(it) || "미정")}</span>`);
    if (it.amb) notes.push('<span class="amb">확인 필요</span>' + (it.why ? ` ${esc(it.why)}` : ""));
    else if (it.why && !moved(it)) notes.push(esc(it.why));
    if (it.same) notes.push("같은 질의 " + it.same.map((x) => esc(keyText(x))).join(", "));
    const prev = it.prev && !done ? `<p class="prev">` + it.prev.map((h, i) =>
      `<span title="${esc(`${h.doc} · ${h.text}`)}"><b>이전 질의</b> ${esc(h.kind)} · ${esc(prevLabel(h))}` +
      (h.submitted ? ` · 제출 ${esc(fmt(h.submitted))}` : "") +
      ` <button type="button" class="use-prev" data-i="${i}">기제출로 표시</button></span>`).join("<br>") + "</p>" : "";
    const det = it.rest.length
      ? `<details><summary>세부 ${it.rest.length}</summary><ul>${it.rest.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details>` : "";
    const asg = `<div class="asg"><span class="sel dsel" title="${esc(d)}"><select class="mv" aria-label="${k} 담당 부서">${deptOptions(d)}</select></span>` +
      (isNA ? "" : `<span class="sel wsel${w ? "" : " none"}" title="${esc(w || "미정")}"><select class="wk" aria-label="${k} 담당자">${workerOptions(d, w)}</select></span>`) + "</div>";
    const chk = isNA ? '<span class="donec"></span>'
      : `<label class="donec"><input type="checkbox" class="chk" aria-label="${k} 기제출 자료로 갈음"${done ? " checked" : ""}><span class="lbl">기제출</span></label>`;
    return `<li class="row${done ? " is-done" : ""}${it.amb ? " is-amb" : ""}" data-id="${esc(it.id)}" data-s="${esc(d + " " + w)}" data-amb="${+it.amb}" data-dup="${+!!it.same}" data-done="${+done}" data-moved="${+changed(it)}" data-prev="${+!!it.prev}">
<span class="k">${it.sec ? `<span class="sec">${esc(it.sec)}</span>` : ""}${esc(it.no)}</span><span class="per">${esc(it.period)}</span>
<div class="body"><p class="q">${esc(it.main)}</p>${notes.length ? `<p class="note">${notes.join(" · ")}</p>` : ""}${prev}${det}</div>
<div class="ctl">${asg}${chk}</div></li>`;
  }
  function contact(d, grp) {
    const ch = chan(d), ws = [...new Set(grp.map(workerOf).filter(Boolean))];
    return esc(ch ? `총괄담당자 ${ch}` : ws.length ? `담당 ${ws.join(" · ")}` : "담당 미정");
  }
  function renderReqs() {
    $("#b-reqs").innerHTML = D.reqs.map((r) => {
      const nm = (v, from) => esc(v || "—") + (from ? '<span class="from-name" title="질의서 본문에 없어 파일명에서 가져온 값">파일명</span>' : "");
      if (r.duplicate) {
        return `<tr class="dup"><td class="mono">${esc(r.doc)}</td><td>${esc(r.title)}</td><td>${esc(r.member || "—")}</td>` +
          `<td colspan="3" class="t3">이미 대장에 있는 요구서 — 다시 기록하지 않음</td></tr>`;
      }
      const cell = (f) => {
        const v = dateOf(r, f), ed = (S.dates[r.tag] || {})[f] !== undefined && v !== r[f], need = f === "due" && !v;
        return `<td${need ? ' class="need"' : ""}><input type="date" class="dt${v ? "" : " empty"}${ed ? " edited" : ""}" data-tag="${esc(r.tag)}" data-f="${f}" value="${esc(v)}" aria-label="${esc(r.label)} ${f === "date" ? "접수일자" : "제출기한"}"${need ? ' aria-invalid="true"' : ""}>${need ? '<span class="need-tag">필수</span>' : ""}</td>`;
      };
      return `<tr><td class="mono">${nm(r.doc, r.from.includes("doc_no"))}</td><td>${esc(r.title)}</td><td>${nm(r.member, r.from.includes("member"))}</td>${cell("date")}${cell("due")}<td class="num">${r.n}</td></tr>`;
    }).join("");
  }
  function render() {
    const act = D.items.filter((it) => deptOf(it) !== NA), na = D.items.filter((it) => deptOf(it) === NA);
    const depts = [...new Set(act.map(deptOf))].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b, "ko"));
    const by = (d) => act.filter((it) => deptOf(it) === d);
    $("#b-sections").innerHTML = depts.map((d, i) => {
      const grp = by(d), reqs = D.reqs.filter((r) => grp.some((x) => x.req === r.tag));
      const nd = grp.filter((x) => S.done[x.id]).length, amb = grp.filter((x) => x.amb).length;
      const blocks = reqs.map((r) => `<div class="rq">${reqs.length > 1 ? `<h3>${esc(r.label)}</h3>` : ""}<ul class="rows">${grp.filter((x) => x.req === r.tag).map(rowHtml).join("")}</ul></div>`).join("");
      return `<section id="b-d${i}" class="dept" data-dept="${esc(d)}" style="--c:var(--o${orgOf(d).c})">
<div class="dh"><div><h2>${esc(d)}<span class="count">${grp.length}${nd ? ` · 기제출 ${nd}` : ""}</span>${amb ? `<span class="amb">확인 ${amb}</span>` : ""}</h2>
<p class="meta"><span class="contacts">${contact(d, grp)}</span>${reqs.length === 1 ? ` <span class="t3">· ${esc(reqs[0].label)}</span>` : ""}</p></div>
<span class="org-tag">${esc(orgOf(d).name)}</span></div>${blocks}</section>`;
    }).join("");
    $("#b-nav").innerHTML = D.org.filter((o) => depts.some((d) => orgOf(d) === o)).map((o) => `<div class="fam" style="--c:var(--o${o.c})"><p class="label">${esc(o.name)}</p>` +
      depts.filter((d) => orgOf(d) === o).map((d) => `<a href="#b-d${depts.indexOf(d)}"><i></i><span>${esc(d)}</span><span class="t3">${by(d).length}</span></a>`).join("") + "</div>").join("");
    $("#b-na").innerHTML = `<summary>해당없음 ${na.length}건 · 기관 유형 비해당 섹션 등</summary><ul class="rows">${na.map(rowHtml).join("")}</ul>`;
    $("#b-na").hidden = !na.length;
    const n = { amb: act.filter((x) => x.amb).length, dup: act.filter((x) => x.same).length, prev: act.filter((x) => x.prev).length, done: act.filter((x) => S.done[x.id]).length, moved: D.items.filter(changed).length };
    for (const k in n) { const b = root.querySelector(`.seg [data-f="${k}"] b`); if (b) b.textContent = n[k]; }
    const noDue = live().filter((r) => r.n && !dateOf(r, "due")).length;
    const skipped = D.reqs.length - live().length;
    $("#b-summary").innerHTML = (noDue ? `<span class="amb">제출기한 미입력 ${noDue}건 — 위 표에서 입력해 주세요</span><br>` : "") +
      `요구서 <b>${live().length}</b>건 · 질의 <b>${D.items.length + D.merged}</b>개 → <b>${depts.length}</b>개 부서` +
      (n.amb ? ` · <span class="amb">확인 필요 ${n.amb}</span>` : "") + (n.done ? ` · 기제출 갈음 <b>${n.done}</b>` : "") +
      (n.moved ? ` · 배정 변경 <b>${n.moved}</b>` : "") + (D.merged ? ` · 같은 질의 ${D.merged}건 합침` : "") +
      (na.length ? ` · 해당없음 ${na.length}건` : "") + (skipped ? ` · 이미 대장에 있는 ${skipped}건 건너뜀` : "");
    $("#b-noroster").hidden = Object.keys(R.channel).length + Object.keys(R.tasks).length > 0;
    $("#b-reset").disabled = !["dept", "wk", "done", "dates"].some((k) => Object.keys(S[k]).length);
    $("#b-empty-all").hidden = D.items.length > 0;
    apply();
  }
  function apply() {
    const t = $("#b-q").value.trim();
    root.querySelectorAll(".dept").forEach((s) => {
      let n = 0;
      s.querySelectorAll(".rq").forEach((b) => {
        let m = 0;
        b.querySelectorAll(".row").forEach((r) => {
          const ok = (filter === "all" || r.dataset[filter] === "1") &&
            (!t || (s.dataset.dept + s.querySelector(".contacts").textContent + r.querySelector(".body").textContent + r.dataset.s).includes(t));
          r.classList.toggle("hide", !ok); m += ok;
        });
        b.classList.toggle("hide", m === 0); n += m;
      });
      s.classList.toggle("hide", n === 0);
    });
    $("#b-empty").classList.toggle("hide", !D.items.length || !!root.querySelector(".dept:not(.hide)"));
  }
  let tt;
  function toast(m) { const el = $("#b-toast"); el.textContent = m; el.classList.add("on"); clearTimeout(tt); tt = setTimeout(() => el.classList.remove("on"), 2600); }

  // ---------- 학습: 정확도·규칙 제안 ----------
  const IGNORED_KEY = "yogu:ignored-rules";
  const ignored = () => { try { return JSON.parse(localStorage.getItem(IGNORED_KEY) || "[]"); } catch (_) { return []; } };
  function renderLearn() {
    const L = D.learned, st = L.stats, ign = ignored();
    const sugg = L.suggestions.filter((s) => !ign.includes(`${s.keyword}|${s.dept}`) && !(L.added || []).includes(s.keyword));
    const parts = [];
    if (st.total) parts.push(`<p class="acc">지금까지 배분 정확도 <b>${st.rate}%</b> <span class="t3">· 질의 ${st.total}개 중 ${st.kept}개를 초안 그대로 확정</span></p>`);
    for (const s of sugg) {
      parts.push(`<p class="sugg" title="${esc(s.examples.join("\n"))}"><span>‘<b>${esc(s.keyword)}</b>’${esc(josa(s.keyword, "이", "가").slice(s.keyword.length))} 들어간 질의를 <b>${esc(s.dept)}</b>${esc(josa(s.dept, "으로", "로").slice(s.dept.length))} ${s.count}번 옮겼습니다. 규칙으로 추가할까요?</span>` +
        `<button type="button" class="btn sm add-rule" data-k="${esc(s.keyword)}" data-d="${esc(s.dept)}" data-n="${s.count}">규칙 추가</button>` +
        `<button type="button" class="linkbtn ignore-rule" data-k="${esc(s.keyword)}" data-d="${esc(s.dept)}">무시</button></p>`);
    }
    $("#b-learn").innerHTML = parts.join("");
    $("#b-learn").hidden = !parts.length;
  }
  async function addRule(btn) {
    const kw = btn.dataset.k, dept = btn.dataset.d;
    try { await api("/api/settings/rules", { keyword: kw, dept, basis: `정정 ${btn.dataset.n}건` }); } catch (err) { toast(err.message); return; }
    (D.learned.added ??= []).push(kw);
    // 이번 분배안에도 바로 적용 (직접 고친 질의는 그대로 둔다)
    let n = 0;
    for (const it of D.items) {
      if (S.dept[it.id] || it.dept === NA || !it.text.includes(kw) || it.dept === dept) continue;
      S.dept[it.id] = dept; n++;
    }
    save(); renderLearn(); render();
    toast(`규칙을 추가했습니다 · 이번 분배안 ${n}개 질의에 적용, 다음 처리부터 자동 적용`);
  }

  // ---------- 서버 저장 ----------
  async function api(url, body) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || "저장하지 못했습니다.");
    return json;
  }
  const post = (path, body) => api(`${path}/${resultId}`, body);
  // 담당자 명단은 앱 설정(data/settings.json)에 있다. 설정 화면에서 저장하면 여기서 다시 읽는다
  function useSettings(cfg) {
    const { rules, ...names } = cfg;
    R = { channel: {}, tasks: {}, members: {}, excluded: [], custom: [], ...names };
    D.learned.added = [...new Set([...(D.learned.added || []), ...rules.map((r) => r.keyword)])];
  }
  async function reloadSettings() {
    if (!D || root.hidden) return;
    try {
      const res = await fetch("/api/settings");
      if (!res.ok) return;
      const before = JSON.stringify(R);
      useSettings((await res.json()).settings);
      if (JSON.stringify(R) !== before) { render(); toast("담당자 설정을 다시 불러왔습니다"); }
      renderLearn();
    } catch (_) {}
  }
  // 질의에서 '직접 입력'한 사람을 그 부서원으로 설정에 더한다 (최신 설정에 더해 다른 변경을 덮지 않음)
  async function addMember(d, name) {
    const cur = (await (await fetch("/api/settings")).json()).settings;
    const members = { ...cur.members, [d]: [...new Set([...(cur.members[d] || []), name])] };
    useSettings((await api("/api/settings", { members })).settings);
  }

  // 표에서 고친 접수일자·제출기한을 결과 대장에 반영
  async function applyDates() {
    const updates = live().filter((r) => r.rows && S.dates[r.tag]).map((r) => {
      const u = { rows: r.rows };
      if (S.dates[r.tag].date) u.request_date = S.dates[r.tag].date;
      if (S.dates[r.tag].due) u.deadline = S.dates[r.tag].due;
      return u;
    }).filter((u) => u.request_date || u.deadline);
    if (updates.length) await post("/dates", { updates });
  }

  // 질의별 모델 배분과 확정 부서를 '배분 이력'에 남긴다 (정확도·규칙 제안의 재료)
  function logEntries() {
    const reqs = new Map(live().filter((r) => r.rows).map((r) => [r.tag, r]));
    return D.items.filter((it) => reqs.has(it.req) && !(it.dept === NA && deptOf(it) === NA)).map((it) => ({
      doc: reqs.get(it.req).doc || it.req, key: it.key, text: it.text, model: it.dept, final: deptOf(it),
    }));
  }

  async function download(e, asFile) {
    e.preventDefault();
    try { await applyDates(); await post("/log", { entries: logEntries() }); } catch (err) { toast(err.message); return; }
    const toFile = asFile || !local;
    const empty = live().filter((r) => !dateOf(r, "due")).length;
    if (empty && !confirm(`제출기한이 비어 있는 요구서가 ${empty}건 있습니다. 비워 둔 채로 ${toFile ? "다운로드" : "저장"}할까요?`)) {
      root.querySelector('.dt[data-f="due"].empty')?.focus();
      return;
    }
    if (toFile) { window.location.href = downloadHref; return; }
    // PC 실행: 원래 대장 파일에 바로 저장 (직전 내용은 같은 폴더에 _백업.xlsx)
    try {
      const j = await post("/save-local", {});
      toast(`대장에 저장했습니다 · ${j.saved}`);
    } catch (err) { toast(err.message); }
  }

  // ---------- 업무 분장내역 엑셀 ----------
  // 화면의 최종 상태(바꾼 부서·담당자, 기제출)를 그대로 내보낸다
  function exportRows() {
    return D.items.filter((it) => !reqOf(it.req).duplicate).map((it) => {
      const r = reqOf(it.req), d = deptOf(it), notes = [];
      if (d === NA) notes.push(it.dept === NA ? it.why : `부서 변경 · 원래 ${it.dept}`);
      else {
        if (it.amb && !changed(it)) notes.push("확인 필요");
        if (moved(it)) notes.push(`부서 변경 · 원래 ${it.dept}`);
        else if (S.wk[it.id] !== undefined) notes.push("담당자 변경");
      }
      if (it.same) notes.push(`같은 질의 ${it.same.map(keyText).join(", ")}`);
      return {
        dept: d, worker: d === NA ? "" : workerOf(it), doc: r.doc || r.tag, member: r.member, title: r.title,
        key: it.key, text: [it.main, ...it.rest.map((x) => `- ${x}`)].join("\n"), due: dateOf(r, "due"),
        done: !!S.done[it.id] && d !== NA, src: S.src[it.id] || "", note: notes.join("; "),
      };
    });
  }
  async function exportExcel(btn) {
    btn.disabled = true;
    try {
      post("/log", { entries: logEntries() }).catch(() => {}); // 최종 확인한 배분을 배분 이력에도 남긴다
      const res = await fetch("/export", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rows: exportRows(), channel: R.channel }) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || "분장내역을 만들지 못했습니다.");
      const name = decodeURIComponent((res.headers.get("Content-Disposition") || "").match(/filename\*=UTF-8''([^;]+)/)?.[1] || "업무분장내역.xlsx");
      const url = URL.createObjectURL(await res.blob());
      const a = Object.assign(document.createElement("a"), { href: url, download: name });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast("분장내역을 엑셀로 출력했습니다");
    } catch (err) { toast(err.message); } finally { btn.disabled = false; }
  }

  // ---------- 이벤트 ----------
  const itemOf = (el) => D.items.find((x) => x.id === el.closest(".row").dataset.id);
  const focusRow = (id, sel) => root.querySelector(`.row[data-id="${CSS.escape(id)}"] ${sel}`)?.focus();
  function onChange(e) {
    const el = e.target;
    if (el.classList.contains("chk")) {
      const it = itemOf(el); if (el.checked) S.done[it.id] = 1; else { delete S.done[it.id]; delete S.src[it.id]; }
      save(); render(); focusRow(it.id, ".chk");
    } else if (el.classList.contains("mv")) {
      const it = itemOf(el), to = el.value;
      if (to === it.dept) delete S.dept[it.id]; else S.dept[it.id] = to;
      delete S.wk[it.id]; if (to === NA) delete S.done[it.id];
      save(); render();
      toast(to === NA ? `${keyText(it.key)} → 해당없음` : `${keyText(it.key)} → ${to} · 담당 ${workerOf(it) || "미정"} (오른쪽에서 담당자를 바꿀 수 있습니다)`);
      focusRow(it.id, ".wk");
    } else if (el.classList.contains("wk")) {
      const it = itemOf(el), d = deptOf(it); let v = el.value;
      if (v === "__new") {
        v = (prompt(`${d} 담당자 이름을 입력하세요 (다음부터 ${d} 부서원 목록에 나옵니다)`) || "").trim();
        if (!v) { render(); return; }
        if (!members(d).includes(v)) { R.members[d] = [...(R.members[d] || []), v]; addMember(d, v).catch((err) => toast(err.message)); }
      }
      if (v === baseWorker(it)) delete S.wk[it.id]; else S.wk[it.id] = v;
      save(); render(); focusRow(it.id, ".wk");
    } else if (el.classList.contains("dt")) {
      const r = reqOf(el.dataset.tag), f = el.dataset.f;
      (S.dates[r.tag] ??= {})[f] = el.value;
      if (el.value === r[f]) delete S.dates[r.tag][f];
      if (!Object.keys(S.dates[r.tag]).length) delete S.dates[r.tag];
      save(); renderReqs(); render();
      root.querySelector(`.dt[data-tag="${CSS.escape(r.tag)}"][data-f="${f}"]`)?.focus();
    }
  }
  function onClick(e) {
    const use = e.target.closest(".use-prev");
    if (use) {
      // 이전 질의를 기제출 자료로 갈음: 체크와 출처를 함께 남긴다
      const it = itemOf(use), h = it.prev[+use.dataset.i];
      S.done[it.id] = 1; S.src[it.id] = `${prevLabel(h)} (${h.doc})`;
      save(); render(); focusRow(it.id, ".chk"); toast("기제출 자료로 갈음했습니다 — 분장내역에 기제출로 표시됩니다");
      return;
    }
    const add = e.target.closest(".add-rule");
    if (add) { addRule(add); return; }
    const ign = e.target.closest(".ignore-rule");
    if (ign) {
      try { localStorage.setItem(IGNORED_KEY, JSON.stringify([...ignored(), `${ign.dataset.k}|${ign.dataset.d}`])); } catch (_) {}
      renderLearn(); return;
    }
    const seg = e.target.closest(".seg button");
    if (seg) {
      root.querySelectorAll(".seg button").forEach((x) => x.classList.toggle("on", x === seg));
      filter = seg.dataset.f; apply();
    }
  }

  let wired = false;
  function wire() {
    if (wired) return; wired = true;
    root.addEventListener("change", onChange);
    root.addEventListener("click", onClick);
    $("#b-q").addEventListener("input", apply);
    $("#b-download").addEventListener("click", (e) => download(e, false));
    $("#b-download-copy").addEventListener("click", (e) => download(e, true));
    $("#b-open-status").addEventListener("click", async () => {
      try {
        const res = await fetch(`/status/${resultId}`);
        const j = await res.json();
        if (!res.ok) throw new Error(j.error || "현황을 불러오지 못했습니다.");
        window.Dash.show(j, "방금 처리한 대장");
      } catch (err) { toast(err.message); }
    });
    // 설정 화면(새 탭)에서 저장하면 바로, 아니면 이 화면으로 돌아올 때 담당자 명단을 다시 읽는다
    window.addEventListener("storage", (e) => { if (e.key === "yogu:settings-saved") reloadSettings(); });
    window.addEventListener("focus", reloadSettings);
    $("#b-export").addEventListener("click", (e) => exportExcel(e.currentTarget));
    $("#b-reset").addEventListener("click", () => {
      if (!confirm("기제출 표시, 부서·담당자 변경, 날짜 수정을 모두 처음 상태로 되돌릴까요?")) return;
      S = { dept: {}, wk: {}, done: {}, src: {}, dates: {} }; save(); renderReqs(); render();
    });
  }

  window.Board = {
    show(json) {
      root = document.getElementById("board");
      D = json.board;
      R = { channel: {}, tasks: {}, members: {}, excluded: [], custom: [], ...D.roster };
      resultId = json.download_url.split("/").pop();
      downloadHref = `${json.download_url}?name=${encodeURIComponent(json.download_name)}`;
      local = json.local || null;
      $("#b-download").textContent = local ? "대장에 저장" : "관리대장 다운로드";
      $("#b-download").title = local ? local.path : "";
      $("#b-download-copy").hidden = !local;
      $("#b-download-copy").href = downloadHref;
      KEY = "board:" + D.reqs.map((r) => r.tag).join(",");
      S = { dept: {}, wk: {}, done: {}, src: {}, dates: {} };
      try { const v = JSON.parse(localStorage.getItem(KEY) || "null"); if (v) S = { ...S, ...v }; } catch (_) {}
      filter = "all";
      root.querySelectorAll(".seg button").forEach((x) => x.classList.toggle("on", x.dataset.f === "all"));
      $("#b-q").value = "";
      wire(); renderReqs(); renderLearn(); render();
      root.hidden = false;
      root.scrollIntoView({ behavior: "smooth" });
    },
  };
})();
