/* Skills: Morning Brief, Catch Me Up, Organize Inbox, Find It For Me, Meeting Prep,
   Brief this person, Turn into a slide (HTML deck file), CRM this contact (local contacts CRM).
   Each skill has an on/off switch (POST /api/skills/settings); a switched-off skill refuses to run.
   Also adds "Brief / CRM / Slide" buttons to the open email. */
(() => {
  "use strict";
  const S = {
    zh: {
      nav: "✦ 技能", title: "技能", intro: "一鍵在本機信件快取上跑的工作。每個都可以在這裡開關；關閉的技能會拒絕執行。",
      on: "開啟", off: "已關閉", run: "執行", running: "執行中…", disabledRun: "此技能已關閉，打開開關才能執行。",
      toggledOn: "已開啟：", toggledOff: "已關閉：", runs: "次", never: "尚未執行", lastRun: "上次",
      today: "日期（可留空＝今天）", hours: "回看幾小時", query: "要找什麼（支援 from: to: has:attachment is:unread after: before:）",
      event: "行程", nextEvent: "（下一個行程）", person: "姓名或信箱", fromSelected: "用目前開啟那封信的寄件人",
      slideSource: "來源", srcEmail: "目前開啟的信", srcSkill: "某個技能的結果", srcMd: "自己貼 Markdown",
      slideTitle: "標題（可留空）", markdown: "Markdown", pickSkill: "技能", tags: "標籤（逗號分隔）",
      stage: "階段", note: "筆記", noEmail: "請先在「郵件」開一封信。", result: "結果",
      openSlide: "開啟投影片", slidesSaved: "投影片檔", noSlides: "還沒有投影片。", toSlide: "▤ 轉成投影片",
      copyMd: "複製 Markdown", copied: "已複製", failed: "失敗：", agentText: "AI 改寫",
      contacts: "聯絡人 CRM", noContacts: "還沒有聯絡人。開一封信按「加入 CRM」，或在這裡執行「加入聯絡人 CRM」。",
      save: "儲存", del: "刪除", delConfirm: "從本機 CRM 刪除這位聯絡人？", deleted: "已刪除", saved: "已儲存",
      emails: "封", addNote: "新增筆記", file: "檔案",
      quickBrief: "👤 這個人是誰", quickCrm: "＋ 加入 CRM", quickSlide: "▤ 轉成投影片",
      readOnly: "技能只讀取本機快取；不搬信、不貼標、不寄信。",
      stages: { lead: "潛在", active: "往來中", customer: "客戶", partner: "夥伴", vendor: "廠商", other: "其他" },
    },
    en: {
      nav: "✦ Skills", title: "Skills", intro: "One-click jobs over your local mail cache. Switch each one on or off here; a switched-off skill refuses to run.",
      on: "On", off: "Off", run: "Run", running: "Running…", disabledRun: "This skill is off. Turn it on to run it.",
      toggledOn: "Turned on: ", toggledOff: "Turned off: ", runs: "runs", never: "never run", lastRun: "last",
      today: "Date (blank = today)", hours: "Look back (hours)", query: "What to find (from: to: has:attachment is:unread after: before: work)",
      event: "Event", nextEvent: "(next event)", person: "Name or address", fromSelected: "Use the sender of the open email",
      slideSource: "Source", srcEmail: "The open email", srcSkill: "A skill result", srcMd: "Paste Markdown",
      slideTitle: "Title (optional)", markdown: "Markdown", pickSkill: "Skill", tags: "Tags (comma separated)",
      stage: "Stage", note: "Note", noEmail: "Open an email in Mail first.", result: "Result",
      openSlide: "Open slides", slidesSaved: "Slide files", noSlides: "No slides yet.", toSlide: "▤ Turn into a slide",
      copyMd: "Copy Markdown", copied: "Copied", failed: "Failed: ", agentText: "AI rewrite",
      contacts: "Contacts CRM", noContacts: "No contacts yet. Open an email and hit \"Add to CRM\", or run \"CRM this contact\" here.",
      save: "Save", del: "Delete", delConfirm: "Delete this contact from the local CRM?", deleted: "Deleted", saved: "Saved",
      emails: "emails", addNote: "Add a note", file: "File",
      quickBrief: "👤 Brief this person", quickCrm: "+ Add to CRM", quickSlide: "▤ Turn into a slide",
      readOnly: "Skills only read the local cache: nothing is moved, labelled or sent.",
      stages: { lead: "Lead", active: "Active", customer: "Customer", partner: "Partner", vendor: "Vendor", other: "Other" },
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
    if (!r.ok || d.error) { const e = new Error(d.message || d.error || String(r.status)); e.data = d; e.status = r.status; throw e; }
    return d;
  };
  const md = (src) => (typeof mdHtml === "function" ? mdHtml(src) : `<pre>${h(src)}</pre>`);
  const nav = document.getElementById("nav");
  if (!nav || typeof state !== "object" || window.__tpiSkills) return;
  window.__tpiSkills = true;

  const css = document.createElement("style");
  css.textContent = `
    .sk-row { display: flex; align-items: center; gap: 10px; padding: 11px 14px; border-bottom: 1px solid #221e1a; cursor: pointer; }
    .sk-row:hover, .sk-row.on { background: #1e1a15; }
    .sk-row .nm { font-size: 13.5px; } .sk-row .ds { color: var(--muted); font-size: 11.5px; margin-top: 2px; }
    .sk-row.off .nm { color: var(--muted); text-decoration: line-through; }
    .sk-sw { margin-left: auto; flex: none; width: 38px; height: 21px; border-radius: 999px; border: 1px solid var(--line); background: #2a241d; position: relative; cursor: pointer; padding: 0; }
    .sk-sw::after { content: ""; position: absolute; top: 2px; left: 2px; width: 15px; height: 15px; border-radius: 50%; background: var(--muted); transition: left .15s; }
    .sk-sw.on { background: #3d5236; border-color: #48603f; } .sk-sw.on::after { left: 19px; background: var(--ok); }
    .sk-tag { font-size: 10px; color: var(--muted); border: 1px solid var(--line); border-radius: 999px; padding: 0 6px; flex: none; }
    .sk-form { display: grid; gap: 8px; margin: 10px 0; }
    .sk-form label { font-size: 12px; color: var(--muted); display: grid; gap: 4px; }
    .sk-form input, .sk-form select, .sk-form textarea { background: #120f0c; color: var(--ink); border: 1px solid var(--line); border-radius: 8px; padding: 7px 9px; font: inherit; font-size: 13px; }
    .sk-form textarea { min-height: 110px; resize: vertical; }
    .sk-off { font-size: 12.5px; padding: 8px 10px; border-radius: 8px; border: 1px dashed #6b4a3a; color: var(--need); margin: 8px 0; }
    .sk-label { font-size: 11px; color: var(--muted); margin: 4px 0; } .sk-label.heur { color: var(--need); }
    .sk-out { border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; background: var(--panel); margin-top: 8px; font-size: 13.5px; line-height: 1.6; }
    .sk-sec { margin: 16px 0 6px; font-size: 13px; color: var(--accent2); border-bottom: 1px dashed #3a332a; padding-bottom: 4px; }
    .sk-li { display: flex; gap: 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid #221e1a; font-size: 12.5px; flex-wrap: wrap; }
    .sk-li .when { color: var(--muted); font-size: 11px; margin-left: auto; }
    .sk-li .btn { font-size: 11px; padding: 2px 8px; }
    .sk-ct { border: 1px solid var(--line); border-radius: 10px; padding: 9px 12px; margin: 8px 0; background: var(--panel); font-size: 12.5px; }
    .sk-ct .row2 { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 6px; }
    .sk-ct input, .sk-ct select { background: #120f0c; color: var(--ink); border: 1px solid var(--line); border-radius: 6px; padding: 3px 6px; font-size: 12px; }
    .sk-quick { display: inline-flex; gap: 6px; flex-wrap: wrap; }`;
  document.head.appendChild(css);

  const navBtn = document.createElement("button");
  navBtn.dataset.view = "skills";
  const navLabel = document.createElement("span");
  navBtn.append(navLabel);
  const anchor = nav.querySelector('[data-view="brain"]');
  nav.insertBefore(navBtn, anchor || null);
  const relabel = () => { navLabel.textContent = t("nav"); };
  relabel();

  const view = { skills: [], current: "morning-brief", result: null, events: [], stages: [], form: {} };
  const $list = () => document.getElementById("list");
  const $pane = () => document.getElementById("pane");
  const skill = (slug) => view.skills.find((s) => s.slug === slug);
  const shortDT = (s) => String(s || "").replace("T", " ").slice(0, 16);
  const selectedSender = () => {
    const f = state.selected?.from_addr || "";
    return (f.match(/<([^>]+)>/)?.[1] || f).trim();
  };

  async function load() {
    try {
      const d = await getJSON("/api/skills?lang=" + langParam());
      view.skills = d.skills || [];
      view.stages = d.stages || [];
    } catch (e) { $list().innerHTML = `<div class='empty'>${h(t("failed") + e.message)}</div>`; return; }
    renderList();
    renderPane();
  }

  function renderList() {
    $list().innerHTML = view.skills.map((s) => `
      <div class="sk-row ${s.enabled ? "" : "off"} ${s.slug === view.current ? "on" : ""}" data-slug="${h(s.slug)}">
        <div><div class="nm">${h(s.name)}</div><div class="ds">${s.runs ? h(s.runs + " " + t("runs") + " · " + t("lastRun") + " " + shortDT(s.last_run_at)) : h(t("never"))}</div></div>
        <span class="sk-tag">${h(s.group)}</span>
        <button class="sk-sw ${s.enabled ? "on" : ""}" data-toggle="${h(s.slug)}" title="${h(s.enabled ? t("on") : t("off"))}" aria-pressed="${s.enabled}"></button>
      </div>`).join("");
    $list().onclick = async (ev) => {
      const sw = ev.target.closest("[data-toggle]");
      if (sw) { ev.stopPropagation(); return toggle(sw.dataset.toggle); }
      const row = ev.target.closest(".sk-row");
      if (!row) return;
      view.current = row.dataset.slug;
      view.result = null;
      renderList();
      renderPane();
    };
  }

  async function toggle(slug) {
    const s = skill(slug);
    if (!s) return;
    try {
      const d = await postJSON("/api/skills/settings", { slug, enabled: !s.enabled });
      view.skills = d.skills || view.skills;
      notify((!s.enabled ? t("toggledOn") : t("toggledOff")) + s.name);
      renderList();
      if (view.current === slug) renderPane();
    } catch (e) { notify(t("failed") + e.message, true); }
  }

  const val = (id) => document.getElementById(id)?.value ?? "";
  const input = (id, label, type, value, extra) => `<label>${h(label)}<input id="${id}" type="${type}" value="${h(value ?? "")}" ${extra || ""}/></label>`;

  function formHtml(s) {
    const f = view.form[s.slug] || {};
    switch (s.slug) {
      case "morning-brief": return input("skToday", t("today"), "date", f.today);
      case "catch-me-up": return input("skHours", t("hours"), "number", f.hours || 72, 'min="1" max="720"');
      case "find-it": return input("skQuery", t("query"), "text", f.query, 'autofocus');
      case "meeting-prep": return `<label>${h(t("event"))}<select id="skEvent"><option value="">${h(t("nextEvent"))}</option>${view.events.map((e) =>
        `<option value="cal:${h(e.id)}" ${f.event_id === "cal:" + e.id ? "selected" : ""}>${h(shortDT(e.start_local))} · ${h(e.title)}</option>`).join("")}</select></label>`;
      case "brief-person": return input("skPerson", t("person"), "text", f.person ?? selectedSender()) + personHint();
      case "crm-contact": return input("skPerson", t("person"), "text", f.person ?? selectedSender()) + personHint()
        + input("skTags", t("tags"), "text", f.tags)
        + `<label>${h(t("stage"))}<select id="skStage"><option value=""></option>${view.stages.map((x) => `<option value="${h(x)}">${h(t("stages")[x] || x)}</option>`).join("")}</select></label>`
        + input("skNote", t("note"), "text", f.note);
      case "slide": {
        const src = f.source || (state.selected ? "email" : "skill");
        return `<label>${h(t("slideSource"))}<select id="skSrc">
            <option value="email" ${src === "email" ? "selected" : ""}>${h(t("srcEmail"))}${state.selected ? " · " + h(state.selected.subject || "") : ""}</option>
            <option value="skill" ${src === "skill" ? "selected" : ""}>${h(t("srcSkill"))}</option>
            <option value="markdown" ${src === "markdown" ? "selected" : ""}>${h(t("srcMd"))}</option></select></label>
          <label data-src="skill">${h(t("pickSkill"))}<select id="skInner">${view.skills.filter((x) => x.agent).map((x) =>
            `<option value="${h(x.slug)}" ${f.from_skill === x.slug ? "selected" : ""}>${h(x.name)}${x.enabled ? "" : " (" + h(t("off")) + ")"}</option>`).join("")}</select></label>
          <label data-src="markdown">${h(t("markdown"))}<textarea id="skMd">${h(f.markdown || "")}</textarea></label>
          ${input("skTitle", t("slideTitle"), "text", f.title)}`;
      }
      default: return "";
    }
  }
  const personHint = () => (state.selected ? `<button class="btn ghost" type="button" data-do="fromSel" style="justify-self:start">${h(t("fromSelected"))}</button>` : "");

  function collect(slug) {
    switch (slug) {
      case "morning-brief": return val("skToday") ? { today: val("skToday") } : {};
      case "catch-me-up": return { hours: Number(val("skHours")) || 72 };
      case "find-it": return { query: val("skQuery") };
      case "meeting-prep": return val("skEvent") ? { event_id: val("skEvent") } : {};
      case "brief-person": return { person: val("skPerson") };
      case "crm-contact": return { person: val("skPerson"), tags: val("skTags"), stage: val("skStage"), note: val("skNote") };
      case "slide": {
        const src = val("skSrc");
        const out = { title: val("skTitle"), source: src };
        if (src === "email") out.email_id = state.selected?.id || "";
        else if (src === "skill") out.from_skill = val("skInner");
        else out.markdown = val("skMd");
        return out;
      }
      default: return {};
    }
  }

  function syncSlideSource() {
    const src = val("skSrc");
    $pane().querySelectorAll("[data-src]").forEach((el) => { el.style.display = el.dataset.src === src ? "" : "none"; });
  }

  async function renderPane() {
    const s = skill(view.current);
    if (!s) { $pane().innerHTML = ""; return; }
    if (s.slug === "meeting-prep" && !view.events.length) {
      try { view.events = (await getJSON("/api/calendar")).events || []; } catch {}
    }
    const r = view.result && view.result.skill === s.slug ? view.result : null;
    $pane().innerHTML = `
      <h2 class="mh">${h(s.name)}</h2>
      <p class="muted" style="margin:0">${h(s.description)}</p>
      ${s.enabled ? "" : `<div class="sk-off">⏻ ${h(t("disabledRun"))}</div>`}
      <form class="sk-form" id="skForm" onsubmit="return false">${formHtml(s)}</form>
      <div class="actionbar">
        <button class="btn primary" data-do="run" ${s.enabled ? "" : "disabled"}>${h(t("run"))}</button>
        <button class="btn ghost" data-do="toggle">${h(s.enabled ? t("on") : t("off"))} ⏻</button>
      </div>
      <div id="skResult">${r ? resultHtml(r) : ""}</div>
      ${s.slug === "slide" ? `<div class="sk-sec">${h(t("slidesSaved"))}</div><div id="skSlides"></div>` : ""}
      ${s.slug === "crm-contact" || s.slug === "brief-person" ? `<div class="sk-sec">${h(t("contacts"))}</div><div id="skContacts"></div>` : ""}
      <p class="hint">${h(t("readOnly"))}</p>`;
    wirePane();
    if (s.slug === "slide") { syncSlideSource(); loadSlides(); }
    if (s.slug === "crm-contact" || s.slug === "brief-person") loadContacts();
  }

  function resultHtml(r) {
    const d = r.data || {};
    let extra = "";
    if (r.skill === "slide" && d.url) extra = `<p><a class="btn primary" href="${h(d.url)}" target="_blank" rel="noopener">${h(t("openSlide"))} ↗</a> <span class="muted" style="font-size:12px">${h(t("file"))}: ${h(d.file)} · ${h(d.slides)}</span></p>`;
    return `
      <div class="sk-sec">${h(t("result"))} · ${h(r.title)}</div>
      <div class="sk-label ${r.source === "agent" ? "" : "heur"}">${h(r.source_label)}${r.agent_error ? " · " + h(r.agent_error) : ""}</div>
      ${extra}
      ${r.agent_text ? `<div class="sk-sec">✦ ${h(t("agentText"))}</div><div class="sk-out">${md(r.agent_text)}</div>` : ""}
      <div class="sk-out">${md(r.markdown)}</div>
      <div class="actionbar">
        ${r.skill !== "slide" && r.skill !== "crm-contact" ? `<button class="btn" data-do="toSlide">${h(t("toSlide"))}</button>` : ""}
        <button class="btn ghost" data-do="copyMd">${h(t("copyMd"))}</button>
      </div>`;
  }

  async function run(slug, args) {
    const s = skill(slug);
    try {
      const r = await postJSON("/api/skills/run", { skill: slug, ...args });
      view.result = r;
      view.current = slug;
      if (s) { s.runs = (s.runs || 0) + 1; s.last_run_at = r.generated_at; }
      if (state.view === "skills") { renderList(); await renderPane(); }
      if (slug === "slide" && r.data?.url) notify(r.data.note);
      return r;
    } catch (e) {
      notify(t("failed") + e.message, true);
      if (e.status === 403) await load();
      throw e;
    }
  }

  function wirePane() {
    const form = document.getElementById("skForm");
    form?.addEventListener("change", (ev) => { if (ev.target.id === "skSrc") syncSlideSource(); });
    form?.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && ev.target.tagName === "INPUT") { ev.preventDefault(); $pane().querySelector('[data-do="run"]')?.click(); } });
    $pane().onclick = async (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      const s = skill(view.current);
      const act = b.dataset.do;
      if (act === "toggle") return toggle(view.current);
      if (act === "fromSel") { const p = document.getElementById("skPerson"); if (p) p.value = selectedSender(); return; }
      if (act === "run" && s) {
        const args = collect(s.slug);
        view.form[s.slug] = args;
        if (s.slug === "slide" && args.source === "email" && !args.email_id) return notify(t("noEmail"), true);
        delete args.source;
        b.disabled = true; b.textContent = t("running");
        try { await run(s.slug, args); } catch {} finally { b.disabled = false; b.textContent = t("run"); }
        return;
      }
      if (act === "toSlide" && view.result) {
        b.disabled = true;
        try { await run("slide", { markdown: view.result.agent_text || view.result.markdown, title: view.result.title }); } catch {}
        finally { b.disabled = false; }
        return;
      }
      if (act === "copyMd" && view.result) {
        try { await navigator.clipboard.writeText(view.result.agent_text || view.result.markdown); notify(t("copied")); }
        catch { notify(t("failed"), true); }
        return;
      }
      if (b.dataset.ct) return contactAction(b);
    };
  }

  async function loadSlides() {
    const box = document.getElementById("skSlides");
    if (!box) return;
    let d;
    try { d = await getJSON("/api/skills/slides"); } catch { return; }
    box.innerHTML = (d.slides || []).map((x) => `<div class="sk-li"><a href="${h(x.url)}" target="_blank" rel="noopener">${h(x.name)}</a><span class="when">${h(shortDT(x.modified))}</span></div>`).join("")
      || `<p class="muted" style="font-size:12.5px">${h(t("noSlides"))}</p>`;
  }

  async function loadContacts() {
    const box = document.getElementById("skContacts");
    if (!box) return;
    let d;
    try { d = await getJSON("/api/skills/crm"); } catch { return; }
    const stages = d.stages || view.stages;
    box.innerHTML = (d.contacts || []).map((c) => `
      <div class="sk-ct" data-email="${h(c.email)}">
        <strong>${h(c.name || c.email)}</strong> <span class="muted">&lt;${h(c.email)}&gt; · ${h(c.org || "")} · ${h(c.emails_total || 0)} ${h(t("emails"))} · ${h(shortDT(c.last_seen))}</span>
        ${c.last_subject ? `<div class="muted">${h(c.last_subject)}</div>` : ""}
        ${(c.notes || []).slice(-3).map((n) => `<div>📝 ${h(n.text)} <span class="muted">${h(String(n.at).slice(0, 10))}</span></div>`).join("")}
        <div class="row2">
          <select data-f="stage">${stages.map((x) => `<option value="${h(x)}" ${c.stage === x ? "selected" : ""}>${h(t("stages")[x] || x)}</option>`).join("")}</select>
          <input data-f="tags" value="${h((c.tags || []).join(", "))}" placeholder="${h(t("tags"))}" />
          <input data-f="note" placeholder="${h(t("addNote"))}" />
          <button class="btn" data-ct="save">${h(t("save"))}</button>
          <button class="btn ghost" data-ct="del">${h(t("del"))}</button>
        </div>
      </div>`).join("") || `<p class="muted" style="font-size:12.5px">${h(t("noContacts"))}</p>`;
  }

  async function contactAction(b) {
    const card = b.closest(".sk-ct");
    const email = card?.dataset.email;
    if (!email) return;
    try {
      if (b.dataset.ct === "del") {
        if (!window.confirm(t("delConfirm"))) return;
        await postJSON("/api/skills/crm/delete", { email });
        notify(t("deleted"));
      } else {
        const f = (k) => card.querySelector(`[data-f="${k}"]`)?.value || "";
        await postJSON("/api/skills/crm/update", { email, stage: f("stage"), tags: f("tags"), note: f("note") });
        notify(t("saved"));
      }
      loadContacts();
    } catch (e) { notify(t("failed") + e.message, true); }
  }

  /* quick buttons on the open email */
  async function quick(slug) {
    const sender = selectedSender();
    const args = slug === "slide" ? { email_id: state.selected?.id || "" } : { person: sender, email_id: state.selected?.id || "" };
    const s = skill(slug);
    if (s && !s.enabled) return notify(t("disabledRun"), true);
    view.current = slug;
    try {
      await run(slug, args);
      window.setView("skills");
    } catch {}
  }

  function decorateThread() {
    if (state.view !== "mail" || !state.selected) return;
    const bar = $pane().querySelector(".actionbar");
    if (!bar || bar.querySelector(".sk-quick")) return;
    const box = document.createElement("span");
    box.className = "sk-quick";
    for (const [slug, key] of [["brief-person", "quickBrief"], ["crm-contact", "quickCrm"], ["slide", "quickSlide"]]) {
      const s = skill(slug);
      if (s && !s.enabled) continue;
      const b = document.createElement("button");
      b.className = "btn ghost";
      b.textContent = t(key);
      b.onclick = () => quick(slug);
      box.append(b);
    }
    bar.append(box);
  }
  new MutationObserver(() => decorateThread()).observe($pane(), { childList: true });

  const coreSetView = window.setView;
  if (typeof coreSetView === "function") {
    window.setView = (v, ...rest) => {
      const out = coreSetView(v, ...rest);
      if (v === "skills") load();
      return out;
    };
  }
  new MutationObserver(() => {
    relabel();
    if (state.view === "skills") { view.result = null; load(); }
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

  getJSON("/api/skills?lang=" + langParam()).then((d) => { view.skills = d.skills || []; view.stages = d.stages || []; }).catch(() => {});
  if (new URLSearchParams(location.hash.slice(1)).get("view") === "skills") window.setView("skills");
})();
