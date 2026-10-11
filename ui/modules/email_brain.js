/* Email Brain tab: identity & workplace, writing tone, contacts & relationships,
   active projects, work patterns — all inferred from local mail (GET /api/brain/profile).
   Every item has a Fix button (POST /api/brain/fix, reset: /api/brain/fix/reset);
   a fix is saved locally and immediately feeds the persona and the AI draft prompt
   (preview: GET /api/brain/prompt). */
(() => {
  "use strict";
  const S = {
    zh: {
      nav: "🧠 信件大腦", title: "Email Brain · 信件大腦",
      intro: "從你的信件推得：你是誰、怎麼寫信、跟誰往來、手上有哪些專案、什麼時候在工作。推錯了就按「修正」，存在本機並立即套用到 persona 與 AI 草稿。",
      sources: "依據", received: "封收信", sent: "封寄件", demoSent: "（示範寄件備份）", fixesN: "項修正",
      fix: "修正", save: "儲存修正", cancel: "取消", reset: "還原推論", resetAll: "全部還原",
      resetAllAsk: "把所有修正還原成從信件推得的結果？", inferred: "原本推得", note: "備註（選填）",
      evidence: "依據的信", hide: "從清單隱藏", hidden: "已隱藏", unhide: "重新顯示", empty: "（無）",
      name: "名稱", email: "信箱位址", relationship: "關係", customRel: "或自訂關係", status: "狀態",
      threads: "信件串", people: "相關的人", events: "行事曆", last: "最近往來", sentN: "寄出", receivedN: "收到",
      addContact: "＋新增聯絡人", addProject: "＋新增專案", add: "新增", openMail: "開信",
      learned: "從你改 AI 草稿學到的語氣", promptTitle: "這些會怎麼影響 AI 草稿", promptHint: "每次 AI 起草都會帶上這段（✎ 撰寫 → AI 起草）。",
      saved: "已修正", resetDone: "已還原", failed: "操作失敗：", hoursHint: "例如 09:00-18:00",
      rulesHint: "一行一條，例如：不要用驚嘆號", fixedTag: "已修正", noData: "信件還不夠，先按「同步」。",
      days: "工作日",
    },
    en: {
      nav: "🧠 Email Brain", title: "Email Brain",
      intro: "What your mail says about you: who you are, how you write, who you work with, what you are working on and when. If something is wrong, hit Fix: it is saved locally and applies to the persona and AI drafts right away.",
      sources: "Based on", received: "received", sent: "sent", demoSent: " (demo sent mail)", fixesN: "fixes",
      fix: "Fix", save: "Save fix", cancel: "Cancel", reset: "Reset to inferred", resetAll: "Reset all",
      resetAllAsk: "Reset every fix back to what your mail says?", inferred: "Inferred", note: "Note (optional)",
      evidence: "Evidence", hide: "Hide from the list", hidden: "Hidden", unhide: "Show again", empty: "(none)",
      name: "Name", email: "Email address", relationship: "Relationship", customRel: "or a custom one", status: "Status",
      threads: "Threads", people: "People", events: "Calendar", last: "Last contact", sentN: "sent", receivedN: "received",
      addContact: "+ Add contact", addProject: "+ Add project", add: "Add", openMail: "Open",
      learned: "Voice learned from your edits to AI drafts", promptTitle: "How this shapes AI drafts", promptHint: "Every AI draft carries this block (✎ Compose → AI draft).",
      saved: "Fixed", resetDone: "Reset", failed: "Failed: ", hoursHint: "e.g. 09:00-18:00",
      rulesHint: "One per line, e.g. Never use exclamation marks", fixedTag: "fixed", noData: "Not enough mail yet: hit Sync first.",
      days: "Work days",
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
  if (!nav || typeof state !== "object" || window.__tpiEmailBrain) return;
  window.__tpiEmailBrain = true;

  const css = document.createElement("style");
  css.textContent = `
    .eb-sec { margin: 18px 0 8px; font-size: 13.5px; color: var(--accent2); border-bottom: 1px dashed #3a332a; padding-bottom: 4px; display: flex; gap: 8px; align-items: baseline; }
    .eb-sec .d { color: var(--muted); font-size: 11.5px; }
    .eb-item { border: 1px solid var(--line); border-radius: 10px; padding: 9px 12px; margin: 8px 0; background: var(--panel); }
    .eb-item.fixed { border-color: #5a4b31; box-shadow: inset 3px 0 0 var(--accent); }
    .eb-item.hid { opacity: .55; }
    .eb-item.flash { animation: ebflash 1.2s ease; }
    @keyframes ebflash { 0% { background: #3a311f; } 100% { background: var(--panel); } }
    .eb-top { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
    .eb-label { color: var(--muted); font-size: 12px; min-width: 92px; }
    .eb-val { font-size: 14px; white-space: pre-wrap; word-break: break-word; flex: 1; min-width: 120px; }
    .eb-src { font-size: 10px; border: 1px solid var(--line); border-radius: 999px; padding: 0 6px; color: var(--muted); white-space: nowrap; }
    .eb-src.fix { color: var(--accent); border-color: #6b5a3a; }
    .eb-item .btn { font-size: 11.5px; padding: 3px 9px; }
    .eb-basis { color: var(--muted); font-size: 11.5px; margin-top: 4px; }
    .eb-ev { color: var(--muted); font-size: 11.5px; margin-top: 2px; }
    .eb-was { color: var(--muted); font-size: 11.5px; margin-top: 3px; }
    .eb-edit { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--line); }
    .eb-edit input, .eb-edit select, .eb-edit textarea { background: #171410; border: 1px solid var(--line); border-radius: 7px; padding: 6px 9px; outline: none; }
    .eb-edit textarea { min-height: 64px; resize: vertical; }
    .eb-edit .acts { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
    .eb-days { display: flex; gap: 8px; flex-wrap: wrap; font-size: 12.5px; }
    .eb-pill { font-size: 11px; border: 1px solid var(--line); border-radius: 999px; padding: 0 7px; color: var(--accent2); }
    .eb-meta { color: var(--muted); font-size: 11.5px; }
    .eb-chips { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
    .eb-chips .btn { font-size: 11px; padding: 2px 8px; }
    .eb-prompt { white-space: pre-wrap; font-size: 12px; background: #120f0c; border: 1px solid var(--line); border-radius: 8px; padding: 10px; margin-top: 6px; }
    .eb-banner { font-size: 12px; padding: 7px 10px; border-radius: 8px; border: 1px dashed #4a4136; color: var(--accent2); margin: 8px 0; }
    details.eb-det summary { cursor: pointer; color: var(--accent2); font-size: 13px; margin-top: 16px; }`;
  document.head.appendChild(css);

  const navBtn = document.createElement("button");
  navBtn.dataset.view = "ebrain";
  const navLabel = document.createElement("span");
  const navCnt = document.createElement("span");
  navCnt.className = "cnt";
  navBtn.append(navLabel, navCnt);
  const anchor = nav.querySelector('[data-view="brain2"]');
  nav.insertBefore(navBtn, anchor ? anchor.nextSibling : null);
  const relabel = () => { navLabel.textContent = t("nav"); };
  relabel();

  const view = { data: null, editing: "", prompt: "", flash: "" };
  const $list = () => document.getElementById("list");
  const $pane = () => document.getElementById("pane");
  const itemId = (sec, key) => `${sec}::${key}`;
  const section = (id) => (view.data?.sections || []).find((s) => s.id === id);

  async function load(keepScroll) {
    const top = $pane().scrollTop;
    if (!view.data) $pane().innerHTML = "<p class='muted'>…</p>";
    try {
      const [profile, prompt] = await Promise.all([
        getJSON("/api/brain/profile?lang=" + langParam()),
        getJSON("/api/brain/prompt?lang=" + langParam()),
      ]);
      if (profile.error) throw new Error(profile.error);
      view.data = profile;
      view.prompt = prompt.text || "";
    } catch (e) {
      $pane().innerHTML = `<p class='muted'>${h(t("failed") + e.message)}</p>`;
      return;
    }
    if (state.view !== "ebrain") return;
    render();
    if (keepScroll) $pane().scrollTop = top;
  }

  function render() {
    renderList();
    renderPane();
  }

  function renderList() {
    const d = view.data;
    navCnt.textContent = d.fixes ? String(d.fixes) : "";
    $list().innerHTML = d.sections.map((s) => `
      <div class="row" data-sec="${h(s.id)}">
        <div class="dot worth_a_look"></div>
        <div><div class="rowline"><span class="from">${h(s.name)}</span></div>
        <div class="subj">${h(s.description)}</div></div>
        <div class="meta">${s.count}${s.fixed ? `<br><span class="eb-pill">${s.fixed} ${h(t("fixedTag"))}</span>` : ""}</div>
      </div>`).join("");
    $list().onclick = (ev) => {
      const row = ev.target.closest("[data-sec]");
      if (!row) return;
      $list().querySelectorAll(".row").forEach((r) => r.classList.toggle("on", r === row));
      const el = $pane().querySelector(`[data-anchor="${CSS.escape(row.dataset.sec)}"]`);
      if (el) el.scrollIntoView({ block: "start", behavior: "smooth" });
    };
  }

  function srcTag(it) {
    return `<span class="eb-src ${it.fixed ? "fix" : ""}">${h(it.source_label || "")}</span>`;
  }

  function scalarItem(it) {
    const id = itemId(it.section, it.key);
    const editing = view.editing === id;
    const was = it.fixed && it.inferred_display !== null && it.inferred_display !== undefined
      ? `<div class="eb-was">${h(t("inferred"))}：${h(it.inferred_display || t("empty"))}</div>` : "";
    return `<div class="eb-item ${it.fixed ? "fixed" : ""} ${view.flash === id ? "flash" : ""}" data-item="${h(id)}">
      <div class="eb-top"><span class="eb-label">${h(it.label)}</span>
        <span class="eb-val">${h(it.display || t("empty"))}</span>${srcTag(it)}
        <button class="btn" data-fix="${h(id)}">${h(t("fix"))}</button>
        ${it.fixed ? `<button class="btn ghost" data-reset="${h(id)}">${h(t("reset"))}</button>` : ""}</div>
      ${it.basis ? `<div class="eb-basis">${h(it.basis)}</div>` : ""}
      ${(it.evidence || []).length ? `<div class="eb-ev">${h(t("evidence"))}：${it.evidence.map(h).join(" · ")}</div>` : ""}
      ${it.note ? `<div class="eb-ev">📝 ${h(it.note)}</div>` : ""}${was}
      ${editing ? scalarEditor(it) : ""}</div>`;
  }

  function scalarEditor(it) {
    let input;
    if (it.kind === "enum") {
      input = `<select data-in="value">${(it.options || []).map((o) => `<option value="${h(o.id)}" ${o.id === it.value ? "selected" : ""}>${h(o.label)}</option>`).join("")}</select>`;
    } else if (it.kind === "days") {
      const cur = new Set(Array.isArray(it.value) ? it.value : []);
      input = `<div class="eb-days">${(view.data.days || []).map((d) => `<label><input type="checkbox" data-day="${h(d.id)}" ${cur.has(d.id) ? "checked" : ""}/> ${h(d.label)}</label>`).join("")}</div>`;
    } else if (it.kind === "hours") {
      input = `<input data-in="value" value="${h(it.display || "")}" placeholder="${h(t("hoursHint"))}" />`;
    } else if (it.kind === "multiline") {
      input = `<textarea data-in="value" placeholder="${h(it.key === "rules" ? t("rulesHint") : "")}">${h(typeof it.value === "string" ? it.value : it.display || "")}</textarea>`;
    } else {
      input = `<input data-in="value" value="${h(typeof it.value === "string" ? it.value : it.display || "")}" />`;
    }
    return `<div class="eb-edit">${input}
      <input data-in="note" value="${h(it.note || "")}" placeholder="${h(t("note"))}" />
      <div class="acts"><button class="btn primary" data-save="${h(itemId(it.section, it.key))}">${h(t("save"))}</button>
      <button class="btn ghost" data-cancel="1">${h(t("cancel"))}</button></div></div>`;
  }

  function relOptions(cur) {
    const rels = view.data.relationships || [];
    const known = rels.some((r) => r.id === cur);
    return `<select data-in="relationship">${rels.map((r) => `<option value="${h(r.id)}" ${r.id === cur ? "selected" : ""}>${h(r.label)}</option>`).join("")}</select>
      <input data-in="relationship_custom" value="${h(known ? "" : cur || "")}" placeholder="${h(t("customRel"))}" />`;
  }

  function contactItem(c) {
    const id = itemId("contacts", c.key);
    const editing = view.editing === id;
    return `<div class="eb-item ${c.fixed ? "fixed" : ""} ${c.hidden ? "hid" : ""} ${view.flash === id ? "flash" : ""}" data-item="${h(id)}">
      <div class="eb-top"><span class="eb-val"><strong>${h(c.name)}</strong> <span class="eb-meta">&lt;${h(c.email)}&gt;</span></span>
        <span class="eb-pill">${h(c.relationship_label)}</span>${c.hidden ? `<span class="eb-src">${h(t("hidden"))}</span>` : ""}${srcTag(c)}
        <button class="btn" data-fix="${h(id)}">${h(t("fix"))}</button>
        ${c.hidden ? `<button class="btn ghost" data-unhide="${h(id)}">${h(t("unhide"))}</button>` : ""}${c.fixed ? `<button class="btn ghost" data-reset="${h(id)}">${h(t("reset"))}</button>` : ""}</div>
      <div class="eb-meta">${h(c.direction_label || "")}${c.sent || c.received ? ` · ${h(t("sentN"))} ${c.sent} · ${h(t("receivedN"))} ${c.received}` : ""}${c.last ? ` · ${h(t("last"))} ${h(String(c.last).replace("T", " ").slice(0, 16))}` : ""}</div>
      ${c.basis ? `<div class="eb-basis">${h(c.basis)}</div>` : ""}
      ${(c.evidence || []).length ? `<div class="eb-ev">${h(t("evidence"))}：${c.evidence.map(h).join(" · ")}</div>` : ""}
      ${c.note ? `<div class="eb-ev">📝 ${h(c.note)}</div>` : ""}
      ${c.fixed && c.inferred_relationship && c.inferred_relationship !== c.relationship ? `<div class="eb-was">${h(t("inferred"))}：${h(relLabel(c.inferred_relationship))}</div>` : ""}
      ${editing ? `<div class="eb-edit">
        <input data-in="name" value="${h(c.name)}" placeholder="${h(t("name"))}" />
        ${relOptions(c.relationship)}
        <input data-in="note" value="${h(c.note || "")}" placeholder="${h(t("note"))}" />
        <label class="eb-meta"><input type="checkbox" data-in="hidden" ${c.hidden ? "checked" : ""}/> ${h(t("hide"))}</label>
        <div class="acts"><button class="btn primary" data-save="${h(id)}">${h(t("save"))}</button><button class="btn ghost" data-cancel="1">${h(t("cancel"))}</button></div></div>` : ""}
    </div>`;
  }

  function relLabel(id) {
    return (view.data.relationships || []).find((r) => r.id === id)?.label || id;
  }

  function projectItem(p) {
    const id = itemId("projects", p.key);
    const editing = view.editing === id;
    const statuses = view.data.project_statuses || [];
    return `<div class="eb-item ${p.fixed ? "fixed" : ""} ${p.hidden ? "hid" : ""} ${view.flash === id ? "flash" : ""}" data-item="${h(id)}">
      <div class="eb-top"><span class="eb-val"><strong>${h(p.name)}</strong></span>
        <span class="eb-pill">${h(p.status_label)}</span>${p.hidden ? `<span class="eb-src">${h(t("hidden"))}</span>` : ""}${srcTag(p)}
        <button class="btn" data-fix="${h(id)}">${h(t("fix"))}</button>
        ${p.hidden ? `<button class="btn ghost" data-unhide="${h(id)}">${h(t("unhide"))}</button>` : ""}${p.fixed ? `<button class="btn ghost" data-reset="${h(id)}">${h(t("reset"))}</button>` : ""}</div>
      ${p.basis ? `<div class="eb-basis">${h(p.basis)}</div>` : ""}
      ${(p.keywords || []).length ? `<div class="eb-meta">${p.keywords.map(h).join(" · ")}</div>` : ""}
      ${(p.people || []).length ? `<div class="eb-meta">${h(t("people"))}：${p.people.map(h).join("、")}</div>` : ""}
      ${(p.events || []).length ? `<div class="eb-meta">🗓 ${p.events.map((e) => `${h(e.title)} · ${h(String(e.start || "").replace("T", " ").slice(0, 16))}`).join("；")}</div>` : ""}
      ${(p.threads || []).length ? `<div class="eb-chips">${p.threads.map((x) => x.in_inbox
        ? `<button class="btn ghost" data-mail="${h(x.id)}">✉ ${h(x.subject || "—")}</button>`
        : `<span class="eb-meta">↗ ${h(x.subject || "—")}</span>`).join("")}</div>` : ""}
      ${p.note ? `<div class="eb-ev">📝 ${h(p.note)}</div>` : ""}
      ${p.fixed && p.inferred_name && p.inferred_name !== p.name ? `<div class="eb-was">${h(t("inferred"))}：${h(p.inferred_name)}</div>` : ""}
      ${editing ? `<div class="eb-edit">
        <input data-in="name" value="${h(p.name)}" placeholder="${h(t("name"))}" />
        <select data-in="status">${statuses.map((s) => `<option value="${h(s.id)}" ${s.id === p.status ? "selected" : ""}>${h(s.label)}</option>`).join("")}</select>
        <input data-in="note" value="${h(p.note || "")}" placeholder="${h(t("note"))}" />
        <label class="eb-meta"><input type="checkbox" data-in="hidden" ${p.hidden ? "checked" : ""}/> ${h(t("hide"))}</label>
        <div class="acts"><button class="btn primary" data-save="${h(id)}">${h(t("save"))}</button><button class="btn ghost" data-cancel="1">${h(t("cancel"))}</button></div></div>` : ""}
    </div>`;
  }

  function addForms(sid) {
    const id = itemId(sid, "__new__");
    if (view.editing !== id) return `<p><button class="btn ghost" data-fix="${h(id)}">${h(sid === "contacts" ? t("addContact") : t("addProject"))}</button></p>`;
    if (sid === "contacts") {
      return `<div class="eb-item" data-item="${h(id)}"><div class="eb-edit">
        <input data-in="email" placeholder="${h(t("email"))}" /><input data-in="name" placeholder="${h(t("name"))}" />
        ${relOptions("other")}<input data-in="note" placeholder="${h(t("note"))}" />
        <div class="acts"><button class="btn primary" data-save="${h(id)}">${h(t("add"))}</button><button class="btn ghost" data-cancel="1">${h(t("cancel"))}</button></div></div></div>`;
    }
    return `<div class="eb-item" data-item="${h(id)}"><div class="eb-edit">
      <input data-in="name" placeholder="${h(t("name"))}" /><input data-in="note" placeholder="${h(t("note"))}" />
      <div class="acts"><button class="btn primary" data-save="${h(id)}">${h(t("add"))}</button><button class="btn ghost" data-cancel="1">${h(t("cancel"))}</button></div></div></div>`;
  }

  function renderPane() {
    const d = view.data;
    const src = d.sources || {};
    let html = `<h2 class="mh">${h(t("title"))}</h2>
      <p class="muted" style="margin:0 0 6px;font-size:13px">${h(t("intro"))}</p>
      <div class="eb-banner">${h(t("sources"))}：${src.received} ${h(t("received"))} · ${src.sent} ${h(t("sent"))}${src.demo_sent ? h(t("demoSent")) : ""} · ${d.fixes} ${h(t("fixesN"))}
        ${d.fixes ? ` <button class="btn ghost" data-resetall="1" style="font-size:11px;padding:2px 8px">${h(t("resetAll"))}</button>` : ""}</div>
      ${!src.sent && !src.received ? `<p class="muted">${h(t("noData"))}</p>` : ""}`;
    for (const s of d.sections) {
      html += `<div class="eb-sec" data-anchor="${h(s.id)}"><b>${h(s.name)}</b><span class="d">${h(s.description)}</span></div>`;
      if (s.id === "contacts") html += s.items.map(contactItem).join("") + addForms("contacts");
      else if (s.id === "projects") html += s.items.map(projectItem).join("") + addForms("projects");
      else html += s.items.map(scalarItem).join("");
      if (s.id === "tone" && (d.learned_voice || []).length) {
        html += `<div class="eb-item"><div class="eb-label">${h(t("learned"))}</div>${d.learned_voice.map((x) => `<div class="eb-ev">· ${h(x)}</div>`).join("")}</div>`;
      }
    }
    html += `<details class="eb-det" ${view.promptOpen ? "open" : ""}><summary>✎ ${h(t("promptTitle"))}</summary>
      <div class="eb-meta" style="margin-top:4px">${h(t("promptHint"))}</div><pre class="eb-prompt">${h(view.prompt)}</pre></details>
      <p class="hint">${h(d.note)}</p>`;
    $pane().innerHTML = html;
    const det = $pane().querySelector("details.eb-det");
    if (det) det.ontoggle = () => { view.promptOpen = det.open; };
    $pane().onclick = onClick;
    if (view.editing) {
      const box = $pane().querySelector(`[data-item="${CSS.escape(view.editing)}"] [data-in]`);
      if (box) box.focus();
    }
    view.flash = "";
  }

  function findItem(id) {
    const [sid, key] = id.split("::");
    return { sid, key, it: (section(sid)?.items || []).find((x) => x.key === key) };
  }

  function collect(id) {
    const box = $pane().querySelector(`[data-item="${CSS.escape(id)}"]`);
    const val = (name) => box?.querySelector(`[data-in="${name}"]`);
    const { sid, key, it } = findItem(id);
    const isNew = key === "__new__";
    const body = { section: sid };
    if (sid === "contacts") {
      body.key = isNew ? (val("email")?.value || "").trim() : key;
      body.name = (val("name")?.value || "").trim();
      const custom = (val("relationship_custom")?.value || "").trim();
      body.relationship = custom || val("relationship")?.value || "other";
      body.note = (val("note")?.value || "").trim();
      if (!isNew) body.hidden = !!val("hidden")?.checked;
    } else if (sid === "projects") {
      if (!isNew) body.key = key;
      body.name = (val("name")?.value || "").trim();
      body.note = (val("note")?.value || "").trim();
      if (!isNew) { body.status = val("status")?.value || "active"; body.hidden = !!val("hidden")?.checked; }
    } else {
      body.key = key;
      body.value = it?.kind === "days"
        ? [...box.querySelectorAll("[data-day]")].filter((x) => x.checked).map((x) => x.dataset.day)
        : (val("value")?.value ?? "");
      body.note = (val("note")?.value || "").trim();
    }
    return body;
  }

  async function onClick(ev) {
    const b = ev.target.closest("button");
    if (!b) return;
    try {
      if (b.dataset.fix) { view.editing = view.editing === b.dataset.fix ? "" : b.dataset.fix; renderPane(); }
      else if (b.dataset.cancel) { view.editing = ""; renderPane(); }
      else if (b.dataset.save) {
        b.disabled = true;
        const r = await postJSON("/api/brain/fix", collect(b.dataset.save));
        view.editing = "";
        view.flash = itemId(r.section, r.key);
        view.data = r.profile;
        view.prompt = r.prompt || view.prompt;
        notify(`${t("saved")} · ${r.note}`);
        const top = $pane().scrollTop;
        render();
        $pane().scrollTop = top;
      } else if (b.dataset.unhide) {
        const { sid, key } = findItem(b.dataset.unhide);
        const r = await postJSON("/api/brain/fix", { section: sid, key, hidden: false });
        view.data = r.profile; view.prompt = r.prompt || view.prompt; view.flash = b.dataset.unhide;
        notify(`${t("saved")} · ${r.note}`);
        const top = $pane().scrollTop;
        render();
        $pane().scrollTop = top;
      } else if (b.dataset.reset) {
        const { sid, key } = findItem(b.dataset.reset);
        const r = await postJSON("/api/brain/fix/reset", { section: sid, key });
        view.data = r.profile; view.prompt = r.prompt || view.prompt; view.flash = b.dataset.reset;
        notify(t("resetDone"));
        const top = $pane().scrollTop;
        render();
        $pane().scrollTop = top;
      } else if (b.dataset.resetall) {
        if (!confirm(t("resetAllAsk"))) return;
        const r = await postJSON("/api/brain/fix/reset", { all: true });
        view.data = r.profile; view.prompt = r.prompt || view.prompt;
        notify(t("resetDone"));
        render();
      } else if (b.dataset.mail && typeof openThread === "function") {
        openThread(b.dataset.mail);
      }
    } catch (e) {
      b.disabled = false;
      notify(t("failed") + e.message, true);
    }
  }

  const coreSetView = window.setView;
  if (typeof coreSetView === "function") {
    window.setView = (v, ...rest) => {
      const out = coreSetView(v, ...rest);
      if (v === "ebrain") { view.editing = ""; load(); }
      return out;
    };
  }

  new MutationObserver(() => {
    relabel();
    if (state.view === "ebrain") { view.editing = ""; load(true); }
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

  getJSON("/api/brain/fixes").then((d) => { navCnt.textContent = (d.fixes || []).length || ""; }).catch(() => {});
  if (new URLSearchParams(location.hash.slice(1)).get("view") === "ebrain") window.setView("ebrain");
})();
