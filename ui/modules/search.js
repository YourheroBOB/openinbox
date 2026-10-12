/* Natural-language search: the toolbar box goes through POST /api/search (FTS5 index,
   Chinese / English query parsing, optional BYO agent rewrite) and shows how the query
   was understood. Adds a Contacts view backed by GET /api/contacts. */
(() => {
  "use strict";
  const S = {
    zh: {
      placeholder: "自然語言搜尋：例如「Samira 上週有附件的信」「未讀的電子報」、from:maya（按 / 聚焦）",
      results: "筆結果", understood: "解讀為", canonical: "等同運算式",
      engineFts: "FTS5 全文索引", engineLike: "LIKE 後備搜尋（本機 SQLite 沒有 FTS5）",
      anchorDemo: "示範模式：相對日期以最新一封信的日期當作今天：",
      agentOn: "✦ Agent 改寫：開", agentOff: "✦ Agent 改寫：關", agentTitle: "用 agent.json 設定的 BYO agent 把句子改寫成搜尋條件",
      clear: "✕ 清除搜尋", noResults: "找不到符合的信。試著放寬條件或拿掉日期。", examples: "試試：",
      nav: "聯絡人", contactsTitle: "聯絡人", contactsHint: "從本機快取的寄件人與收件人整理而成，不會上傳。",
      cq: "搜尋聯絡人：名字、信箱、網域", sortFrequent: "最常往來", sortRecent: "最近往來", sortName: "依名稱",
      peopleOnly: "只看真人（隱藏 noreply／電子報）", noContacts: "沒有符合的聯絡人。", total: "位",
      received: "來信", cc: "同列收件", unread: "未讀", attachments: "附件", first: "首次往來", last: "最近往來",
      searchFrom: "🔍 搜尋此人的信", copyAddr: "複製地址", recent: "最近的信", automated: "自動寄件",
      aliases: "其他稱呼", failed: "操作失敗：",
      ex: ["Samira 上週有附件的信", "未讀的電子報", "9月15日之後的帳單", "from:maya has:attachment", "receipt 或 renewal -cables"],
    },
    en: {
      placeholder: "Natural-language search: e.g. “samira last week with attachments”, “unread newsletters” or from:maya (/ to focus)",
      results: "results", understood: "Understood as", canonical: "Same as",
      engineFts: "FTS5 full-text index", engineLike: "LIKE fallback (no FTS5 in local SQLite)",
      anchorDemo: "Demo mode: relative dates treat the newest mail's date as today: ",
      agentOn: "✦ Agent rewrite: on", agentOff: "✦ Agent rewrite: off", agentTitle: "Let the BYO agent from agent.json turn the sentence into filters",
      clear: "✕ Clear search", noResults: "No matching mail. Try fewer filters or drop the date.", examples: "Try: ",
      nav: "Contacts", contactsTitle: "Contacts", contactsHint: "Built from senders and recipients in the local cache; never uploaded.",
      cq: "Search contacts: name, address, domain", sortFrequent: "Most frequent", sortRecent: "Most recent", sortName: "By name",
      peopleOnly: "People only (hide noreply / newsletters)", noContacts: "No matching contacts.", total: "contacts",
      received: "Received", cc: "Co-recipient", unread: "Unread", attachments: "Attachments", first: "First seen", last: "Last seen",
      searchFrom: "🔍 Search their mail", copyAddr: "Copy address", recent: "Recent mail", automated: "Automated",
      aliases: "Also known as", failed: "Failed: ",
      ex: ["samira last week with attachments", "unread newsletters", "receipts since Sep 15", "from:maya has:attachment", "receipt OR renewal -cables"],
    },
  };
  const isZh = () => document.documentElement.lang.startsWith("zh");
  const t = (k) => S[isZh() ? "zh" : "en"][k];
  const langParam = () => (isZh() ? "zh-Hant" : "en");
  const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const notify = (msg, isErr) => (typeof toast === "function" ? toast(msg, isErr) : console.log(msg));
  const getJSON = async (path) => {
    const r = await fetch(path);
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || String(r.status));
    return d;
  };
  const postJSON = async (path, body) => {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: langParam(), ...body }) });
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || String(r.status));
    return d;
  };
  const nav = document.getElementById("nav");
  const qBox = document.getElementById("q");
  const toolbar = document.querySelector("main .toolbar");
  if (!nav || !qBox || !toolbar || typeof state !== "object" || window.__tpiSearch) return;
  window.__tpiSearch = true;

  const css = document.createElement("style");
  css.textContent = `
    .tpi-sbar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 8px 14px; border-bottom: 1px solid var(--line); font-size: 12px; background: #181511; }
    .tpi-sbar[hidden] { display: none; }
    .tpi-sbar .lbl { color: var(--muted); }
    .tpi-chip { border: 1px solid #4a4136; border-radius: 999px; padding: 1px 9px; color: var(--accent2); background: rgba(196,165,116,.06); white-space: nowrap; }
    .tpi-chip.terms { color: var(--ink); } .tpi-chip.exclude, .tpi-chip.exclude_from, .tpi-chip.exclude_category { color: var(--need); border-color: #6b4a3a; }
    .tpi-sbar .cnt { margin-left: auto; color: var(--muted); white-space: nowrap; }
    .tpi-sbar .btn { font-size: 11.5px; padding: 3px 9px; }
    .tpi-sbar .btn.on { border-color: var(--ok); color: var(--ok); }
    .tpi-sbar .note { flex-basis: 100%; color: var(--muted); font-size: 11.5px; }
    .tpi-sbar .note.warn { color: var(--need); }
    .tpi-sbar code { font-size: 11px; background: #26211b; padding: 0 5px; border-radius: 4px; }
    .tpi-ex { cursor: pointer; border: 1px dashed var(--line); border-radius: 999px; padding: 1px 9px; color: var(--muted); background: transparent; font-size: 11.5px; }
    .tpi-ex:hover { color: var(--ink); border-color: var(--accent); }
    .row .tpi-hit { color: #b9b0a2; font-size: 11.5px; margin-top: 3px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .row .tpi-hit mark, .tpi-hl mark { background: rgba(196,165,116,.28); color: var(--ink); border-radius: 2px; padding: 0 1px; }
    .tpi-chead { position: sticky; top: 0; z-index: 2; display: flex; flex-direction: column; gap: 6px; padding: 10px 14px; background: #1a1713; border-bottom: 1px solid var(--line); }
    .tpi-chead input[type=text] { background: var(--panel); border: 1px solid var(--line); padding: 7px 10px; border-radius: 8px; outline: none; }
    .tpi-chead .opts { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 11.5px; color: var(--muted); }
    .tpi-chead select { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 2px 6px; font-size: 11.5px; }
    .tpi-cbadge { font-size: 10px; border: 1px solid var(--line); border-radius: 999px; padding: 0 6px; color: var(--muted); flex: none; }
    .tpi-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 12px 0; }
    .tpi-stat { border: 1px solid var(--line); border-radius: 10px; padding: 8px 10px; background: var(--panel); }
    .tpi-stat .big { font-size: 19px; color: var(--accent2); } .tpi-stat .muted { font-size: 11.5px; }
    .tpi-mrow { display: flex; gap: 8px; padding: 7px 0; border-bottom: 1px solid #221e1a; cursor: pointer; font-size: 13px; }
    .tpi-mrow:hover { background: #1e1a15; } .tpi-mrow .when { margin-left: auto; color: var(--muted); font-size: 11px; white-space: nowrap; }`;
  document.head.appendChild(css);

  const bar = document.createElement("div");
  bar.id = "tpi-search-bar";
  bar.className = "tpi-sbar";
  bar.hidden = true;
  toolbar.after(bar);

  const sv = { last: null, agent: false, seq: 0 };
  const $list = () => document.getElementById("list");
  const $pane = () => document.getElementById("pane");
  const searchText = () => (state.q || qBox.value || "").trim();
  const shortDT = (s) => String(s || "").replace("T", " ").slice(5, 16);

  function marked(text, needles) {
    const src = String(text || "");
    const words = (needles || []).filter((n) => n && n.length > 0).sort((a, b) => b.length - a.length);
    if (!words.length) return h(src);
    const low = src.toLowerCase();
    let out = "", i = 0;
    while (i < src.length) {
      let hit = null;
      for (const w of words) if (low.startsWith(w, i)) { hit = w; break; }
      if (hit) { out += "<mark>" + h(src.slice(i, i + hit.length)) + "</mark>"; i += hit.length; }
      else { out += h(src[i]); i += 1; }
    }
    return out;
  }

  function setPlaceholder() { qBox.placeholder = t("placeholder"); }

  function renderExamples() {
    bar.innerHTML = `<span class="lbl">${h(t("examples"))}</span>` +
      t("ex").map((x, i) => `<button class="tpi-ex" data-ex="${i}">${h(x)}</button>`).join("");
    bar.hidden = false;
  }

  function renderBar(d) {
    const chips = (d.explain || []).map((c) => `<span class="tpi-chip ${h(c.kind)}">${h(c.text)}</span>`).join("");
    const notes = [];
    if (d.rewrite) notes.push(`<span class="note ${d.rewrite.used ? "" : "warn"}">${h(d.rewrite.note)}</span>`);
    if (d.anchor_source === "demo" && (d.parsed?.after || d.parsed?.before)) notes.push(`<span class="note">${h(t("anchorDemo") + d.anchor)}</span>`);
    if (d.canonical) notes.push(`<span class="note">${h(t("canonical"))}: <code>${h(d.canonical)}</code></span>`);
    if (d.error) notes.push(`<span class="note warn">${h(t("failed") + d.error)}</span>`);
    bar.innerHTML = `<span class="lbl">${h(t("understood"))}</span>${chips}
      <span class="cnt" title="${h(d.engine === "fts5" ? t("engineFts") : t("engineLike"))}">${h(d.total)} ${h(t("results"))} · ${h(d.engine)}</span>
      <button class="btn ${sv.agent ? "on" : ""}" data-do="agent" title="${h(t("agentTitle"))}">${h(sv.agent ? t("agentOn") : t("agentOff"))}</button>
      <button class="btn ghost" data-do="clear">${h(t("clear"))}</button>${notes.join("")}`;
    bar.hidden = false;
  }

  function renderRows(d) {
    const needles = d.terms || [];
    $list().innerHTML = (d.emails || []).map((e, i) => `
      <div class="row ${e.unread ? "unread" : ""}" data-id="${h(e.id)}" data-i="${i}">
        <div class="dot ${h(e.category)}"></div>
        <div>
          <div class="rowline">${typeof avatarHtml === "function" ? avatarHtml(e.from_addr) : ""}<span class="from">${h(typeof fromLabel === "function" ? fromLabel(e.from_addr) : e.from_addr)}</span></div>
          <div class="subj">${marked(e.subject || "—", needles)}</div>
          ${e.highlight ? `<div class="tpi-hit">${marked(e.highlight, needles)}</div>` : ""}
        </div>
        <div class="meta">${h(shortDT(e.date_raw))}<br>${h((e.account || "").split("@")[0])}</div>
      </div>`).join("") || `<div class="empty">${h(t("noResults"))}</div>`;
    $list().onclick = (ev) => {
      const row = ev.target.closest(".row"); if (!row) return;
      state.selIdx = parseInt(row.dataset.i, 10);
      $list().querySelectorAll(".row").forEach((r) => r.classList.toggle("on", r === row));
      if (typeof openThread === "function") openThread(row.dataset.id);
    };
  }

  async function runSearch(text) {
    const seq = ++sv.seq;
    const body = { q: text, limit: 120, agent: sv.agent };
    if (state.account) body.account = state.account;
    if (state.category && state.category !== "all") body.category = state.category;
    $list().innerHTML = "<div class='empty'>…</div>";
    let d;
    try { d = await postJSON("/api/search", body); }
    catch (e) { if (seq === sv.seq) $list().innerHTML = `<div class="empty">${h(t("failed") + e.message)}</div>`; return; }
    if (seq !== sv.seq || state.view !== "mail") return;
    sv.last = d;
    state.emails = d.emails || [];
    state.selIdx = -1;
    renderRows(d);
    renderBar(d);
  }

  function clearSearch() {
    qBox.value = "";
    state.q = "";
    sv.last = null;
    bar.hidden = true;
    window.loadInbox();
  }

  bar.addEventListener("mousedown", (e) => { if (e.target.closest("[data-ex]")) e.preventDefault(); });
  bar.addEventListener("click", (e) => {
    const ex = e.target.closest("[data-ex]");
    if (ex) {
      qBox.value = t("ex")[parseInt(ex.dataset.ex, 10)];
      state.q = qBox.value;
      if (state.view !== "mail" && typeof setView === "function") window.setView("mail"); else window.loadInbox();
      return;
    }
    const btn = e.target.closest("[data-do]");
    if (!btn) return;
    if (btn.dataset.do === "clear") clearSearch();
    else if (btn.dataset.do === "agent") { sv.agent = !sv.agent; window.loadInbox(); }
  });
  qBox.addEventListener("focus", () => { if (!qBox.value.trim() && state.view === "mail") renderExamples(); });
  qBox.addEventListener("blur", () => setTimeout(() => { if (!searchText() && document.activeElement !== qBox) bar.hidden = true; }, 150));

  const coreLoadInbox = window.loadInbox;
  window.loadInbox = async (...args) => {
    const text = state.view === "mail" ? searchText() : "";
    if (!text) {
      sv.seq += 1;
      sv.last = null;
      if (document.activeElement !== qBox) bar.hidden = true;
      return typeof coreLoadInbox === "function" ? coreLoadInbox(...args) : undefined;
    }
    return runSearch(text);
  };

  /* ── contacts view ── */
  const navBtn = document.createElement("button");
  navBtn.dataset.view = "contacts";
  const navLabel = document.createElement("span");
  const navCnt = document.createElement("span");
  navCnt.className = "cnt";
  navBtn.append(navLabel, navCnt);
  nav.appendChild(navBtn);
  const cv = { q: "", sort: "frequent", people: false, seq: 0, items: [] };
  let paneHandler = null;

  function renderContactsShell() {
    $list().innerHTML = `
      <div class="tpi-chead">
        <input type="text" id="tpi-cq" placeholder="${h(t("cq"))}" value="${h(cv.q)}" />
        <div class="opts">
          <select id="tpi-csort">
            ${["frequent", "recent", "name"].map((s) => `<option value="${s}" ${cv.sort === s ? "selected" : ""}>${h(t("sort" + s[0].toUpperCase() + s.slice(1)))}</option>`).join("")}
          </select>
          <label><input type="checkbox" id="tpi-cpeople" ${cv.people ? "checked" : ""} /> ${h(t("peopleOnly"))}</label>
          <span id="tpi-ccount"></span>
        </div>
      </div>
      <div id="tpi-clist"></div>`;
    let timer = null;
    document.getElementById("tpi-cq").addEventListener("input", (e) => {
      cv.q = e.target.value; clearTimeout(timer); timer = setTimeout(fetchContacts, 180);
    });
    document.getElementById("tpi-csort").onchange = (e) => { cv.sort = e.target.value; fetchContacts(); };
    document.getElementById("tpi-cpeople").onchange = (e) => { cv.people = e.target.checked; fetchContacts(); };
    document.getElementById("tpi-clist").onclick = (ev) => {
      const row = ev.target.closest("[data-email]"); if (!row) return;
      document.querySelectorAll("#tpi-clist .row").forEach((r) => r.classList.toggle("on", r === row));
      showContact(row.dataset.email);
    };
  }

  async function fetchContacts() {
    const seq = ++cv.seq;
    const q = new URLSearchParams({ q: cv.q, sort: cv.sort, limit: "300" });
    if (cv.people) q.set("people", "1");
    let d;
    try { d = await getJSON("/api/contacts?" + q.toString()); }
    catch (e) { notify(t("failed") + e.message, true); return; }
    if (seq !== cv.seq || state.view !== "contacts") return;
    cv.items = d.contacts || [];
    const box = document.getElementById("tpi-clist");
    if (!box) return;
    document.getElementById("tpi-ccount").textContent = `${d.total} ${t("total")}`;
    if (!cv.q && !cv.people) navCnt.textContent = d.total || "";
    box.innerHTML = cv.items.map((c) => `
      <div class="row" data-email="${h(c.email)}">
        <div class="dot ${c.unread ? "needs_you" : "fyi"}"></div>
        <div>
          <div class="rowline">${typeof avatarHtml === "function" ? avatarHtml(c.email) : ""}<span class="from">${marked(c.name, cv.q ? [cv.q.toLowerCase()] : [])}</span>${c.automated ? `<span class="tpi-cbadge">${h(t("automated"))}</span>` : ""}</div>
          <div class="subj">${marked(c.email, cv.q ? [cv.q.toLowerCase()] : [])}</div>
        </div>
        <div class="meta">${h(c.count)}<br>${h(shortDT(c.last_date))}</div>
      </div>`).join("") || `<div class="empty">${h(t("noContacts"))}</div>`;
  }

  async function showContact(email) {
    $pane().innerHTML = "<p class='muted'>…</p>";
    let c;
    try { c = await getJSON("/api/contacts/" + encodeURIComponent(email) + "?lang=" + langParam()); }
    catch (e) { $pane().innerHTML = `<p class="muted">${h(t("failed") + e.message)}</p>`; return; }
    const stat = (n, label) => `<div class="tpi-stat"><div class="big">${h(n)}</div><div class="muted">${h(label)}</div></div>`;
    $pane().innerHTML = `
      <h2 class="mh">${h(c.name)}</h2>
      <p class="muted" style="margin:0">${h(c.email)} · ${h(c.domain)}${c.automated ? " · " + h(t("automated")) : ""}</p>
      ${c.aliases?.length ? `<p class="muted" style="margin:4px 0 0">${h(t("aliases"))}: ${h(c.aliases.join(", "))}</p>` : ""}
      <div class="actionbar">
        <button class="btn primary" data-do="searchFrom">${h(t("searchFrom"))}</button>
        <button class="btn ghost" data-do="copyAddr">${h(t("copyAddr"))}</button>
      </div>
      <div class="tpi-stats">
        ${stat(c.received, t("received"))}${stat(c.cc, t("cc"))}${stat(c.unread, t("unread"))}
        ${stat(c.attachments, t("attachments"))}${stat(shortDT(c.first_ts ? new Date(c.first_ts * 1000).toISOString() : ""), t("first"))}${stat(shortDT(c.last_date), t("last"))}
      </div>
      <div class="label">${h(t("recent"))}</div>
      ${(c.emails || []).map((m) => `<div class="tpi-mrow" data-mid="${h(m.id)}"><span>${m.direction === "from" ? "←" : "→"}</span><span>${h(m.subject || "—")}</span>${m.has_attachment ? "<span>📎</span>" : ""}<span class="when">${h(shortDT(m.date_raw))}</span></div>`).join("")}`;
    $pane().onclick = paneHandler = (ev) => {
      const mrow = ev.target.closest("[data-mid]");
      if (mrow && typeof openThread === "function") { openThread(mrow.dataset.mid); return; }
      const btn = ev.target.closest("[data-do]");
      if (!btn) return;
      if (btn.dataset.do === "copyAddr" && typeof copyText === "function") copyText(c.email);
      if (btn.dataset.do === "searchFrom") {
        qBox.value = c.search_query;
        state.q = c.search_query;
        window.setView("mail");
      }
    };
  }

  function dropPaneHandler() {
    if (paneHandler && $pane().onclick === paneHandler) $pane().onclick = null;
  }

  function loadContacts() {
    renderContactsShell();
    $pane().innerHTML = `<h2 class="mh">${h(t("contactsTitle"))}</h2><p class="muted">${h(t("contactsHint"))}</p>`;
    dropPaneHandler();
    fetchContacts();
  }

  const coreSetView = window.setView;
  if (typeof coreSetView === "function") {
    window.setView = (v, ...rest) => {
      const out = coreSetView(v, ...rest);
      if (v !== "mail") bar.hidden = true;
      if (v !== "contacts") dropPaneHandler();
      if (v === "contacts") loadContacts();
      return out;
    };
  }

  function relabel() {
    navLabel.textContent = t("nav");
    setPlaceholder();
    if (state.view === "mail" && sv.last) window.loadInbox();
    if (state.view === "contacts") loadContacts();
  }
  new MutationObserver(relabel).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
  navLabel.textContent = t("nav");
  setPlaceholder();
  getJSON("/api/contacts?limit=1").then((d) => { navCnt.textContent = d.total || ""; }).catch(() => {});

  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.get("view") === "contacts") window.setView("contacts");
  else if (hash.get("q")) {
    qBox.value = hash.get("q");
    state.q = qBox.value;
    if (state.view === "mail") window.loadInbox();
  } else if (state.view === "mail" && searchText()) window.loadInbox();
})();
