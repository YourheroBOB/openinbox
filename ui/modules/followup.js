/* Follow-ups & automation: threads waiting on others for N days (GET /api/followup),
   JSON automation rules with dry run (/api/rules*), and the overnight run with its
   morning brief (/api/overnight/*). Also shows rule labels / local archive on mail rows.
   Everything is local: nudges and rule drafts are local drafts, nothing is sent. */
(() => {
  "use strict";
  const S = {
    zh: {
      nav: "⏰ 追蹤與自動化", title: "追蹤與自動化", tabFollow: "待回覆追蹤", tabRules: "自動化規則", tabNight: "夜班交接",
      followHint: "你寫了最後一封、對方超過 N 天沒回的信件串會浮上來。追蹤草稿只存本機，不會寄出。",
      daysLabel: "幾天沒回就浮上來", save: "儲存", saved: "已儲存", onlyQ: "只看有提問的", answered: "已收到回覆",
      overdue: "逾期未回", waiting: "等待中", snoozed: "已延後", done: "已完成", empty: "沒有等待中的信件串。",
      waitedDays: "已等 {n} 天", dueAt: "到期", sentAt: "寄出", to: "收件者", question: "你問的", noQuestion: "這封沒有直接提問",
      nudge: "✎ 寫追蹤草稿", nudgeMade: "已存成本機草稿 #{id}", nudgeExisting: "已有追蹤草稿 #{id}", openDraft: "開草稿匣",
      snooze: "延後", snooze1: "1 天", snooze3: "3 天", snooze7: "7 天", markDone: "✓ 不用追了", reopen: "重新追蹤",
      openSent: "開啟原信", pick: "點左邊的信件串看細節。",
      rulesHint: "符合條件就自動加標籤、封存、標已讀、起草回覆或加任務。一律先 dry-run；套用只改本機，不碰遠端信箱、不寄信。",
      srcDemo: "目前顯示示範規則（fixtures/rules_demo.json）；存檔後會寫入 rules.json。", srcFile: "規則檔：",
      validate: "檢查格式", dryRun: "▶ Dry-run（不改任何東西）", saveRules: "存檔", apply: "套用規則",
      applyConfirm: "確定要套用已存檔的規則嗎？只會改本機（標籤、本機封存、已讀、本機草稿、任務），不寄信。",
      saveFirst: "編輯器內容跟已存檔的不同，請先存檔再套用。", valid: "格式正確", badJson: "JSON 格式錯誤：",
      matched: "符合的信件", noMatch: "沒有信件符合。", recentRuns: "最近套用紀錄", noRuns: "還沒有套用過。",
      fields: "可用欄位", actions: "可用動作", placeholders: "草稿範本可用",
      nightHint: "夜班一次跑完：分流、自動化規則、待回覆追蹤、預備本機草稿，最後寫一份早晨交接。也可以排程執行 scripts/overnight.py。",
      runNow: "▶ 立即跑夜班", running: "夜班執行中…", optApply: "套用規則（不勾＝dry-run）", optDrafts: "預備草稿",
      optSync: "先同步信件", latest: "最新交接", noBrief: "還沒有交接，按「立即跑夜班」。", runs: "歷次夜班",
      copyMd: "複製 Markdown", copied: "已複製", cron: "排程範例", failed: "操作失敗：",
      archived: "已封存（本機）", unarchive: "取消封存", draftsN: "新草稿 {n} 份", nothingSent: "沒有寄出任何信",
      status: { planned: "將執行", applied: "已套用", already: "先前已做", skipped: "略過", error: "錯誤" },
    },
    en: {
      nav: "⏰ Follow-ups & rules", title: "Follow-ups & automation", tabFollow: "Follow-ups", tabRules: "Automation rules", tabNight: "Overnight brief",
      followHint: "Threads where you wrote last and nobody answered for N days float up here. Nudges are local drafts; nothing is sent.",
      daysLabel: "Surface after this many days", save: "Save", saved: "Saved", onlyQ: "Only ones with a question", answered: "Answered",
      overdue: "Overdue", waiting: "Waiting", snoozed: "Snoozed", done: "Done", empty: "Nothing is waiting on others.",
      waitedDays: "waiting {n} days", dueAt: "Due", sentAt: "Sent", to: "To", question: "You asked", noQuestion: "No direct question in this one",
      nudge: "✎ Draft a nudge", nudgeMade: "Saved as local draft #{id}", nudgeExisting: "Nudge draft #{id} already exists", openDraft: "Open drafts",
      snooze: "Snooze", snooze1: "1 day", snooze3: "3 days", snooze7: "7 days", markDone: "✓ No need to chase", reopen: "Track again",
      openSent: "Open email", pick: "Pick a thread on the left for details.",
      rulesHint: "When conditions match: add a label, archive, mark read, draft a reply or add a task. Always dry run first; applying only changes this app, never the remote mailbox, and sends nothing.",
      srcDemo: "Showing the demo rules (fixtures/rules_demo.json); saving writes rules.json.", srcFile: "Rules file: ",
      validate: "Validate", dryRun: "▶ Dry run (changes nothing)", saveRules: "Save", apply: "Apply rules",
      applyConfirm: "Apply the saved rules? Only local changes (labels, local archive, read state, local drafts, tasks); nothing is sent.",
      saveFirst: "The editor differs from the saved rules. Save first, then apply.", valid: "Looks good", badJson: "Invalid JSON: ",
      matched: "Matching mail", noMatch: "No mail matches.", recentRuns: "Recent applied runs", noRuns: "Nothing applied yet.",
      fields: "Fields", actions: "Actions", placeholders: "Draft template placeholders",
      nightHint: "One pass: triage, automation rules, follow-ups, local drafts, then a morning handoff. Schedule scripts/overnight.py to run it every night.",
      runNow: "▶ Run overnight now", running: "Running…", optApply: "Apply rules (unchecked = dry run)", optDrafts: "Prepare drafts",
      optSync: "Sync mail first", latest: "Latest brief", noBrief: "No brief yet. Hit “Run overnight now”.", runs: "Past runs",
      copyMd: "Copy Markdown", copied: "Copied", cron: "Cron example", failed: "Failed: ",
      archived: "Archived (local)", unarchive: "Unarchive", draftsN: "{n} new drafts", nothingSent: "nothing sent",
      status: { planned: "would run", applied: "applied", already: "already done", skipped: "skipped", error: "error" },
    },
  };
  const isZh = () => document.documentElement.lang.startsWith("zh");
  const t = (k) => S[isZh() ? "zh" : "en"][k];
  const tf = (k, vars) => String(t(k)).replace(/\{(\w+)\}/g, (_, v) => String(vars[v] ?? ""));
  const langParam = () => (isZh() ? "zh-Hant" : "en");
  const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const notify = (msg, isErr) => (typeof toast === "function" ? toast(msg, isErr) : console.log(msg));
  const getJSON = async (path) => (await fetch(path)).json();
  const postJSON = async (path, body) => {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: langParam(), ...body }) });
    const d = await r.json();
    if (!r.ok || d.error) { const e = new Error(d.error || (d.errors || []).map((x) => x.message).join("; ") || String(r.status)); e.data = d; throw e; }
    return d;
  };
  const nav = document.getElementById("nav");
  if (!nav || typeof state !== "object" || window.__tpiFollowup) return;
  window.__tpiFollowup = true;

  const css = document.createElement("style");
  css.textContent = `
    .tfu-tabs { display: flex; gap: 6px; margin: 0 0 12px; flex-wrap: wrap; }
    .tfu-tabs button { background: none; border: 1px solid var(--line); border-radius: 999px; padding: 4px 12px; color: var(--muted); cursor: pointer; font-size: 12.5px; }
    .tfu-tabs button.on { color: var(--ink); border-color: var(--accent); }
    .tfu-h { position: sticky; top: 0; z-index: 2; display: flex; gap: 8px; align-items: center; padding: 9px 14px; background: #1a1713; border-bottom: 1px solid var(--line); font-size: 12.5px; }
    .tfu-h .n { margin-left: auto; color: var(--muted); font-size: 11.5px; }
    .tfu-dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: var(--other); display: inline-block; }
    .tfu-dot.overdue { background: var(--need); } .tfu-dot.waiting { background: var(--up); } .tfu-dot.snoozed { background: var(--fyi); } .tfu-dot.done { background: var(--ok); }
    .tfu-row .q { color: #cfc6b8; font-size: 12px; margin-top: 3px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .tfu-empty { padding: 12px 14px; color: var(--muted); font-size: 12.5px; }
    .tfu-sec { margin: 16px 0 6px; font-size: 13px; color: var(--accent2); border-bottom: 1px dashed #3a332a; padding-bottom: 4px; }
    .tfu-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; font-size: 12.5px; margin: 8px 0; }
    .tfu-form input[type=number] { width: 64px; background: #171410; border: 1px solid var(--line); border-radius: 6px; padding: 4px 6px; color: var(--ink); }
    .tfu-editor { width: 100%; min-height: 300px; background: #120f0c; color: var(--ink); border: 1px solid var(--line); border-radius: 8px; padding: 10px; font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; resize: vertical; box-sizing: border-box; }
    .tfu-md { white-space: pre-wrap; font-size: 12.5px; background: #120f0c; border: 1px solid var(--line); border-radius: 8px; padding: 10px; max-height: 60vh; overflow: auto; }
    .tfu-li { display: flex; gap: 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid #221e1a; font-size: 12.5px; flex-wrap: wrap; }
    .tfu-li .when { color: var(--muted); font-size: 11px; margin-left: auto; white-space: nowrap; }
    .tfu-pill { font-size: 10.5px; border: 1px solid var(--line); border-radius: 999px; padding: 0 6px; color: var(--muted); }
    .tfu-pill.planned { color: var(--accent); } .tfu-pill.applied { color: var(--ok); } .tfu-pill.error { color: var(--bad); }
    .tfu-err { color: var(--bad); font-size: 12px; margin: 4px 0; }
    .tfu-ok { color: var(--ok); font-size: 12px; margin: 4px 0; }
    .tfu-help { font-size: 11.5px; color: var(--muted); line-height: 1.6; }
    .tfu-help code { color: var(--accent2); }
    .tfu-chip { font-size: 10px; border: 1px solid #4a4136; border-radius: 999px; padding: 0 6px; color: var(--accent2); margin-left: 4px; flex: none; }
    .tfu-chip.arch { color: var(--muted); border-style: dashed; }
    #list .row.tfu-archived { opacity: .55; }`;
  document.head.appendChild(css);

  const navBtn = document.createElement("button");
  navBtn.dataset.view = "followup";
  const navLabel = document.createElement("span");
  const navCnt = document.createElement("span");
  navCnt.className = "cnt";
  navBtn.append(navLabel, navCnt);
  nav.appendChild(navBtn);
  const relabel = () => { navLabel.textContent = t("nav"); };
  relabel();

  const view = { tab: "follow", data: null, selected: null, onlyQ: false, rules: null, savedText: "", editorText: null, lastRun: null };
  const $list = () => document.getElementById("list");
  const $pane = () => document.getElementById("pane");
  const shortDT = (s) => String(s || "").replace("T", " ").slice(5, 16);
  const STATUSES = ["overdue", "waiting", "snoozed", "done"];

  async function load() {
    $list().innerHTML = "<div class='empty'>…</div>";
    try {
      const q = new URLSearchParams({ lang: langParam() });
      if (view.onlyQ) q.set("only_questions", "1");
      view.data = await getJSON("/api/followup?" + q.toString());
    } catch (e) {
      $list().innerHTML = `<div class='empty'>${h(t("failed") + e.message)}</div>`;
      return;
    }
    navCnt.textContent = view.data.counts?.overdue || "";
    renderList();
    renderPane();
  }

  function renderList() {
    const items = view.data?.items || [];
    let html = "";
    for (const st of STATUSES) {
      const group = items.filter((i) => i.status === st);
      if (!group.length) continue;
      html += `<div class="tfu-h"><span class="tfu-dot ${h(st)}"></span><b>${h(t(st))}</b><span class="n">${group.length}</span></div>`;
      html += group.map((it) => `
        <div class="row tfu-row ${it.thread === view.selected ? "on" : ""}" data-thread="${h(it.thread)}">
          <div class="tfu-dot ${h(it.status)}" style="margin-top:7px"></div>
          <div>
            <div class="rowline"><span class="from">→ ${h(it.to_name)}</span>${it.nudge_draft_id ? `<span class="tfu-chip">✎ #${h(it.nudge_draft_id)}</span>` : ""}</div>
            <div class="subj">${h(it.subject || "—")}</div>
            <div class="q">${h(it.question || it.excerpt)}</div>
          </div>
          <div class="meta">${h(tf("waitedDays", { n: it.waiting_days }))}<br>${h(shortDT(it.sent_at))}</div>
        </div>`).join("");
    }
    if (!html) html = `<div class="tfu-empty">${h(t("empty"))}</div>`;
    if (view.data?.counts?.answered) html += `<div class="tfu-empty">✓ ${h(t("answered"))} · ${h(view.data.counts.answered)}</div>`;
    $list().innerHTML = html;
    $list().onclick = (ev) => {
      const row = ev.target.closest(".tfu-row");
      if (!row) return;
      view.selected = row.dataset.thread;
      view.tab = "follow";
      $list().querySelectorAll(".tfu-row").forEach((r) => r.classList.toggle("on", r === row));
      renderPane();
    };
  }

  function tabsHtml() {
    return `<div class="tfu-tabs">${[["follow", "tabFollow"], ["rules", "tabRules"], ["night", "tabNight"]]
      .map(([id, k]) => `<button data-tab="${id}" class="${view.tab === id ? "on" : ""}">${h(t(k))}</button>`).join("")}</div>`;
  }

  function renderPane() {
    if (state.view !== "followup") return;
    if (view.tab === "rules") return renderRules();
    if (view.tab === "night") return renderNight();
    renderFollow();
  }

  function renderFollow() {
    const d = view.data || { counts: {}, settings: { days: 3 }, items: [] };
    const it = (d.items || []).find((x) => x.thread === view.selected);
    let detail = `<p class="muted">${h(t("pick"))}</p>`;
    if (it) {
      detail = `
        <h3 class="mh" style="font-size:16px">${h(it.subject || "—")}</h3>
        <p class="muted" style="margin:0">${h(t("to"))} ${h(it.to_name)} &lt;${h(it.to_email)}&gt; · ${h(t("sentAt"))} ${h(shortDT(it.sent_at))} · ${h(t("dueAt"))} ${h(shortDT(it.due_at))}</p>
        <p style="margin:8px 0"><span class="tfu-dot ${h(it.status)}"></span> ${h(t(it.status))} · ${h(tf("waitedDays", { n: it.waiting_days }))}${it.snoozed_until ? " · → " + h(shortDT(it.snoozed_until)) : ""}</p>
        <div class="tfu-sec">${h(t("question"))}</div>
        <div style="font-size:13.5px">${it.question ? h(it.question) : `<span class="muted">${h(t("noQuestion"))}</span>`}</div>
        <p class="muted" style="font-size:12px">${h(it.excerpt)}</p>
        <div class="actionbar">
          <button class="btn primary" data-do="nudge">${h(t("nudge"))}</button>
          ${it.nudge_draft_id ? `<button class="btn ghost" data-do="drafts">${h(t("openDraft"))} #${h(it.nudge_draft_id)}</button>` : ""}
          ${it.in_db ? `<button class="btn ghost" data-do="open">${h(t("openSent"))}</button>` : ""}
        </div>
        <div class="tfu-form">${h(t("snooze"))}:
          <button class="btn ghost" data-snooze="1">${h(t("snooze1"))}</button>
          <button class="btn ghost" data-snooze="3">${h(t("snooze3"))}</button>
          <button class="btn ghost" data-snooze="7">${h(t("snooze7"))}</button>
          ${it.status === "done" || it.status === "snoozed"
            ? `<button class="btn" data-do="reopen">${h(t("reopen"))}</button>`
            : `<button class="btn" data-do="done">${h(t("markDone"))}</button>`}
        </div>`;
    }
    $pane().innerHTML = `
      <h2 class="mh">${h(t("title"))}</h2>${tabsHtml()}
      <p class="hint" style="margin-top:0">${h(t("followHint"))}</p>
      <div class="tfu-form">
        <label>${h(t("daysLabel"))} <input type="number" min="1" max="90" id="tfuDays" value="${h(d.settings?.days ?? d.days ?? 3)}"></label>
        <button class="btn" data-do="saveDays">${h(t("save"))}</button>
        <label><input type="checkbox" id="tfuOnlyQ" ${view.onlyQ ? "checked" : ""}> ${h(t("onlyQ"))}</label>
      </div>
      <div class="tfu-form">${STATUSES.map((s) => `<span><span class="tfu-dot ${h(s)}"></span> ${h(t(s))} ${h(d.counts?.[s] ?? 0)}</span>`).join(" · ")} · ✓ ${h(t("answered"))} ${h(d.counts?.answered ?? 0)}</div>
      <div class="tfu-sec"></div>${detail}`;
    wire(it);
  }

  async function loadRules(force) {
    if (view.rules && !force) return;
    view.rules = await getJSON("/api/rules?lang=" + langParam());
    view.savedText = JSON.stringify({ version: 1, rules: view.rules.rules || [] }, null, 2);
    if (view.editorText === null || force) view.editorText = view.savedText;
  }

  async function renderRules() {
    try { await loadRules(); } catch (e) { $pane().innerHTML = `<p class="muted">${h(t("failed") + e.message)}</p>`; return; }
    if (state.view !== "followup" || view.tab !== "rules") return;
    const r = view.rules;
    let runs = [];
    try { runs = (await getJSON("/api/rules/runs")).runs || []; } catch {}
    const sch = r.schema || { fields: [], actions: [], ops: {}, placeholders: [] };
    $pane().innerHTML = `
      <h2 class="mh">${h(t("title"))}</h2>${tabsHtml()}
      <p class="hint" style="margin-top:0">${h(t("rulesHint"))}</p>
      <p class="muted" style="font-size:12px">${r.source === "file" ? h(t("srcFile") + r.path) : h(t("srcDemo"))}</p>
      ${(r.errors || []).map((e) => `<div class="tfu-err">⚠ ${h(e.message)}</div>`).join("")}
      <textarea class="tfu-editor" id="tfuEditor" spellcheck="false"></textarea>
      <div id="tfuMsg"></div>
      <div class="actionbar">
        <button class="btn primary" data-do="dry">${h(t("dryRun"))}</button>
        <button class="btn" data-do="validate">${h(t("validate"))}</button>
        <button class="btn" data-do="saveRules">${h(t("saveRules"))}</button>
        <button class="btn ghost" data-do="apply">${h(t("apply"))}</button>
      </div>
      <div id="tfuResult">${view.lastRun ? resultHtml(view.lastRun) : ""}</div>
      <div class="tfu-sec">${h(t("recentRuns"))}</div>
      ${runs.length ? runs.slice(0, 8).map((x) => `<div class="tfu-li"><span class="tfu-pill applied">#${h(x.id)}</span><span>${h(x.source)} · ${h(x.matched ?? 0)} ✉ · ${h(t("status").applied)} ${h(x.applied ?? 0)}${x.errors ? " · " + h(t("status").error) + " " + h(x.errors) : ""}</span><span class="when">${h(shortDT(x.at))}</span></div>`).join("") : `<p class="muted" style="font-size:12.5px">${h(t("noRuns"))}</p>`}
      <div class="tfu-sec">${h(t("fields"))} / ${h(t("actions"))}</div>
      <div class="tfu-help">${sch.fields.map((f) => `<code>${h(f.id)}</code> ${h(f.label)} (${f.ops.map((o) => h(o)).join(", ")})`).join("<br>")}</div>
      <div class="tfu-help" style="margin-top:6px">${sch.actions.map((a) => `<code>${h(a.id)}</code> ${h(a.label)}${a.params.length ? " · " + a.params.map((p) => h(p)).join(", ") : ""}`).join("<br>")}</div>
      <div class="tfu-help" style="margin-top:6px">${h(t("placeholders"))}: ${sch.placeholders.map((p) => `<code>${h(p)}</code>`).join(" ")}</div>`;
    const ed = document.getElementById("tfuEditor");
    ed.value = view.editorText ?? view.savedText;
    ed.oninput = () => { view.editorText = ed.value; };
    wire();
  }

  function resultHtml(res) {
    const rows = (res.matched || []).map((m) => `
      <div class="tfu-li"><b>${h(m.rule_name)}</b><button class="btn ghost" data-mail="${h(m.email_id)}">${h(m.subject || "—")}</button>
        ${m.actions.map((a) => `<span class="tfu-pill ${h(a.status)}" title="${h(a.detail?.reason || a.detail?.preview || "")}">${h(a.label)} · ${h(t("status")[a.status] || a.status)}${a.detail?.draft_id ? " #" + h(a.detail.draft_id) : ""}</span>`).join("")}
        <span class="when">${h(shortDT(m.date_raw))}</span></div>`).join("");
    return `<div class="tfu-sec">${h(t("matched"))} · ${h(res.emails_matched)}</div>
      <p class="tfu-ok">${h(res.note)}</p>${rows || `<p class="muted" style="font-size:12.5px">${h(t("noMatch"))}</p>`}`;
  }

  function editorDoc() {
    const ed = document.getElementById("tfuEditor");
    const text = ed ? ed.value : view.editorText;
    try { return { doc: JSON.parse(text), text }; }
    catch (e) { showMsg(t("badJson") + e.message, true); return null; }
  }

  function showMsg(msg, isErr, errors) {
    const box = document.getElementById("tfuMsg");
    if (!box) return notify(msg, isErr);
    box.innerHTML = `<div class="${isErr ? "tfu-err" : "tfu-ok"}">${h(msg)}</div>` +
      (errors || []).map((e) => `<div class="tfu-err">• ${e.id ? h(e.id) + ": " : ""}${h(e.message)}</div>`).join("");
  }

  async function rulesAction(kind) {
    const parsed = editorDoc();
    if (!parsed) return;
    try {
      if (kind === "validate") {
        const r = await postJSON("/api/rules/validate", { doc: parsed.doc });
        showMsg(r.ok ? t("valid") : t("failed"), !r.ok, r.errors);
      } else if (kind === "dry") {
        view.lastRun = await postJSON("/api/rules/run", { doc: parsed.doc, dry_run: true });
        document.getElementById("tfuResult").innerHTML = resultHtml(view.lastRun);
        showMsg(view.lastRun.note, false);
      } else if (kind === "saveRules") {
        await postJSON("/api/rules", { doc: parsed.doc });
        view.editorText = null;
        await loadRules(true);
        notify(t("saved"));
        renderRules();
      } else if (kind === "apply") {
        if (parsed.text.trim() !== view.savedText.trim()) return showMsg(t("saveFirst"), true);
        if (!confirm(t("applyConfirm"))) return;
        view.lastRun = await postJSON("/api/rules/run", { dry_run: false });
        notify(view.lastRun.note, !view.lastRun.ok);
        renderRules();
        if (typeof refreshCounts === "function") refreshCounts();
      }
    } catch (e) { showMsg(t("failed") + e.message, true, e.data?.errors); }
  }

  async function renderNight(fresh) {
    let latest = null, runs = [];
    try {
      [latest, runs] = await Promise.all([
        fresh ? Promise.resolve({ run: fresh }) : getJSON("/api/overnight/latest"),
        getJSON("/api/overnight/runs").then((d) => d.runs || []),
      ]);
      latest = latest.run;
    } catch (e) { $pane().innerHTML = `<p class="muted">${h(t("failed") + e.message)}</p>`; return; }
    if (state.view !== "followup" || view.tab !== "night") return;
    const sum = latest?.summary || {};
    $pane().innerHTML = `
      <h2 class="mh">${h(t("title"))}</h2>${tabsHtml()}
      <p class="hint" style="margin-top:0">${h(t("nightHint"))}</p>
      <div class="tfu-form">
        <label><input type="checkbox" id="tfuOptDrafts" checked> ${h(t("optDrafts"))}</label>
        <label><input type="checkbox" id="tfuOptApply"> ${h(t("optApply"))}</label>
        <label><input type="checkbox" id="tfuOptSync"> ${h(t("optSync"))}</label>
      </div>
      <div class="actionbar"><button class="btn primary" data-do="night">${h(t("runNow"))}</button>
        ${latest ? `<button class="btn ghost" data-do="copyBrief">${h(t("copyMd"))}</button>` : ""}</div>
      <div class="tfu-sec">${h(t("latest"))}${latest ? ` · #${h(latest.id)} · ${h(shortDT(latest.finished_at))} · ${h(tf("draftsN", { n: sum.drafts_new ?? 0 }))} · ${h(t("nothingSent"))}` : ""}</div>
      ${latest ? `<pre class="tfu-md">${h(latest.markdown)}</pre>` : `<p class="muted">${h(t("noBrief"))}</p>`}
      <div class="tfu-sec">${h(t("runs"))}</div>
      ${runs.map((x) => `<div class="tfu-li"><button class="btn ghost" data-run="${h(x.id)}">#${h(x.id)}</button><span>${h(x.source)} · ${h(x.lang)} · ✉ ${h(x.summary?.needs_you ?? 0)} · ⏰ ${h(x.summary?.overdue ?? 0)} · ✎ ${h(x.summary?.drafts_new ?? 0)}${x.ok ? "" : " · ⚠"}</span><span class="when">${h(shortDT(x.finished_at))}</span></div>`).join("")}
      <div class="tfu-sec">${h(t("cron"))}</div>
      <pre class="tfu-md">0 6 * * * cd /path/to/openinbox &amp;&amp; python3 scripts/overnight.py --lang ${h(langParam())}</pre>`;
    view.brief = latest?.markdown || "";
    wire();
  }

  async function runNight(btn) {
    btn.disabled = true; btn.textContent = t("running");
    try {
      const r = await postJSON("/api/overnight/run", {
        drafts: document.getElementById("tfuOptDrafts")?.checked ?? true,
        apply_rules: document.getElementById("tfuOptApply")?.checked ?? false,
        sync: document.getElementById("tfuOptSync")?.checked ?? false,
      });
      notify(`#${r.id} · ${tf("draftsN", { n: r.summary?.drafts_new ?? 0 })} · ${t("nothingSent")}`);
      await load();
      view.tab = "night";
      const full = await getJSON("/api/overnight/run/" + r.id);
      renderNight(full);
      if (typeof refreshCounts === "function") refreshCounts();
    } catch (e) { notify(t("failed") + e.message, true); btn.disabled = false; btn.textContent = t("runNow"); }
  }

  function wire(it) {
    const days = document.getElementById("tfuDays");
    const onlyQ = document.getElementById("tfuOnlyQ");
    if (onlyQ) onlyQ.onchange = () => { view.onlyQ = onlyQ.checked; load(); };
    $pane().onclick = async (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      try {
        if (b.dataset.tab) { view.tab = b.dataset.tab; renderPane(); }
        else if (b.dataset.do === "saveDays" && days) {
          await postJSON("/api/followup/settings", { days: Number(days.value) });
          notify(t("saved")); await load();
        } else if (b.dataset.do === "nudge" && it) {
          const r = await postJSON("/api/followup/nudge", { thread: it.thread });
          notify(tf(r.existing ? "nudgeExisting" : "nudgeMade", { id: r.draft_id }));
          await load();
          if (typeof refreshCounts === "function") refreshCounts();
        } else if (b.dataset.do === "drafts") { if (typeof setView === "function") setView("drafts"); }
        else if (b.dataset.do === "open" && it) { if (typeof openThread === "function") openThread(it.sent_id); }
        else if ((b.dataset.do === "done" || b.dataset.do === "reopen") && it) {
          await postJSON("/api/followup/state", { thread: it.thread, action: b.dataset.do }); await load();
        } else if (b.dataset.snooze && it) {
          await postJSON("/api/followup/state", { thread: it.thread, action: "snooze", days: Number(b.dataset.snooze) }); await load();
        } else if (["dry", "validate", "saveRules", "apply"].includes(b.dataset.do)) rulesAction(b.dataset.do);
        else if (b.dataset.do === "night") runNight(b);
        else if (b.dataset.do === "copyBrief") {
          try { await navigator.clipboard.writeText(view.brief || ""); notify(t("copied")); } catch { notify(t("failed"), true); }
        } else if (b.dataset.run) { renderNight(await getJSON("/api/overnight/run/" + encodeURIComponent(b.dataset.run))); }
        else if (b.dataset.mail) { if (typeof openThread === "function") openThread(b.dataset.mail); }
      } catch (e) { notify(t("failed") + e.message, true); }
    };
  }

  async function annotateMailRows() {
    const rows = [...document.querySelectorAll("#list .row[data-i]")];
    const ids = rows.map((r) => state.emails?.[parseInt(r.dataset.i, 10)]?.id).filter(Boolean);
    if (!ids.length || state.view !== "mail") return;
    let data;
    try { data = await postJSON("/api/rules/marks", { ids }); } catch { return; }
    rows.forEach((row) => {
      const mail = state.emails?.[parseInt(row.dataset.i, 10)];
      const m = mail && data.marks?.[mail.id];
      if (!m || row.querySelector(".tfu-chip")) return;
      const line = row.querySelector(".rowline");
      for (const label of m.labels || []) {
        const chip = document.createElement("span");
        chip.className = "tfu-chip";
        chip.textContent = label;
        line?.append(chip);
      }
      if (m.archived) {
        row.classList.add("tfu-archived");
        const chip = document.createElement("span");
        chip.className = "tfu-chip arch";
        chip.textContent = t("archived");
        line?.append(chip);
      }
    });
  }

  const coreSetView = window.setView;
  if (typeof coreSetView === "function") {
    window.setView = (v, ...rest) => {
      const out = coreSetView(v, ...rest);
      if (v === "followup") load();
      return out;
    };
  }
  const coreRefreshCounts = window.refreshCounts;
  const refreshNav = () => getJSON("/api/followup?lang=" + langParam()).then((d) => { navCnt.textContent = d.counts?.overdue || ""; }).catch(() => {});
  if (typeof coreRefreshCounts === "function") {
    window.refreshCounts = async (...args) => {
      const out = await coreRefreshCounts(...args);
      refreshNav();
      return out;
    };
  }
  let annotateTimer = null;
  new MutationObserver(() => {
    if (state.view !== "mail") return;
    clearTimeout(annotateTimer);
    annotateTimer = setTimeout(annotateMailRows, 40);
  }).observe($list(), { childList: true });
  new MutationObserver(() => {
    relabel();
    view.rules = null;
    if (state.view === "followup") load();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

  if (new URLSearchParams(location.hash.slice(1)).get("view") === "followup") window.setView("followup");
  else {
    refreshNav();
    if (document.querySelector("#list .row[data-i]")) annotateMailRows();
  }
})();
