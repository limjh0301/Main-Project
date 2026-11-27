// 마감 현황 — 관리대장의 제출기한·제출일자로 미제출 요구서를 기한 순으로 보여 준다.
// D-day는 이 PC의 오늘 날짜로 계산한다 (서버 시간대와 무관).
(() => {
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (d) => (d ? d.replaceAll("-", ".") : "—");
  const DAY = 86400000;
  const today = () => { const t = new Date(); return Date.UTC(t.getFullYear(), t.getMonth(), t.getDate()); };
  const toUTC = (iso) => { const [y, m, d] = iso.split("-").map(Number); return Date.UTC(y, m - 1, d); };

  // 상태: overdue(기한 지남) · today · tomorrow · week(2~7일) · later · nodue(기한 없음) · done(제출 완료)
  function classify(r, now) {
    if (r.submitted) return { key: "done", days: null };
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.deadline)) return { key: "nodue", days: null };
    const days = Math.round((toUTC(r.deadline) - now) / DAY);
    const key = days < 0 ? "overdue" : days === 0 ? "today" : days === 1 ? "tomorrow" : days <= 7 ? "week" : "later";
    return { key, days };
  }
  const LABEL = { overdue: "기한 지남", today: "오늘 마감", tomorrow: "내일 마감", week: "이번 주", later: "그 이후", nodue: "기한 없음", done: "제출 완료" };
  const dday = (s) => s.key === "overdue" ? `D+${-s.days}` : s.key === "today" ? "오늘" : s.key === "tomorrow" ? "내일" : s.days != null ? `D-${s.days}` : "기한 없음";

  function render(root, data, source) {
    const now = today();
    const rows = data.records.map((r) => ({ ...r, s: classify(r, now) }));
    const count = (k) => rows.filter((r) => r.s.key === k).length;
    const open = rows.filter((r) => r.s.key !== "done")
      .sort((a, b) => (a.s.days ?? 1e9) - (b.s.days ?? 1e9) || a.doc.localeCompare(b.doc));
    const done = rows.filter((r) => r.s.key === "done").sort((a, b) => b.submitted.localeCompare(a.submitted));

    root.querySelector("#d-sub").textContent = `${source} · 요구서 ${rows.length}건 · 오늘 ${new Date().toLocaleDateString("ko-KR")}`;
    root.querySelector("#d-tiles").innerHTML = ["overdue", "today", "tomorrow", "week", "later", "nodue", "done"].map((k) =>
      `<div class="tile${count(k) && ["overdue", "today"].includes(k) ? " alert" : ""}${count(k) ? "" : " zero"}"><dt>${LABEL[k]}</dt><dd>${count(k)}</dd></div>`).join("");

    root.querySelector("#d-rows").innerHTML = open.length ? open.map((r) => {
      const depts = Object.entries(r.depts).sort((a, b) => b[1] - a[1]);
      return `<tr class="st-${r.s.key}"><td class="dd">${esc(dday(r.s))}</td><td class="mono">${esc(fmt(r.deadline))}</td>` +
        `<td class="mono">${esc(r.doc)}</td><td>${esc(r.member || "—")}</td><td class="ttl">${esc(r.title)}</td>` +
        `<td class="num">${r.questions}</td><td class="dp">${depts.map(([d, n]) => `${esc(d)} ${n}`).join(" · ") || '<span class="t3">—</span>'}</td></tr>`;
    }).join("") : '<tr><td colspan="7" class="t3">미제출 요구서가 없습니다.</td></tr>';

    // 부서별: 미제출 요구서에 걸린 질의 수와 가장 이른 기한
    const by = new Map();
    for (const r of open) for (const [d, n] of Object.entries(r.depts)) {
      const cur = by.get(d) || { n: 0, docs: 0, first: null };
      cur.n += n; cur.docs += 1;
      if (r.s.days != null && (cur.first == null || r.s.days < cur.first.days)) cur.first = r.s;
      by.set(d, cur);
    }
    const depts = [...by.entries()].sort((a, b) => (a[1].first?.days ?? 1e9) - (b[1].first?.days ?? 1e9) || b[1].n - a[1].n);
    root.querySelector("#d-depts").innerHTML = depts.length ? depts.map(([d, v]) =>
      `<li><span class="nm">${esc(d)}</span><span class="t3">요구서 ${v.docs} · 질의 ${v.n}</span><span class="dd${v.first && v.first.days < 1 ? " hot" : ""}">${v.first ? esc(dday(v.first)) : ""}</span></li>`).join("")
      : '<li class="t3">배분 이력이 있는 미제출 요구서가 없습니다.</li>';

    root.querySelector("#d-done").hidden = !done.length;
    root.querySelector("#d-done summary").textContent = `제출 완료 ${done.length}건`;
    root.querySelector("#d-done-rows").innerHTML = done.map((r) =>
      `<tr><td class="mono">${esc(fmt(r.submitted))}</td><td class="mono">${esc(fmt(r.deadline))}</td><td class="mono">${esc(r.doc)}</td><td>${esc(r.member || "—")}</td><td class="ttl">${esc(r.title)}</td></tr>`).join("");
  }

  // 첫 화면 오른쪽 요약: 기한 지남 · 7일 안 마감 · 미제출 건수와 마감이 가까운 요구서 5건
  const SIDE_LIMIT = 5;
  const HOT = ["overdue", "today", "tomorrow"];
  function side(body, data) {
    const now = today();
    const open = data.records.map((r) => ({ ...r, s: classify(r, now) })).filter((r) => r.s.key !== "done")
      .sort((a, b) => (a.s.days ?? 1e9) - (b.s.days ?? 1e9) || a.doc.localeCompare(b.doc));
    const n = (keys) => open.filter((r) => keys.includes(r.s.key)).length;
    const tiles = [["기한 지남", n(["overdue"]), "alert"], ["7일 안 마감", n(["today", "tomorrow", "week"]), ""], ["미제출", open.length, ""]];
    body.innerHTML = `<div class="side-tiles">${tiles.map(([label, v, cls]) =>
      `<div class="${v ? cls : "zero"}"><span>${label}</span><b>${v}</b></div>`).join("")}</div>` +
      (open.length ? `<ul class="side-list">${open.slice(0, SIDE_LIMIT).map((r) =>
        `<li><span class="ttl" title="${esc(`${r.doc} · ${r.title}`)}">${esc(r.title || r.doc)}<small>${esc(r.member ? `${r.member} 의원` : r.doc)} · ${esc(fmt(r.deadline))}</small></span>` +
        `<span class="dd${HOT.includes(r.s.key) ? " hot" : ""}">${esc(dday(r.s))}</span></li>`).join("")}</ul>` +
        (open.length > SIDE_LIMIT ? `<p class="t3 side-more">외 ${open.length - SIDE_LIMIT}건</p>` : "")
        : '<p class="side-empty">미제출 요구서가 없습니다.</p>') +
      '<button type="button" class="btn side-all" id="side-all">전체 보기</button>';
  }

  window.Dash = {
    side,
    show(data, source) {
      const root = document.getElementById("dash");
      render(root, data, source);
      root.hidden = false;
      root.querySelector("#d-close").onclick = () => { root.hidden = true; };
      root.scrollIntoView({ behavior: "smooth" });
    },
  };
})();
