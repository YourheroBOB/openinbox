/* Agent collaboration (F32 F33): research a person or company, prepare a meeting, or
   mention an agent in a thread (@agent / @research / @prep). Work goes through the BYO
   agent bridge (POST /api/agents/task, /api/agents/mention) and each result becomes a
   deliverable card (MD / HTML) you can preview here. Read only: nothing is sent. */
(() => {
  "use strict";
  const S = {
    zh: {
      nav: "🤝 代理協作", title: "代理協作", hint: "用 BYO agent 研究人物或公司、準備會議。成果存成本機卡片（MD／HTML），不會寄出任何信。",
      tabTask: "發動任務", tabCards: "成果卡片", person: "研究人物", company: "研究公司", meeting: "會議準備",
      target: "對象（人名或公司）", targetPh: "例如：Samira Ortiz", run: "▶ 執行", running: "代理處理中…",
      mentionTitle: "在 thread 中 @agent", mentionHint: "輸入 @agent（或 @research、@prep）開頭的訊息即可觸發；別名 {alias} 只作路由辨識，不收發信。",
      mentionPh: "@research Samira Ortiz 最近的往來重點", mentionRun: "▶ 送出 @agent", notTriggered: "沒有 @agent 提及，未觸發。",
      triggered: "已觸發：{kind}", cards: "成果卡片", noCards: "還沒有成果卡片。", openMd: "預覽 MD", openHtml: "預覽 HTML",
      back: "← 返回", fallback: "已退回本機啟發式", driver: "驅動", created: "產出", kind: "類型", failed: "操作失敗：",
      emptyTarget: "請填對象。", sources: "本機資料來源", noSources: "本機沒有相關資料。", result: "結果",
      copyMd: "複製 Markdown", copied: "已複製", refresh: "重新整理",
      kinds: { research_person: "人物研究", research_company: "公司研究", meeting_prep: "會議準備" },
    },
    en: {
      nav: "🤝 Agent collab", title: "Agent collaboration", hint: "Use your BYO agent to research a person or company, or prepare a meeting. Results are saved as local cards (MD / HTML). Nothing is sent.",
      tabTask: "Run a task", tabCards: "Deliverables", person: "Research person", company: "Research company", meeting: "Meeting prep",
      target: "Subject (person or company)", targetPh: "e.g. Samira Ortiz", run: "▶ Run", running: "Agent working…",
      mentionTitle: "@agent in a thread", mentionHint: "Start a message with @agent (or @research, @prep) to trigger it. The alias {alias} is only a routing word; nothing is sent or received.",
      mentionPh: "@research Samira Ortiz recent threads", mentionRun: "▶ Send @agent", notTriggered: "No @agent mention, nothing triggered.",
      triggered: "Triggered: {kind}", cards: "Deliverables", noCards: "No deliverables yet.", openMd: "Preview MD", openHtml: "Preview HTML",
      back: "← Back", fallback: "Fell back to local heuristic", driver: "Driver", created: "Created", kind: "Kind", failed: "Failed: ",
      emptyTarget: "Enter a subject.", sources: "Local sources", noSources: "No matching local data.", result: "Result",
      copyMd: "Copy Markdown", copied: "Copied", refresh: "Refresh",
      kinds: { research_person: "Person research", research_company: "Company research", meeting_prep: "Meeting prep" },
    },
  };
  const isZh = () => document.documentElement.lang.startsWith("zh");
  const t = (k) => S[isZh() ? "zh" : "en"][k];
  const tf = (k, vars) => String(t(k)).replace(/\{(\w+)\}/g, (_, v) => String(vars[v] ?? ""));
  const langParam = () => (isZh() ? "zh-Hant" : "en");
  const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const getJSON = async (path) => (await fetch(path)).json();
  const postJSON = async (path, body) => {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: langParam(), ...body }) });
    const d = await r.json();
    if (!r.ok || d.error) { const e = new Error(d.error || String(r.status)); e.data = d; throw e; }
    return d;
  };
  const nav = document.getElementById("nav");
  if (!nav || typeof state !== "object" || window.__tpiAgents) return;
  window.__tpiAgents = true;

  const css = document.createElement("style");
  css.textContent = `
    .tag-tabs { display: flex; gap: 6px; margin: 0 0 12px; flex-wrap: wrap; }
    .tag-tabs button { background: none; border: 1px solid var(--line); border-radius: 999px; padding: 4px 12px; color: var(--muted); cursor: pointer; font-size: 12.5px; }
    .tag-tabs button.on { color: var(--ink); border-color: var(--accent); }
    .tag-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 12.5px; margin: 8px 0; }
    .tag-form input[type=text] { flex: 1; min-width: 200px; background: #171410; border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; color: var(--ink); }
    .tag-area { width: 100%; min-height: 90px; background: #120f0c; color: var(--ink); border: 1px solid var(--line); border-radius: 8px; padding: 8px; font: 12.5px/1.5 system-ui, sans-serif; box-sizing: border-box; }
    .tag-out { white-space: pre-wrap; font-size: 12.5px; background: #120f0c; border: 1px solid var(--line); border-radius: 8px; padding: 10px; max-height: 50vh; overflow: auto; margin-top: 8px; }
    .tag-li { display: flex; gap: 8px; align-items: center; padding: 8px 0; border-bottom: 1px solid #221e1a; font-size: 12.5px; flex-wrap: wrap; }
    .tag-li .when { color: var(--muted); font-size: 11px; margin-left: auto; white-space: nowrap; }
    .tag-pill { font-size: 10.5px; border: 1px solid var(--line); border-radius: 999px; padding: 0 6px; color: var(--muted); }
    .tag-pill.fb { color: var(--fyi); }
    .tag-err { color: var(--bad); font-size: 12px; margin: 4px 0; }
    .tag-ok { color: var(--ok); font-size: 12px; margin: 4px 0; }
    .tag-frame { width: 100%; height: 60vh; border: 1px solid var(--line); border-radius: 8px; background: #fff; margin-top: 8px; }
    .tag-src { font-size: 12px; color: var(--muted); margin: 4px 0; }`;
  document.head.appendChild(css);

  const navBtn = document.createElement("button");
  navBtn.dataset.view = "agents";
  const navLabel = document.createElement("span");
  navBtn.append(navLabel);
  nav.appendChild(navBtn);
  const relabel = () => { navLabel.textContent = t("nav"); };
  relabel();

  const view = { tab: "task", kind: "research_person", cards: null, preview: null, lastResult: null, busy: false, taskMsg: "", mentionMsg: "", targetDraft: "", mentionDraft: "" };
  const $pane = () => document.getElementById("pane");

  function tabsHtml() {
    return `<div class="tag-tabs">${[["task", t("tabTask")], ["cards", t("tabCards")]]
      .map(([id, label]) => `<button data-tab="${id}" class="${view.tab === id ? "on" : ""}">${h(label)}</button>`).join("")}</div>`;
  }

  function kindButtons() {
    return ["research_person", "research_company", "meeting_prep"].map((k) =>
      `<button class="btn ${view.kind === k ? "primary" : ""}" data-kind="${k}">${h(t(k === "research_person" ? "person" : k === "research_company" ? "company" : "meeting"))}</button>`).join(" ");
  }

  function resultHtml(res) {
    if (!res) return "";
    const d = res.deliverable || {};
    const src = (res.sources || []).map((s) => `<div class="tag-src">• ${h(s.subject)} · ${h(s.from)} · ${h(s.date)}</div>`).join("");
    return `
      <div class="tag-li"><span class="tag-pill">${h(t("driver"))}: ${h(res.driver || d.driver)}</span>
        ${res.fallback ? `<span class="tag-pill fb">${h(t("fallback"))}</span>` : ""}
        ${res.error ? `<span class="tag-err">${h(res.error)}</span>` : ""}
        <span class="when">${h(d.created || "")}</span></div>
      <div class="tag-out">${h(res.text || "")}</div>
      <div class="tag-sec" style="margin-top:8px;font-size:12px;color:var(--accent2)">${h(t("sources"))}</div>
      ${src || `<div class="tag-src">${h(t("noSources"))}</div>`}
      ${d.id ? `<div class="actionbar"><button class="btn" data-preview="${h(d.id)}" data-fmt="md">${h(t("openMd"))}</button><button class="btn" data-preview="${h(d.id)}" data-fmt="html">${h(t("openHtml"))}</button></div>` : ""}`;
  }

  async function loadCards() {
    try {
      view.cards = await getJSON("/api/agents/deliverables?limit=50");
    } catch (e) {
      view.cards = { deliverables: [], error: e.message };
    }
  }

  function cardsHtml() {
    const items = view.cards?.deliverables || [];
    if (!items.length) return `<p class="muted" style="font-size:12.5px">${h(t("noCards"))}</p>`;
    return items.map((c) => `
      <div class="tag-li">
        <span class="tag-pill">${h((t("kinds"))[c.kind] || c.kind)}</span>
        <b>${h(c.title || c.target || c.id)}</b>
        ${c.fallback ? `<span class="tag-pill fb">${h(t("fallback"))}</span>` : ""}
        <button class="btn ghost" data-preview="${h(c.id)}" data-fmt="md">${h(t("openMd"))}</button>
        <button class="btn ghost" data-preview="${h(c.id)}" data-fmt="html">${h(t("openHtml"))}</button>
        <span class="when">${h(c.created || "")}</span>
      </div>`).join("");
  }

  function previewHtml() {
    const p = view.preview;
    if (!p) return "";
    const src = `/api/agents/deliverables/${encodeURIComponent(p.id)}.${p.fmt}`;
    if (p.fmt === "html") {
      return `<div class="actionbar"><button class="btn" data-back="1">${h(t("back"))}</button></div>
        <iframe class="tag-frame" sandbox="" src="${h(src)}" title="${h(p.id)}"></iframe>`;
    }
    return `<div class="actionbar"><button class="btn" data-back="1">${h(t("back"))}</button></div>
      <div class="tag-out" id="tagMd">…</div>`;
  }

  async function renderPane() {
    if (state.view !== "agents") return;
    if (view.preview) {
      $pane().innerHTML = `<h2 class="mh">${h(t("title"))}</h2>${previewHtml()}`;
      if (view.preview.fmt === "md") {
        try {
          const r = await fetch(`/api/agents/deliverables/${encodeURIComponent(view.preview.id)}.md`);
          const md = await r.text();
          const el = document.getElementById("tagMd");
          if (el) el.textContent = md;
        } catch (e) {
          const el = document.getElementById("tagMd");
          if (el) el.textContent = t("failed") + e.message;
        }
      }
      wire();
      return;
    }
    if (view.tab === "cards") {
      if (!view.cards) await loadCards();
      if (state.view !== "agents") return;
      $pane().innerHTML = `<h2 class="mh">${h(t("title"))}</h2>${tabsHtml()}
        <div class="actionbar"><button class="btn" data-refresh="1">${h(t("refresh"))}</button></div>
        <div class="tag-sec" style="font-size:13px;color:var(--accent2)">${h(t("cards"))}</div>${cardsHtml()}`;
      wire();
      return;
    }
    $pane().innerHTML = `
      <h2 class="mh">${h(t("title"))}</h2>${tabsHtml()}
      <p class="hint" style="margin-top:0">${h(t("hint"))}</p>
      <div class="tag-form">${kindButtons()}</div>
      <div class="tag-form"><input type="text" id="tagTarget" value="${h(view.targetDraft)}" placeholder="${h(t("targetPh"))}" aria-label="${h(t("target"))}"></div>
      <div class="actionbar"><button class="btn primary" data-do="run" ${view.busy ? "disabled" : ""}>${h(view.busy ? t("running") : t("run"))}</button></div>
      <div id="tagMsg">${view.taskMsg}</div>
      <div id="tagResult">${resultHtml(view.lastResult)}</div>
      <div class="tag-sec" style="margin-top:18px;font-size:13px;color:var(--accent2)">${h(t("mentionTitle"))}</div>
      <p class="hint">${h(tf("mentionHint", { alias: "agent@example.com" }))}</p>
      <div class="tag-form"><textarea class="tag-area" id="tagMention" placeholder="${h(t("mentionPh"))}">${h(view.mentionDraft)}</textarea></div>
      <div class="actionbar"><button class="btn" data-do="mention" ${view.busy ? "disabled" : ""}>${h(t("mentionRun"))}</button></div>
      <div id="tagMentionMsg">${view.mentionMsg}</div>`;
    wire();
  }

  function wire() {
    $pane().querySelectorAll("[data-tab]").forEach((b) => b.onclick = () => { view.tab = b.dataset.tab; view.preview = null; view.cards = null; renderPane(); });
    $pane().querySelectorAll("[data-kind]").forEach((b) => b.onclick = () => { view.kind = b.dataset.kind; renderPane(); });
    $pane().querySelectorAll("[data-preview]").forEach((b) => b.onclick = () => { view.preview = { id: b.dataset.preview, fmt: b.dataset.fmt }; renderPane(); });
    $pane().querySelectorAll("[data-back]").forEach((b) => b.onclick = () => { view.preview = null; renderPane(); });
    $pane().querySelectorAll("[data-refresh]").forEach((b) => b.onclick = () => { view.cards = null; renderPane(); });
    $pane().querySelectorAll("[data-do]").forEach((b) => b.onclick = () => {
      if (b.dataset.do === "run") runTask();
      else if (b.dataset.do === "mention") runMention();
    });
  }

  async function runTask() {
    const target = (document.getElementById("tagTarget")?.value || "").trim();
    view.targetDraft = target;
    if (!target) { view.taskMsg = `<div class="tag-err">${h(t("emptyTarget"))}</div>`; renderPane(); return; }
    view.taskMsg = ""; view.busy = true; renderPane();
    try {
      view.lastResult = await postJSON("/api/agents/task", { kind: view.kind, target });
      view.cards = null;
    } catch (e) {
      view.lastResult = null;
      view.taskMsg = `<div class="tag-err">${h(t("failed") + e.message)}</div>`;
    } finally {
      view.busy = false;
      renderPane();
    }
  }

  async function runMention() {
    const text = (document.getElementById("tagMention")?.value || "").trim();
    view.mentionDraft = text;
    if (!text) return;
    view.mentionMsg = ""; view.busy = true; renderPane();
    try {
      const d = await postJSON("/api/agents/mention", { text });
      if (!d.triggered) {
        view.mentionMsg = `<div class="tag-err">${h(t("notTriggered"))}</div>`;
      } else {
        view.lastResult = d;
        view.cards = null;
        view.mentionMsg = `<div class="tag-ok">${h(tf("triggered", { kind: (t("kinds"))[d.mention.kind] || d.mention.kind }))}</div>`;
      }
    } catch (e) {
      view.mentionMsg = `<div class="tag-err">${h(t("failed") + e.message)}</div>`;
    } finally {
      view.busy = false;
      renderPane();
    }
  }

  const coreSetView = window.setView;
  if (typeof coreSetView === "function") {
    window.setView = (v, ...rest) => {
      const out = coreSetView(v, ...rest);
      if (v === "agents") { view.preview = null; view.cards = null; renderPane(); }
      return out;
    };
  }
  new MutationObserver(() => {
    relabel();
    if (state.view === "agents") renderPane();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

  if (new URLSearchParams(location.hash.slice(1)).get("view") === "agents") window.setView("agents");
})();
