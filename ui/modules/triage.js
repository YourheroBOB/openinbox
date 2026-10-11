/* Super Agent triage view: Needs You / Upcoming Today / FYI / Other (GET /api/triage),
   per-mail summary + attachment flag + suggested actions, newsletter digest,
   tasks and task history. Also adds the summary line and 📎 to the mail list. */
(() => {
  "use strict";
  const S = {
    zh: {
      nav: "✦ Super Agent 分流", title: "Super Agent 分流", today: "今天",
      llmOn: "摘要使用 BYO agent：", llmOff: "未接 LLM：摘要為規則式 heuristic（agent.json 設定 driver 可升級）",
      summarize: "✦ 用 agent 重新摘要", summarizing: "摘要中…", digest: "📰 電子報摘要",
      digestAgent: "✦ 用 agent 濃縮", digestTask: "＋任務：瀏覽摘要", copyMd: "複製 Markdown",
      tasks: "任務", history: "任務歷史", noTasks: "目前沒有任務。", noHistory: "還沒有紀錄。",
      done: "完成", dismiss: "略過", reopen: "重開", addTask: "＋任務", taskAdded: "已加入任務",
      openMail: "開啟原信", back: "← 回分流總覽", summary: "摘要", attachment: "附件",
      attFlagged: "信件帶有附件", attMentioned: "內文提到附件", noAtt: "沒有附件",
      actions: "建議後續動作", noReply: "回覆一律只存本機草稿，不會寄出。",
      eventsToday: "今天的行程", noEventsToday: "今天沒有行程", nextEvents: "接下來",
      empty: "這一類沒有信。", markedRead: "已標為已讀", failed: "操作失敗：",
      heuristicTag: "規則", agentTag: "AI", openTasks: "待辦",
      status: { open: "進行中", done: "已完成", dismissed: "已略過" },
      kind: { newsletter: "電子報", promotion: "廣告" },
    },
    en: {
      nav: "✦ Super Agent", title: "Super Agent triage", today: "Today",
      llmOn: "Summaries from BYO agent: ", llmOff: "No LLM wired: summaries are rule-based heuristics (set a driver in agent.json to upgrade)",
      summarize: "✦ Re-summarize with agent", summarizing: "Summarizing…", digest: "📰 Newsletter digest",
      digestAgent: "✦ Condense with agent", digestTask: "+ Task: skim digest", copyMd: "Copy Markdown",
      tasks: "Tasks", history: "Task history", noTasks: "No tasks yet.", noHistory: "Nothing recorded yet.",
      done: "Done", dismiss: "Dismiss", reopen: "Reopen", addTask: "+ Task", taskAdded: "Task added",
      openMail: "Open email", back: "← Back to overview", summary: "Summary", attachment: "Attachment",
      attFlagged: "Has an attachment", attMentioned: "Mentions an attachment", noAtt: "No attachment",
      actions: "Suggested next actions", noReply: "Replies are saved as local drafts only; nothing is sent.",
      eventsToday: "Today's calendar", noEventsToday: "Nothing on the calendar today", nextEvents: "Next up",
      empty: "Nothing in this lane.", markedRead: "Marked read", failed: "Failed: ",
      heuristicTag: "rules", agentTag: "AI", openTasks: "open",
      status: { open: "Open", done: "Done", dismissed: "Dismissed" },
      kind: { newsletter: "Newsletter", promotion: "Promotion" },
    },
  };
  const isZh = () => document.documentElement.lang.startsWith("zh");
  const t = (k) => S[isZh() ? "zh" : "en"][k];
  const langParam = () => (isZh() ? "zh-Hant" : "en");
  const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const notify = (msg, isErr) => (typeof toast === "function" ? toast(msg, isErr) : console.log(msg));
  const getJSON = async (path) => (await fetch(path)).json();
  const postJSON = async (path, body) => {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: langParam(), ...body }) });
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || String(r.status));
    return d;
  };
  const nav = document.getElementById("nav");
  if (!nav || typeof state !== "object" || window.__tpiTriage) return;
  window.__tpiTriage = true;

  const css = document.createElement("style");
  css.textContent = `
    .tpi-lane-h { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 8px; padding: 9px 14px; background: #1a1713; border-bottom: 1px solid var(--line); font-size: 12.5px; letter-spacing: .04em; }
    .tpi-lane-h .n { color: var(--muted); font-size: 11.5px; margin-left: auto; }
    .tpi-dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: var(--other); }
    .tpi-dot.needs_you { background: var(--need); } .tpi-dot.upcoming_today { background: var(--up); }
    .tpi-dot.fyi { background: var(--fyi); } .tpi-dot.other { background: var(--other); }
    .row .tpi-sum { color: #cfc6b8; font-size: 12px; line-height: 1.45; margin-top: 3px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .tpi-att { font-size: 12px; flex: none; }
    .tpi-src { font-size: 9.5px; border: 1px solid var(--line); border-radius: 999px; padding: 0 5px; color: var(--muted); flex: none; }
    .tpi-src.agent { color: var(--ok); border-color: #48603f; }
    .tpi-ev { padding: 7px 14px 7px 38px; font-size: 12px; color: var(--muted); border-bottom: 1px solid #221e1a; }
    .tpi-ev b { color: var(--ink); font-weight: 600; }
    .tpi-digest-row { padding: 9px 14px; font-size: 12.5px; color: var(--accent2); border-bottom: 1px solid #221e1a; cursor: pointer; }
    .tpi-digest-row:hover { background: #1e1a15; }
    .tpi-empty { padding: 10px 14px 12px 38px; color: var(--muted); font-size: 12px; border-bottom: 1px solid #221e1a; }
    .tpi-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 12px 0; }
    .tpi-card { border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; background: var(--panel); }
    .tpi-card .big { font-size: 22px; color: var(--accent2); }
    .tpi-card .muted { font-size: 12px; }
    .tpi-banner { font-size: 12px; padding: 7px 10px; border-radius: 8px; border: 1px dashed #4a4136; color: var(--accent2); margin: 8px 0; }
    .tpi-banner.off { border-color: #6b4a3a; color: var(--need); }
    .tpi-sec { margin: 16px 0 6px; font-size: 13px; color: var(--accent2); border-bottom: 1px dashed #3a332a; padding-bottom: 4px; }
    .tpi-sumbox { white-space: pre-wrap; line-height: 1.65; font-size: 14px; }
    .tpi-label { font-size: 11px; color: var(--muted); margin-top: 4px; }
    .tpi-label.heur { color: var(--need); }
    .tpi-act { display: flex; align-items: center; gap: 8px; margin: 6px 0; flex-wrap: wrap; }
    .tpi-act .why { color: var(--muted); font-size: 12px; }
    .tpi-li { display: flex; gap: 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid #221e1a; font-size: 12.5px; flex-wrap: wrap; }
    .tpi-li .when { color: var(--muted); font-size: 11px; margin-left: auto; white-space: nowrap; }
    .tpi-li .btn { font-size: 11px; padding: 2px 8px; }
    .tpi-pill { font-size: 10.5px; border: 1px solid var(--line); border-radius: 999px; padding: 0 6px; color: var(--muted); }
    .tpi-pill.open { color: var(--accent); } .tpi-pill.done { color: var(--ok); }
    .tpi-md { white-space: pre-wrap; font-size: 12.5px; background: #120f0c; border: 1px solid var(--line); border-radius: 8px; padding: 10px; }`;
  document.head.appendChild(css);

  const navBtn = document.createElement("button");
  navBtn.dataset.view = "super";
  const navLabel = document.createElement("span");
  const navCnt = document.createElement("span");
  navCnt.className = "cnt";
  navBtn.append(navLabel, navCnt);
  const mailBtn = nav.querySelector('[data-view="mail"]');
  nav.insertBefore(navBtn, mailBtn ? mailBtn.nextSibling : nav.firstChild);
  const relabel = () => { navLabel.textContent = t("nav"); };
  relabel();

  const view = { data: null, selected: null };
  const laneName = (id) => (view.data?.lanes || []).find((l) => l.id === id)?.name || id;
  const srcTag = (it) => `<span class="tpi-src ${it.summary_source === "agent" ? "agent" : ""}" title="${h(it.summary_label)}">${h(it.summary_source === "agent" ? t("agentTag") : t("heuristicTag"))}</span>`;
  const attTag = (it) => (it.has_attachment ? `<span class="tpi-att" title="${h(t("attachment"))}">📎</span>` : "");
  const shortDT = (s) => String(s || "").replace("T", " ").slice(5, 16);

  async function load() {
    $list().innerHTML = "<div class='empty'>…</div>";
    try {
      const q = new URLSearchParams({ lang: langParam() });
      if (state.account) q.set("account", state.account);
      view.data = await getJSON("/api/triage?" + q.toString());
    } catch (e) {
      $list().innerHTML = `<div class='empty'>${h(t("failed") + e.message)}</div>`;
      return;
    }
    navCnt.textContent = view.data.counts?.needs_you || "";
    renderList();
    if (view.selected && state.view === "super") showItem(view.selected, true);
    else renderOverview();
  }
  const $list = () => document.getElementById("list");
  const $pane = () => document.getElementById("pane");

  function renderList() {
    const d = view.data;
    let html = "";
    for (const lane of d.lanes) {
      html += `<div class="tpi-lane-h" data-lane="${h(lane.id)}"><span class="tpi-dot ${h(lane.id)}"></span><b>${h(lane.name)}</b><span class="n">${lane.count}${lane.unread ? " · " + lane.unread + "●" : ""}</span></div>`;
      if (lane.id === "upcoming_today") {
        const evs = lane.events || [];
        html += evs.length
          ? evs.map((e) => `<div class="tpi-ev">🗓 <b>${h(e.title)}</b> · ${h(e.all_day ? t("today") : String(e.start_local).slice(11, 16))}</div>`).join("")
          : `<div class="tpi-ev">🗓 ${h(t("noEventsToday"))}</div>`;
      }
      if (lane.id === "other" && lane.count) html += `<div class="tpi-digest-row" data-digest="1">${h(t("digest"))} →</div>`;
      html += lane.items.map((it) => `
        <div class="row tpi-trow ${it.unread ? "unread" : ""}" data-tid="${h(it.id)}">
          <div class="tpi-dot ${h(lane.id)}" style="margin-top:7px"></div>
          <div>
            <div class="rowline"><span class="from">${h(it.from_name)}</span>${attTag(it)}${srcTag(it)}</div>
            <div class="subj">${h(it.subject || "—")}</div>
            <div class="tpi-sum">${h(it.summary)}</div>
          </div>
          <div class="meta">${h(shortDT(it.date_raw))}${it.open_tasks ? `<br><span class="tpi-pill open">${it.open_tasks} ${h(t("openTasks"))}</span>` : ""}</div>
        </div>`).join("") || (lane.id !== "upcoming_today" || !(lane.events || []).length ? `<div class="tpi-empty">${h(t("empty"))}</div>` : "");
    }
    $list().innerHTML = html;
    $list().onclick = (ev) => {
      if (ev.target.closest("[data-digest]")) return showDigest();
      const row = ev.target.closest(".tpi-trow");
      if (!row) return;
      $list().querySelectorAll(".tpi-trow").forEach((r) => r.classList.toggle("on", r === row));
      showItem(row.dataset.tid);
    };
  }

  async function renderOverview() {
    view.selected = null;
    const d = view.data;
    const [tasks, hist] = await Promise.all([
      getJSON("/api/triage/tasks?status=open&lang=" + langParam()).catch(() => ({ tasks: [] })),
      getJSON("/api/triage/history?limit=20&lang=" + langParam()).catch(() => ({ history: [] })),
    ]);
    if (state.view !== "super" || view.selected) return;
    const banner = d.llm
      ? `<div class="tpi-banner">${h(t("llmOn") + d.agent_driver)} · ${h(t("agentTag"))} ${d.summary_sources.agent} / ${h(t("heuristicTag"))} ${d.summary_sources.heuristic}</div>`
      : `<div class="tpi-banner off">⚠ ${h(t("llmOff"))}</div>`;
    $pane().innerHTML = `
      <h2 class="mh">${h(t("title"))}</h2>
      <p class="muted" style="margin:0">${h(t("today"))} ${h(d.today)}</p>
      ${banner}
      <div class="tpi-grid">${d.lanes.map((l) => `
        <div class="tpi-card" data-jump="${h(l.id)}" style="cursor:pointer"><span class="tpi-dot ${h(l.id)}" style="display:inline-block"></span> <strong>${h(l.name)}</strong>
          <div class="big">${l.count}</div><div class="muted">${h(l.description)}</div></div>`).join("")}</div>
      <div class="actionbar">
        <button class="btn primary" data-do="summarize">${h(t("summarize"))}</button>
        <button class="btn" data-do="digest">${h(t("digest"))}</button>
      </div>
      <div class="tpi-sec">${h(t("tasks"))}</div>${taskList(tasks.tasks || [], true)}
      <div class="tpi-sec">${h(t("history"))}</div>${historyList(hist.history || [], true)}
      <p class="hint">${h(t("noReply"))}</p>`;
    wirePane();
  }

  function taskList(tasks, withSubject) {
    if (!tasks.length) return `<p class="muted" style="font-size:12.5px">${h(t("noTasks"))}</p>`;
    return tasks.map((x) => `
      <div class="tpi-li"><span class="tpi-pill ${h(x.status)}">${h(t("status")[x.status] || x.status)}</span>
        <span>${h(x.label)}</span>${withSubject && x.subject ? `<span class="muted">· ${h(x.subject)}</span>` : ""}
        ${x.status === "open"
          ? `<button class="btn" data-task="${x.id}" data-status="done">${h(t("done"))}</button><button class="btn ghost" data-task="${x.id}" data-status="dismissed">${h(t("dismiss"))}</button>`
          : `<button class="btn ghost" data-task="${x.id}" data-status="open">${h(t("reopen"))}</button>`}
        <span class="when">${h(shortDT(x.updated_at))}</span></div>`).join("");
  }

  function historyList(items, withSubject) {
    if (!items.length) return `<p class="muted" style="font-size:12.5px">${h(t("noHistory"))}</p>`;
    return items.map((x) => `<div class="tpi-li"><span>${h(x.text)}</span>${withSubject && x.subject ? `<span class="muted">· ${h(x.subject)}</span>` : ""}<span class="when">${h(shortDT(x.at))}</span></div>`).join("");
  }

  async function showItem(id, quiet) {
    view.selected = id;
    if (!quiet) $pane().innerHTML = "<p class='muted'>…</p>";
    let it;
    try { it = await getJSON(`/api/triage/item/${encodeURIComponent(id)}?lang=${langParam()}`); }
    catch (e) { $pane().innerHTML = `<p class='muted'>${h(t("failed") + e.message)}</p>`; return; }
    if (it.error) { $pane().innerHTML = `<p class='muted'>${h(it.error)}</p>`; return; }
    if (view.selected !== id) return;
    const att = it.attachment || {};
    const attText = att.has
      ? `📎 ${h(att.flagged ? t("attFlagged") : t("attMentioned"))}${(att.names || []).length ? " · " + att.names.map(h).join(", ") : ""}`
      : h(t("noAtt"));
    $pane().innerHTML = `
      <p style="margin:0 0 8px"><button class="btn ghost" data-do="back">${h(t("back"))}</button></p>
      <h2 class="mh">${h(it.subject || "—")}</h2>
      <p class="muted" style="margin:0">${h(it.from_name)} &lt;${h(it.from_email)}&gt; · ${h(shortDT(it.date_raw))} ·
        <span class="tpi-dot ${h(it.lane)}" style="display:inline-block"></span> ${h(laneName(it.lane))}</p>
      <div class="tpi-sec">${h(t("summary"))}</div>
      <div class="tpi-sumbox">${h(it.summary)}</div>
      <div class="tpi-label ${it.summary_source === "agent" ? "" : "heur"}">${h(it.summary_label)}</div>
      <div class="tpi-sec">${h(t("attachment"))}</div><div style="font-size:13px">${attText}</div>
      <div class="tpi-sec">${h(t("actions"))}</div>
      ${(it.suggested_actions || []).map((a) => `
        <div class="tpi-act"><button class="btn ${a.primary ? "primary" : ""}" data-act="${h(a.kind)}" data-ui="${h(a.ui)}">${h(a.label)}</button>
          <button class="btn ghost" data-addtask="${h(a.kind)}">${h(t("addTask"))}</button><span class="why">${h(a.reason)}</span></div>`).join("")}
      <p class="hint" style="margin-top:4px">${h(t("noReply"))}</p>
      <div class="actionbar"><button class="btn" data-do="open">${h(t("openMail"))}</button></div>
      <div class="tpi-sec">${h(t("tasks"))}</div>${taskList(it.tasks || [], false)}
      <div class="tpi-sec">${h(t("history"))}</div>${historyList(it.history || [], false)}`;
    wirePane(it);
  }

  async function logEvent(event, emailId, action) {
    try { await postJSON("/api/triage/history", { event, email_id: emailId || "", action }); } catch {}
  }

  async function openOriginal(id) {
    if (typeof openThread === "function") await openThread(id);
  }

  async function runAction(it, kind, ui) {
    try {
      if (ui === "draft") {
        await logEvent("reply_draft", it.id, kind);
        await openOriginal(it.id);
        if (typeof cpAction === "function") cpAction("draft");
      } else if (ui === "open") {
        await logEvent("opened", it.id, kind);
        await openOriginal(it.id);
      } else if (ui === "calendar") {
        await logEvent("opened", it.id, kind);
        if (typeof setView === "function") setView("calendar");
      } else if (ui === "mark_read") {
        await postJSON("/api/read", { id: it.id, unread: false });
        await logEvent("marked_read", it.id, kind);
        notify(t("markedRead"));
        await load();
      } else {
        await addTask(it.id, kind);
      }
    } catch (e) { notify(t("failed") + e.message, true); }
  }

  async function addTask(emailId, kind) {
    try {
      await postJSON("/api/triage/tasks", { email_id: emailId || "", action: kind });
      notify(t("taskAdded"));
      await load();
    } catch (e) { notify(t("failed") + e.message, true); }
  }

  function wirePane(it) {
    $pane().onclick = async (ev) => {
      const b = ev.target.closest("button, [data-jump]");
      if (!b) return;
      if (b.dataset.jump) {
        const head = $list().querySelector(`.tpi-lane-h[data-lane="${CSS.escape(b.dataset.jump)}"]`);
        if (head) head.scrollIntoView({ block: "start" });
      } else if (b.dataset.do === "back") { $list().querySelectorAll(".tpi-trow").forEach((r) => r.classList.remove("on")); renderOverview(); }
      else if (b.dataset.do === "open" && it) { await logEvent("opened", it.id); openOriginal(it.id); }
      else if (b.dataset.do === "digest") showDigest();
      else if (b.dataset.do === "summarize") summarizeAll(b);
      else if (b.dataset.do === "digestAgent") showDigest(true);
      else if (b.dataset.do === "digestTask") addTask("", "review_digest");
      else if (b.dataset.do === "copyMd" && view.digest) {
        try { await navigator.clipboard.writeText(view.digest.markdown); notify(typeof T === "function" ? T("copied") : "OK"); }
        catch { notify(t("failed"), true); }
      }
      else if (b.dataset.act && it) runAction(it, b.dataset.act, b.dataset.ui);
      else if (b.dataset.addtask && it) addTask(it.id, b.dataset.addtask);
      else if (b.dataset.task) {
        try { await postJSON("/api/triage/tasks/update", { id: Number(b.dataset.task), status: b.dataset.status }); await load(); }
        catch (e) { notify(t("failed") + e.message, true); }
      } else if (b.dataset.mail) { openOriginal(b.dataset.mail); }
    };
  }

  async function summarizeAll(btn) {
    btn.disabled = true; btn.textContent = t("summarizing");
    try {
      const r = await postJSON("/api/triage/summarize", { limit: 50 });
      notify(r.note, !r.ok);
      await load();
    } catch (e) { notify(t("failed") + e.message, true); }
    finally { btn.disabled = false; btn.textContent = t("summarize"); }
  }

  async function showDigest(useAgent) {
    view.selected = null;
    $pane().innerHTML = "<p class='muted'>…</p>";
    let d;
    try {
      d = useAgent ? await postJSON("/api/triage/digest", { account: state.account || "" })
        : await getJSON(`/api/triage/digest?lang=${langParam()}${state.account ? "&account=" + encodeURIComponent(state.account) : ""}`);
    } catch (e) { $pane().innerHTML = `<p class='muted'>${h(t("failed") + e.message)}</p>`; return; }
    view.digest = d;
    $pane().innerHTML = `
      <p style="margin:0 0 8px"><button class="btn ghost" data-do="back">${h(t("back"))}</button></p>
      <h2 class="mh">${h(t("digest"))}</h2>
      <p class="muted" style="margin:0">${h(d.headline)}</p>
      <div class="tpi-label ${d.source === "agent" ? "" : "heur"}">${h(d.source_label)}${d.agent_error ? " · " + h(d.agent_error) : ""}</div>
      ${d.agent_text ? `<div class="tpi-sec">✦ ${h(t("agentTag"))}</div><div class="tpi-sumbox">${h(d.agent_text)}</div>` : ""}
      ${(d.groups || []).map((g) => `
        <div class="tpi-sec">${h(g.sender)} · ${h(t("kind")[g.kind] || g.kind)} · ${g.count}</div>
        ${g.items.map((x) => `<div class="tpi-li"><button class="btn ghost" data-mail="${h(x.id)}">${h(x.subject || "—")}</button>${x.has_attachment ? "📎" : ""}<span class="muted">${h(x.highlight)}</span><span class="when">${h(shortDT(x.date_raw))}</span></div>`).join("")}`).join("")}
      <div class="actionbar">
        <button class="btn primary" data-do="digestAgent">${h(t("digestAgent"))}</button>
        <button class="btn" data-do="digestTask">${h(t("digestTask"))}</button>
        <button class="btn ghost" data-do="copyMd">${h(t("copyMd"))}</button>
      </div>
      <pre class="tpi-md">${h(d.markdown)}</pre>`;
    wirePane();
  }

  async function annotateMailRows() {
    const rows = [...document.querySelectorAll("#list .row[data-i]")];
    const ids = rows.map((r) => state.emails?.[parseInt(r.dataset.i, 10)]?.id).filter(Boolean);
    if (!ids.length || state.view !== "mail") return;
    let data;
    try { data = await postJSON("/api/triage/summaries", { ids }); } catch { return; }
    rows.forEach((row) => {
      const mail = state.emails?.[parseInt(row.dataset.i, 10)];
      const s = mail && data.summaries?.[mail.id];
      if (!s || row.querySelector(".tpi-sum")) return;
      const subj = row.querySelector(".subj");
      const line = document.createElement("div");
      line.className = "tpi-sum";
      line.textContent = s.summary;
      line.title = s.summary_label;
      if (subj) subj.after(line);
      if (s.has_attachment) {
        const clip = document.createElement("span");
        clip.className = "tpi-att";
        clip.textContent = "📎";
        clip.title = t("attachment");
        row.querySelector(".rowline")?.append(clip);
      }
    });
  }

  const coreSetView = window.setView;
  if (typeof coreSetView === "function") {
    window.setView = (v, ...rest) => {
      const out = coreSetView(v, ...rest);
      if (v === "super") load();
      return out;
    };
  }
  const coreLoadInbox = window.loadInbox;
  if (typeof coreLoadInbox === "function") {
    window.loadInbox = async (...args) => {
      const out = await coreLoadInbox(...args);
      if (state.view === "super") load();
      return out;
    };
  }
  let annotateTimer = null;
  new MutationObserver(() => {
    if (state.view !== "mail") return;
    clearTimeout(annotateTimer);
    annotateTimer = setTimeout(annotateMailRows, 30);
  }).observe($list(), { childList: true });
  const coreRefreshCounts = window.refreshCounts;
  if (typeof coreRefreshCounts === "function") {
    window.refreshCounts = async (...args) => {
      const out = await coreRefreshCounts(...args);
      getJSON("/api/triage?lang=" + langParam()).then((d) => { navCnt.textContent = d.counts?.needs_you || ""; }).catch(() => {});
      return out;
    };
  }

  new MutationObserver(() => {
    relabel();
    if (state.view === "super") load();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

  if (new URLSearchParams(location.hash.slice(1)).get("view") === "super") window.setView("super");
  else {
    if (document.querySelector("#list .row[data-i]")) annotateMailRows();
    getJSON("/api/triage?lang=" + langParam()).then((d) => { navCnt.textContent = d.counts?.needs_you || ""; }).catch(() => {});
  }
})();
