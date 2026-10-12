/* Schedule Send + Undo Send + confirm before release (/api/outbox/*).
   The composer gets "Send…" and "Schedule…": the draft is saved, previewed (POST /api/outbox/prepare) and only
   queued after the user ticks the confirmation (POST /api/outbox/confirm). "Now" opens an Undo Send countdown;
   when it ends (or a scheduled time comes) the server writes data/outbox/*.eml, marked as awaiting the user to
   send it themselves. There is no delivery transport. Sidebar: Scheduled folder (change time / edit / cancel,
   agent proposals waiting for you) and Outbox (download .eml, mark as sent by you, move back to Drafts). */
(() => {
  "use strict";
  const S = {
    zh: {
      navScheduled: "⏰ 已排程", navOutbox: "📤 寄件匣",
      sendBtn: "寄出…", scheduleBtn: "⏰ 排程…",
      confirmTitle: "寄出前確認", proposedBy: "由 agent 提議，需要你確認",
      noTransport: "TooPowerInbox 不會真的寄信：確認後只把信寫成 .eml 放進本機寄件匣，待你自行寄出。",
      from: "寄件帳號", to: "收件者", cc: "副本", bcc: "密件副本", subject: "主旨", body: "內文", noSubject: "（無主旨）",
      modeNow: "立即（{n} 秒內可撤回）", modeSchedule: "排程於", tz: "時區",
      ack: "我已確認收件者與內容", confirmNow: "確認，排入寄件匣", confirmSchedule: "確認排程", cancel: "取消",
      blocked: "需要先修正才能確認：", warn: "提醒", editInComposer: "回撰寫器修改",
      needAck: "請先勾選「我已確認收件者與內容」", needTime: "請選排程時間",
      undoBar: "已排入寄件匣 · {n} 秒後寫成 .eml", undo: "撤回", undone: "已撤回，信回到草稿匣",
      released: "已寫成 {f}，待你自行寄出", releasedScheduled: "排程的信已寫成 .eml，待你自行寄出",
      scheduledTitle: "已排程", scheduledHint: "到了排程時間只會寫成 .eml，不會寄出。可以改時間、編輯（放回草稿）或取消。",
      awaitingTitle: "待你確認", awaitingHint: "agent 或你先前開過但沒確認的信；不確認就永遠不會進寄件匣。",
      emptyScheduled: "沒有排程中的信。在撰寫器按「⏰ 排程…」。",
      outboxTitle: "寄件匣（待自行寄出）", outboxHint: "這些信已寫成 .eml，但沒有寄出：下載後用你的郵件程式開啟並自行寄出。",
      emptyOutbox: "寄件匣是空的。",
      historyTitle: "已處理", at: "時間", releaseAt: "排程時間", writtenAt: "寫出時間", file: "檔案",
      changeTime: "變更時間", apply: "套用", releaseNow: "立即寫成 .eml", edit: "編輯", cancelSchedule: "取消排程",
      review: "檢視並確認", discard: "捨棄", download: "下載 .eml", copyPath: "複製路徑", markDone: "標記為我已自行寄出",
      backToDrafts: "移回草稿", copied: "已複製", failed: "操作失敗：",
      editNote: "已放回草稿匣：改完再按「⏰ 排程…」重新排程（原時間 {t}）",
      confirmCancel: "取消排程並把信放回草稿匣？", confirmBack: "刪除 .eml 並把信放回草稿匣？",
      settingsTitle: "寄件設定", undoSeconds: "Undo Send 撤回秒數", transport: "寄信傳輸", alwaysConfirm: "寄出前一律人工確認",
      locked: "固定開啟", folder: "寄件匣資料夾", seconds: "秒", settingsSaved: "寄件設定已儲存",
      byAgent: "agent", byUser: "你", select: "點左側一封信看詳情。", composerMissing: "找不到撰寫器模組",
    },
    en: {
      navScheduled: "⏰ Scheduled", navOutbox: "📤 Outbox",
      sendBtn: "Send…", scheduleBtn: "⏰ Schedule…",
      confirmTitle: "Confirm before release", proposedBy: "Proposed by an agent; needs your confirmation",
      noTransport: "TooPowerInbox never sends mail: once confirmed, the message is only written as an .eml in the local outbox, waiting for you to send it yourself.",
      from: "From", to: "To", cc: "Cc", bcc: "Bcc", subject: "Subject", body: "Body", noSubject: "(no subject)",
      modeNow: "Now (undo within {n} s)", modeSchedule: "Schedule for", tz: "Time zone",
      ack: "I checked the recipients and content", confirmNow: "Confirm and queue", confirmSchedule: "Confirm schedule", cancel: "Cancel",
      blocked: "Fix this before confirming: ", warn: "Heads-up", editInComposer: "Back to the composer",
      needAck: "Tick 'I checked the recipients and content' first", needTime: "Pick a schedule time",
      undoBar: "Queued · written as .eml in {n} s", undo: "Undo", undone: "Undone: the message is back in Drafts",
      released: "Written as {f}; waiting for you to send it yourself", releasedScheduled: "A scheduled message was written as .eml for you to send yourself",
      scheduledTitle: "Scheduled", scheduledHint: "When the time comes it is only written as an .eml, never sent. Change the time, edit (back to Drafts) or cancel.",
      awaitingTitle: "Needs your confirmation", awaitingHint: "Proposed by an agent, or opened by you and not confirmed; without your confirmation it never reaches the outbox.",
      emptyScheduled: "Nothing scheduled. Use '⏰ Schedule…' in the composer.",
      outboxTitle: "Outbox (send it yourself)", outboxHint: "These are written as .eml files but not sent: download one, open it in your mail app and send it yourself.",
      emptyOutbox: "The outbox is empty.",
      historyTitle: "Handled", at: "Time", releaseAt: "Scheduled for", writtenAt: "Written", file: "File",
      changeTime: "Change time", apply: "Apply", releaseNow: "Write .eml now", edit: "Edit", cancelSchedule: "Cancel schedule",
      review: "Review and confirm", discard: "Discard", download: "Download .eml", copyPath: "Copy path", markDone: "Mark as sent by me",
      backToDrafts: "Move back to Drafts", copied: "Copied", failed: "Failed: ",
      editNote: "Back in Drafts: edit it, then use '⏰ Schedule…' again (was {t})",
      confirmCancel: "Cancel the schedule and move the message back to Drafts?", confirmBack: "Delete the .eml and move the message back to Drafts?",
      settingsTitle: "Outbox settings", undoSeconds: "Undo Send window", transport: "Delivery transport", alwaysConfirm: "Always confirm before release",
      locked: "always on", folder: "Outbox folder", seconds: "s", settingsSaved: "Outbox settings saved",
      byAgent: "agent", byUser: "you", select: "Pick a message on the left to see it.", composerMissing: "The composer module is missing",
    },
  };
  const isZh = () => document.documentElement.lang.startsWith("zh");
  const t = (k) => S[isZh() ? "zh" : "en"][k];
  const langParam = () => (isZh() ? "zh-Hant" : "en");
  const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const notify = (msg, isErr) => (typeof toast === "function" ? toast(msg, isErr) : console.log(msg));
  const getJSON = async (path) => {
    const r = await fetch(path + (path.includes("?") ? "&" : "?") + "lang=" + langParam());
    const d = await r.json();
    if (!r.ok || d.error) throw new Error(d.error || String(r.status));
    return d;
  };
  const postJSON = async (path, body) => {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: langParam(), ...body }) });
    const d = await r.json();
    if (!r.ok || d.error) {
      const err = new Error(d.error || String(r.status));
      err.data = d;
      throw err;
    }
    return d;
  };
  const when = (iso) => String(iso || "").replace("T", " ").slice(0, 16);
  const localInput = (iso) => String(iso || "").slice(0, 16);

  const nav = document.getElementById("nav");
  if (!nav || typeof state !== "object" || window.__tpiOutbox) return;
  window.__tpiOutbox = true;

  const css = document.createElement("style");
  css.textContent = `
    .ob-back { position: fixed; inset: 0; background: rgba(10,8,6,.66); display: none; align-items: center; justify-content: center; z-index: 70; }
    .ob-back.open { display: flex; }
    .ob-dlg { width: min(720px, 94vw); max-height: 92vh; display: flex; flex-direction: column; background: var(--panel); border: 1px solid #3a332a; border-radius: 14px; box-shadow: var(--shadow); }
    .ob-head { display: flex; gap: 10px; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--line); }
    .ob-head b { font-size: 15px; }
    .ob-head .x { margin-left: auto; background: transparent; border: none; color: var(--muted); font-size: 17px; }
    .ob-main { padding: 12px 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
    .ob-note { font-size: 12px; color: var(--accent2); border: 1px dashed #4a4136; border-radius: 8px; padding: 7px 10px; }
    .ob-kv { display: grid; grid-template-columns: 92px 1fr; gap: 4px 10px; font-size: 13px; }
    .ob-kv span { color: var(--muted); font-size: 12.5px; }
    .ob-kv div { word-break: break-word; }
    .ob-body { white-space: pre-wrap; font-size: 13px; line-height: 1.7; background: #171410; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; max-height: 260px; overflow: auto; margin: 0; }
    .ob-block { font-size: 12.5px; color: var(--bad); }
    .ob-warn { font-size: 12.5px; color: var(--need); }
    .ob-mode { display: flex; flex-direction: column; gap: 6px; font-size: 13px; border-top: 1px solid var(--line); padding-top: 8px; }
    .ob-mode label { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .ob-mode input[type=datetime-local], .ob-pane input[type=datetime-local], .ob-pane select { background: #171410; border: 1px solid var(--line); border-radius: 8px; padding: 5px 8px; color: var(--ink); }
    .ob-picks { display: flex; gap: 6px; flex-wrap: wrap; padding-left: 26px; }
    .ob-picks .btn, .ob-pane .ob-picks .btn { font-size: 11.5px; padding: 3px 9px; }
    .ob-ack { font-size: 13px; display: flex; gap: 8px; align-items: center; margin-top: 4px; }
    .ob-foot { display: flex; gap: 8px; align-items: center; justify-content: flex-end; padding: 10px 16px 14px; border-top: 1px solid var(--line); }
    .ob-foot .btn[disabled] { opacity: .45; cursor: not-allowed; }
    .ob-badge { font-size: 10.5px; border: 1px solid var(--line); border-radius: 999px; padding: 0 7px; color: var(--accent2); white-space: nowrap; }
    .ob-badge.agent { color: var(--need); border-color: #6b4a3a; }
    .ob-badge.ready { color: var(--ok); border-color: #48603f; }
    #obUndoBar { position: fixed; left: 50%; transform: translateX(-50%); bottom: 18px; display: flex; flex-direction: column; gap: 8px; z-index: 85; }
    .ob-undo { display: flex; gap: 12px; align-items: center; background: #242019; border: 1px solid #3a332a; border-left: 3px solid var(--accent); border-radius: 9px; padding: 9px 14px; font-size: 13px; box-shadow: var(--shadow); }
    .ob-undo .btn { font-size: 12.5px; padding: 4px 12px; }
    .ob-undo .bar { height: 3px; background: var(--accent); border-radius: 2px; transition: width .25s linear; }
    .ob-pane h4 { margin: 18px 0 6px; font-size: 13.5px; color: var(--accent2); border-bottom: 1px dashed #3a332a; padding-bottom: 4px; }
    .ob-pane .row-set { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; font-size: 13px; margin: 6px 0; }
    .ob-pane code { font-size: 12px; word-break: break-all; }
    .ob-sec { padding: 8px 14px 4px; font-size: 11.5px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
    .row.ob-dim { opacity: .55; }`;
  document.head.appendChild(css);

  /* ── sidebar ── */
  const mkNav = (view) => {
    const b = document.createElement("button");
    b.dataset.view = view;
    const label = document.createElement("span");
    const cnt = document.createElement("span");
    cnt.className = "cnt";
    b.append(label, cnt);
    return { b, label, cnt };
  };
  const navScheduled = mkNav("scheduled");
  const navOutbox = mkNav("outbox");
  const anchor = nav.querySelector('[data-view="drafts"]');
  nav.insertBefore(navScheduled.b, anchor ? anchor.nextSibling : null);
  nav.insertBefore(navOutbox.b, navScheduled.b.nextSibling);
  const relabel = () => {
    navScheduled.label.textContent = t("navScheduled");
    navOutbox.label.textContent = t("navOutbox");
  };
  relabel();

  const ob = { settings: null, summary: null, lastReady: null, selected: null, items: [], undo: new Map(),
    undoReleased: new Set(), pendingSendAt: {} };

  async function loadSettings() {
    try { ob.settings = await getJSON("/api/outbox/settings"); } catch { ob.settings = ob.settings || null; }
    return ob.settings;
  }
  async function refreshSummary() {
    let s;
    try { s = await getJSON("/api/outbox/summary"); } catch { return null; }
    const c = s.counts || {};
    navScheduled.cnt.textContent = (c.scheduled || 0) + (c.awaiting_confirm || 0) || "";
    navOutbox.cnt.textContent = c.ready || "";
    const fresh = s.last_ready_id;
    if (ob.lastReady !== null && fresh > ob.lastReady && !ob.undoReleased.has(fresh) && !ob.undo.has(fresh)) {
      notify(t("releasedScheduled"));
      if (state.view === "outbox" || state.view === "scheduled") loadView(state.view);
    }
    ob.lastReady = s.last_ready_id;
    ob.summary = s;
    if (typeof refreshCounts === "function") refreshCounts();
    return s;
  }

  /* ── confirm dialog ── */
  const back = document.createElement("div");
  back.className = "ob-back";
  back.id = "obConfirmBack";
  document.body.appendChild(back);
  const dlg = { open: false, item: null, token: "", mode: "now", sendAt: "", ack: false, busy: false, fromComposer: false };

  function renderDialog() {
    const it = dlg.item;
    const s = ob.settings || { undo_seconds: 10, suggestions: [], tz: "" };
    const blocked = (it.blocking || []).length > 0;
    const canConfirm = dlg.ack && !blocked && !dlg.busy && (dlg.mode === "now" || dlg.sendAt);
    back.innerHTML = `
      <div class="ob-dlg" role="dialog" aria-label="${h(t("confirmTitle"))}">
        <div class="ob-head"><b>✉ ${h(t("confirmTitle"))}</b>
          ${it.created_by === "agent" ? `<span class="ob-badge agent">${h(t("proposedBy"))}</span>` : ""}
          <button class="x" data-ob="close" title="${h(t("cancel"))}">✕</button></div>
        <div class="ob-main">
          <div class="ob-note">${h(t("noTransport"))}</div>
          <div class="ob-kv">
            <span>${h(t("from"))}</span><div>${h(it.account)}</div>
            <span>${h(t("to"))}</span><div>${h(it.to)}</div>
            ${it.cc ? `<span>${h(t("cc"))}</span><div>${h(it.cc)}</div>` : ""}
            ${it.bcc ? `<span>${h(t("bcc"))}</span><div>${h(it.bcc)}</div>` : ""}
            <span>${h(t("subject"))}</span><div>${h(it.subject || t("noSubject"))}</div>
          </div>
          <pre class="ob-body" aria-label="${h(t("body"))}">${h(it.body)}</pre>
          ${(it.blocking || []).map((x) => `<div class="ob-block">⛔ ${h(t("blocked"))}${h(x)}</div>`).join("")}
          ${(it.warnings || []).map((x) => `<div class="ob-warn">⚠ ${h(x)}</div>`).join("")}
          <div class="ob-mode">
            <label><input type="radio" name="obMode" value="now" ${dlg.mode === "now" ? "checked" : ""}/> ${h(t("modeNow").replace("{n}", s.undo_seconds))}</label>
            <label><input type="radio" name="obMode" value="schedule" ${dlg.mode === "schedule" ? "checked" : ""}/> ${h(t("modeSchedule"))}
              <input type="datetime-local" id="obSendAt" value="${h(localInput(dlg.sendAt))}" />
              <span class="muted" style="font-size:12px">${h(t("tz"))} ${h(s.tz)}</span></label>
            <div class="ob-picks">${(s.suggestions || []).map((p) => `<button class="btn ghost" data-ob-pick="${h(p.at)}">${h(p.label)} · ${h(when(p.at).slice(5))}</button>`).join("")}</div>
          </div>
          <label class="ob-ack"><input type="checkbox" id="obAck" ${dlg.ack ? "checked" : ""} ${blocked ? "disabled" : ""}/> ${h(t("ack"))}</label>
        </div>
        <div class="ob-foot">
          ${dlg.fromComposer && blocked ? `<button class="btn" data-ob="close">${h(t("editInComposer"))}</button>` : ""}
          <button class="btn ghost" data-ob="close">${h(t("cancel"))}</button>
          <button class="btn primary" data-ob="confirm" ${canConfirm ? "" : "disabled"}>${h(dlg.mode === "now" ? t("confirmNow") : t("confirmSchedule"))}</button>
        </div>
      </div>`;
  }

  function openDialog(item, token, mode, opts = {}) {
    Object.assign(dlg, { open: true, item, token, mode: mode || "now", ack: false, busy: false, fromComposer: !!opts.fromComposer });
    const s = ob.settings || {};
    dlg.sendAt = opts.sendAt || item.proposed_at || (s.suggestions || []).find((p) => p.id === "tomorrow_morning")?.at || "";
    renderDialog();
    back.classList.add("open");
    back.querySelector("#obAck")?.focus();
  }

  async function closeDialog() {
    if (!dlg.open) return;
    const it = dlg.item;
    dlg.open = false;
    back.classList.remove("open");
    back.innerHTML = "";
    if (it && it.state === "awaiting_confirm" && it.created_by !== "agent") {
      try { await postJSON("/api/outbox/discard", { id: it.id }); } catch {}
    }
    refreshSummary();
    if (state.view === "scheduled") loadView("scheduled");
  }

  async function doConfirm() {
    if (dlg.busy) return;
    const body = { id: dlg.item.id, token: dlg.token, ack: dlg.ack === true, mode: dlg.mode };
    if (dlg.mode === "schedule") {
      const v = back.querySelector("#obSendAt")?.value || "";
      if (!v) { notify(t("needTime"), true); return; }
      body.send_at = v;
    }
    if (!dlg.ack) { notify(t("needAck"), true); return; }
    dlg.busy = true;
    renderDialog();
    try {
      const r = await postJSON("/api/outbox/confirm", body);
      dlg.open = false;
      back.classList.remove("open");
      back.innerHTML = "";
      if (dlg.fromComposer && window.tpiComposer) window.tpiComposer.close();
      notify(r.note);
      if (r.item.state === "undo_window") startUndo(r.item);
      if (typeof loadDrafts === "function" && state.view === "drafts") loadDrafts();
      refreshSummary();
      if (state.view === "scheduled" || state.view === "outbox") loadView(state.view);
    } catch (e) {
      dlg.busy = false;
      if (e.data?.blocking) dlg.item.blocking = e.data.blocking;
      renderDialog();
      notify(t("failed") + e.message, true);
    }
  }

  back.addEventListener("click", (ev) => {
    if (ev.target === back) return closeDialog();
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.ob === "close") closeDialog();
    else if (b.dataset.ob === "confirm") doConfirm();
    else if (b.dataset.obPick) { dlg.sendAt = b.dataset.obPick; dlg.mode = "schedule"; renderDialog(); }
  });
  back.addEventListener("change", (ev) => {
    const el = ev.target;
    if (el.name === "obMode") { dlg.mode = el.value; renderDialog(); }
    else if (el.id === "obAck") { dlg.ack = el.checked; renderDialog(); }
    else if (el.id === "obSendAt") { dlg.sendAt = el.value; if (el.value) dlg.mode = "schedule"; renderDialog(); }
  });
  /* window capture runs before the composer's document-level Esc / Ctrl+Enter handlers */
  window.addEventListener("keydown", (ev) => {
    if (!dlg.open) return;
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopImmediatePropagation(); closeDialog(); }
    else if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") { ev.preventDefault(); ev.stopImmediatePropagation(); doConfirm(); }
    else if ((ev.ctrlKey || ev.metaKey) && ev.key === "s") { ev.preventDefault(); ev.stopImmediatePropagation(); }
  }, true);

  async function fromComposer(mode) {
    if (!window.tpiComposer) { notify(t("composerMissing"), true); return; }
    const draft = await window.tpiComposer.save();
    if (!draft) return;
    if (!ob.settings) await loadSettings();
    try {
      const r = await postJSON("/api/outbox/prepare", { draft_id: draft.id });
      if (r.settings) ob.settings = r.settings;
      openDialog(r.item, r.token, mode, { fromComposer: true, sendAt: ob.pendingSendAt?.[draft.id] });
    } catch (e) {
      notify(t("failed") + ((e.data?.errors || []).join("；") || e.message), true);
    }
  }
  window.openOutboxConfirm = fromComposer;

  /* composer footer buttons, re-added after every composer render */
  const cmpBack = document.getElementById("tpiCmpBack");
  function injectComposer() {
    const foot = cmpBack?.querySelector(".tpi-cmp-foot");
    if (!foot || foot.querySelector("[data-ob-cmp]")) return;
    const mk = (mode, key, cls) => {
      const b = document.createElement("button");
      b.className = "btn " + cls;
      b.dataset.obCmp = mode;
      b.textContent = t(key);
      return b;
    };
    foot.append(mk("schedule", "scheduleBtn", ""), mk("now", "sendBtn", "primary"));
  }
  if (cmpBack) {
    new MutationObserver(injectComposer).observe(cmpBack, { childList: true });
    cmpBack.addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-ob-cmp]");
      if (b) { ev.stopPropagation(); fromComposer(b.dataset.obCmp); }
    }, true);
    injectComposer();
  }

  /* ── Undo Send countdown ── */
  const undoBar = document.createElement("div");
  undoBar.id = "obUndoBar";
  document.body.appendChild(undoBar);

  function startUndo(item) {
    const total = Math.max(1, Number(item.seconds_left) || (ob.settings?.undo_seconds ?? 10));
    ob.undo.set(item.id, { item, total, deadline: performance.now() + total * 1000, done: false });
    renderUndo();
  }
  function renderUndo() {
    const now = performance.now();
    undoBar.innerHTML = [...ob.undo.entries()].map(([id, u]) => {
      const left = Math.max(0, Math.ceil((u.deadline - now) / 1000));
      const pct = Math.max(0, Math.min(100, ((u.deadline - now) / (u.total * 1000)) * 100));
      return `<div class="ob-undo" data-undo-id="${h(id)}"><div><div>${h(t("undoBar").replace("{n}", left))} · ${h(u.item.subject || t("noSubject"))}</div>
        <div class="bar" style="width:${pct.toFixed(1)}%"></div></div><button class="btn primary" data-ob-undo="${h(id)}">${h(t("undo"))}</button></div>`;
    }).join("");
  }
  async function finishUndo(id) {
    const u = ob.undo.get(id);
    if (!u || u.done) return;
    u.done = true;
    try {
      await postJSON("/api/outbox/tick", {});
      const it = await getJSON("/api/outbox/item/" + encodeURIComponent(id));
      ob.undo.delete(id);
      if (it.state === "ready") {
        ob.undoReleased.add(it.id);
        notify(t("released").replace("{f}", it.eml_name));
      }
    } catch { ob.undo.delete(id); }
    renderUndo();
    refreshSummary();
    if (state.view === "outbox" || state.view === "scheduled") loadView(state.view);
  }
  async function doUndo(id) {
    const u = ob.undo.get(id);
    if (!u) return;
    u.done = true;
    try {
      const r = await postJSON("/api/outbox/undo", { id });
      ob.undo.delete(id);
      renderUndo();
      notify(t("undone"));
      if (r.draft_id && window.tpiComposer) window.tpiComposer.open(u.item.kind || "new", { draftId: r.draft_id });
    } catch (e) {
      ob.undo.delete(id);
      renderUndo();
      notify(e.message, true);
    }
    refreshSummary();
    if (typeof loadDrafts === "function" && state.view === "drafts") loadDrafts();
  }
  undoBar.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-ob-undo]");
    if (b) doUndo(Number(b.dataset.obUndo));
  });
  setInterval(() => {
    if (!ob.undo.size) return;
    const now = performance.now();
    for (const [id, u] of ob.undo) if (!u.done && u.deadline <= now) finishUndo(id);
    renderUndo();
  }, 250);
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "z" || ev.ctrlKey || ev.metaKey || ev.altKey || !ob.undo.size) return;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(ev.target.tagName) || dlg.open) return;
    const open = [...ob.undo.entries()].filter(([, u]) => !u.done);
    if (!open.length) return;
    ev.preventDefault();
    doUndo(open[open.length - 1][0]);
  });

  /* ── Scheduled + Outbox folders ── */
  const $list = () => document.getElementById("list");
  const $pane = () => document.getElementById("pane");
  const badge = (it) => {
    if (it.state === "awaiting_confirm") return `<span class="ob-badge ${it.created_by === "agent" ? "agent" : ""}">${h(it.state_label)}${it.created_by === "agent" ? " · " + h(t("byAgent")) : ""}</span>`;
    return `<span class="ob-badge ${it.state === "ready" ? "ready" : ""}">${h(it.state_label)}</span>`;
  };
  const rowHtml = (it, meta, dim) => `
    <div class="row ${dim ? "ob-dim" : ""} ${ob.selected === it.id ? "on" : ""}" data-ob-id="${h(it.id)}">
      <div class="dot ${it.state === "ready" ? "upcoming" : it.state === "awaiting_confirm" ? "needs_you" : "worth_a_look"}"></div>
      <div><div class="rowline"><span class="from">${h(it.to || "—")}</span></div>
      <div class="subj">${h(it.subject || t("noSubject"))}</div></div>
      <div class="meta">${h(meta)}<br>${badge(it)}</div>
    </div>`;

  async function loadView(view) {
    const states = view === "scheduled" ? "awaiting_confirm,undo_window,scheduled,blocked" : "ready,done,cancelled";
    let items = [];
    try {
      if (!ob.settings) await loadSettings();
      items = (await getJSON("/api/outbox/items?state=" + states + "&limit=200")).items || [];
    } catch (e) {
      $pane().innerHTML = `<p class="muted">${h(t("failed") + e.message)}</p>`;
      return;
    }
    if (state.view !== view) return;
    if (view === "outbox") items = items.filter((x) => x.state !== "cancelled" || x.eml_path);
    ob.items = items;
    if (ob.selected && !items.some((x) => x.id === ob.selected)) ob.selected = null;
    renderList(view);
    renderPane(view);
  }

  function renderList(view) {
    const items = ob.items;
    let html = "";
    if (view === "scheduled") {
      const awaiting = items.filter((x) => x.state === "awaiting_confirm");
      const pending = items.filter((x) => x.state !== "awaiting_confirm");
      if (awaiting.length) html += `<div class="ob-sec">${h(t("awaitingTitle"))}</div>` + awaiting.map((x) => rowHtml(x, when(x.proposed_at || x.created_at).slice(5))).join("");
      if (pending.length) html += `<div class="ob-sec">${h(t("scheduledTitle"))}</div>` + pending.map((x) => rowHtml(x, when(x.release_at).slice(5))).join("");
      html = html || `<div class="empty">${h(t("emptyScheduled"))}</div>`;
    } else {
      const ready = items.filter((x) => x.state === "ready");
      const rest = items.filter((x) => x.state !== "ready");
      html += ready.map((x) => rowHtml(x, when(x.released_at).slice(5))).join("");
      if (rest.length) html += `<div class="ob-sec">${h(t("historyTitle"))}</div>` + rest.map((x) => rowHtml(x, when(x.done_at || x.updated_at).slice(5), true)).join("");
      html = html || `<div class="empty">${h(t("emptyOutbox"))}</div>`;
    }
    $list().innerHTML = html;
    $list().onclick = (ev) => {
      const row = ev.target.closest("[data-ob-id]");
      if (!row) return;
      ob.selected = Number(row.dataset.obId);
      $list().querySelectorAll(".row").forEach((r) => r.classList.toggle("on", r === row));
      renderPane(view);
    };
  }

  function settingsHtml() {
    const s = ob.settings;
    if (!s) return "";
    return `<h4>⚙ ${h(t("settingsTitle"))}</h4>
      <div class="row-set"><span>${h(t("undoSeconds"))}</span>
        <select id="obUndoSecs">${(s.undo_choices || []).map((n) => `<option value="${h(n)}" ${n === s.undo_seconds ? "selected" : ""}>${h(n)} ${h(t("seconds"))}</option>`).join("")}</select></div>
      <div class="row-set"><span>${h(t("alwaysConfirm"))}</span><span class="ob-badge">✔ ${h(t("locked"))}</span></div>
      <div class="row-set"><span>${h(t("transport"))}</span><code>${h(s.transport_info?.name)}</code><span class="muted" style="font-size:12px">${h(s.transport_info?.label)}</span></div>
      <div class="row-set"><span>${h(t("folder"))}</span><code>${h(s.outbox_dir)}/</code></div>
      <p class="hint">${h(s.note)}</p>`;
  }

  function detailHtml(it, view) {
    const kv = `<div class="ob-kv">
        <span>${h(t("from"))}</span><div>${h(it.account)}</div>
        <span>${h(t("to"))}</span><div>${h(it.to)}</div>
        ${it.cc ? `<span>${h(t("cc"))}</span><div>${h(it.cc)}</div>` : ""}
        ${it.bcc ? `<span>${h(t("bcc"))}</span><div>${h(it.bcc)}</div>` : ""}
        ${it.release_at ? `<span>${h(t("releaseAt"))}</span><div>${h(when(it.release_at))}</div>` : ""}
        ${it.released_at ? `<span>${h(t("writtenAt"))}</span><div>${h(when(it.released_at))}</div>` : ""}
        ${it.eml_path ? `<span>${h(t("file"))}</span><div><code>${h(it.eml_path)}</code></div>` : ""}
      </div>`;
    let acts = "";
    if (it.state === "scheduled") {
      acts = `<label class="row-set" style="margin:0">${h(t("changeTime"))} <input type="datetime-local" id="obResched" value="${h(localInput(it.release_at))}"/>
          <button class="btn" data-act="resched">${h(t("apply"))}</button></label>
        <div class="ob-picks" style="padding-left:0;width:100%">${((ob.settings || {}).suggestions || []).map((p) => `<button class="btn ghost" data-act="pick" data-at="${h(p.at)}">${h(p.label)} · ${h(when(p.at).slice(5))}</button>`).join("")}</div>
        <button class="btn" data-act="now">${h(t("releaseNow"))}</button>
        <button class="btn" data-act="edit">${h(t("edit"))}</button>
        <button class="btn ghost" data-act="cancel">${h(t("cancelSchedule"))}</button>`;
    } else if (it.state === "awaiting_confirm") {
      acts = `<button class="btn primary" data-act="review">${h(t("review"))}</button>
        <button class="btn" data-act="edit">${h(t("edit"))}</button>
        <button class="btn ghost" data-act="discard">${h(t("discard"))}</button>`;
    } else if (it.state === "undo_window") {
      acts = `<button class="btn primary" data-act="undo">${h(t("undo"))}</button>`;
    } else if (it.state === "blocked") {
      acts = `<button class="btn" data-act="edit">${h(t("edit"))}</button>
        <button class="btn ghost" data-act="cancel">${h(t("cancelSchedule"))}</button>`;
    } else if (it.state === "ready") {
      acts = `<a class="btn primary" href="${h(it.eml_url)}" download="${h(it.eml_name)}">${h(t("download"))}</a>
        <button class="btn" data-act="copy">${h(t("copyPath"))}</button>
        <button class="btn" data-act="done">${h(t("markDone"))}</button>
        <button class="btn ghost" data-act="back">${h(t("backToDrafts"))}</button>`;
    } else if (it.state === "done" && it.eml_url) {
      acts = `<a class="btn ghost" href="${h(it.eml_url)}" download="${h(it.eml_name)}">${h(t("download"))}</a>`;
    }
    return `<h2 class="mh">${h(it.subject || t("noSubject"))}</h2>
      <p class="muted" style="margin:0 0 6px">${badge(it)} · ${h(it.created_by === "agent" ? t("byAgent") : t("byUser"))}</p>
      ${it.note ? `<div class="ob-note">${h(it.note)}</div>` : ""}
      ${it.state === "ready" ? `<div class="ob-note">${h(t("outboxHint"))}</div>` : ""}
      ${kv}
      ${(it.blocking || []).map((x) => `<div class="ob-block">⛔ ${h(x)}</div>`).join("")}
      ${(it.warnings || []).map((x) => `<div class="ob-warn">⚠ ${h(x)}</div>`).join("")}
      ${acts ? `<div class="actionbar" data-ob-acts="${h(it.id)}">${acts}</div>` : ""}
      <div class="msg"><div class="body">${h(it.body)}</div></div>`;
  }

  function renderPane(view) {
    const it = ob.items.find((x) => x.id === ob.selected);
    if (it) {
      $pane().innerHTML = `<div class="ob-pane">${detailHtml(it, view)}</div>`;
      return;
    }
    const title = view === "scheduled" ? t("scheduledTitle") : t("outboxTitle");
    const hint = view === "scheduled" ? t("scheduledHint") : t("outboxHint");
    const extra = view === "scheduled" && ob.items.some((x) => x.state === "awaiting_confirm") ? `<p class="hint">${h(t("awaitingHint"))}</p>` : "";
    $pane().innerHTML = `<div class="ob-pane"><h2 class="mh">${h(title)}</h2>
      <p class="muted">${h(ob.items.length)} · ${h(hint)}</p>${extra}
      <p class="hint">${h(t("select"))}</p>${settingsHtml()}</div>`;
  }

  async function act(id, what, extra = {}) {
    const it = ob.items.find((x) => x.id === id);
    if (!it) return;
    try {
      if (what === "review") {
        const r = await postJSON("/api/outbox/review", { id });
        if (r.settings) ob.settings = r.settings;
        openDialog(r.item, r.token, it.proposed_at ? "schedule" : "now");
        return;
      }
      if (what === "copy") {
        try { await navigator.clipboard.writeText(it.eml_path); notify(t("copied")); } catch { notify(t("failed"), true); }
        return;
      }
      if (what === "cancel" && !window.confirm(t("confirmCancel"))) return;
      if (what === "back" && !window.confirm(t("confirmBack"))) return;
      let r;
      if (what === "resched" || what === "pick" || what === "now") r = await postJSON("/api/outbox/reschedule", { id, send_at: what === "now" ? "now" : extra.at });
      else if (what === "edit") r = await postJSON("/api/outbox/edit", { id });
      else if (what === "cancel" || what === "back") r = await postJSON("/api/outbox/cancel", { id, keep_draft: true });
      else if (what === "discard") r = await postJSON("/api/outbox/discard", { id });
      else if (what === "done") r = await postJSON("/api/outbox/done", { id });
      else if (what === "undo") r = await postJSON("/api/outbox/undo", { id });
      if (!r) return;
      if (r.item?.state === "ready") ob.undoReleased.add(r.item.id);
      notify(r.note || "");
      if (what === "edit" && r.draft_id) {
        if (r.previous_release_at) {
          ob.pendingSendAt[r.draft_id] = r.previous_release_at;
          notify(t("editNote").replace("{t}", when(r.previous_release_at)));
        }
        if (window.tpiComposer) window.tpiComposer.open(it.kind || "new", { draftId: r.draft_id });
      }
      if (what === "now" && r.item?.state === "ready") ob.selected = null;
      refreshSummary();
      loadView(state.view);
    } catch (e) {
      notify(t("failed") + e.message, true);
      loadView(state.view);
    }
  }

  document.getElementById("pane").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-act]");
    const bar = ev.target.closest("[data-ob-acts]");
    if (!b || !bar || (state.view !== "scheduled" && state.view !== "outbox")) return;
    const id = Number(bar.dataset.obActs);
    const what = b.dataset.act;
    if (what === "resched") {
      const v = document.getElementById("obResched")?.value;
      if (!v) { notify(t("needTime"), true); return; }
      act(id, "resched", { at: v });
    } else if (what === "pick") act(id, "pick", { at: b.dataset.at });
    else act(id, what);
  });
  document.getElementById("pane").addEventListener("change", async (ev) => {
    if (ev.target.id !== "obUndoSecs") return;
    try {
      ob.settings = await postJSON("/api/outbox/settings", { undo_seconds: Number(ev.target.value) });
      notify(t("settingsSaved"));
    } catch (e) { notify(t("failed") + e.message, true); }
  });

  const coreSetView = window.setView;
  if (typeof coreSetView === "function") {
    window.setView = (v, ...rest) => {
      const out = coreSetView(v, ...rest);
      if (v === "scheduled" || v === "outbox") { ob.selected = null; loadView(v); }
      return out;
    };
  }

  new MutationObserver(async () => {
    relabel();
    await loadSettings();
    cmpBack?.querySelectorAll("[data-ob-cmp]").forEach((b) => { b.textContent = t(b.dataset.obCmp === "now" ? "sendBtn" : "scheduleBtn"); });
    if (dlg.open) renderDialog();
    renderUndo();
    if (state.view === "scheduled" || state.view === "outbox") loadView(state.view);
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

  loadSettings();
  refreshSummary();
  setInterval(refreshSummary, 10000);
  const hv = new URLSearchParams(location.hash.slice(1)).get("view");
  if (hv === "scheduled" || hv === "outbox") window.setView(hv);
})();
