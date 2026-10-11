/* Composer + AI Write: new mail / reply / forward saved as local drafts (POST /api/compose/draft),
   AI draft from the thread + draft style (POST /api/compose/write), tone rewrite (POST /api/compose/rewrite),
   draft style + CJK font settings (/api/compose/settings) and the voice learned from your edits
   (/api/compose/voice). Nothing is ever sent. */
(() => {
  "use strict";
  const S = {
    zh: {
      compose: "✎ 撰寫", settings: "⚙ 撰寫設定", newMail: "新郵件", reply: "↩ 回覆", forward: "↪ 轉寄",
      titleNew: "新郵件", titleReply: "回覆", titleForward: "轉寄",
      from: "寄件帳號", to: "收件者", cc: "副本", bcc: "密件副本", ccToggle: "副本／密件", subject: "主旨",
      aiPlaceholder: "告訴 AI 要寫什麼，或要怎麼改（例如：答應週五前給、語氣更正式）",
      aiWrite: "✦ AI 起草", aiRewrite: "✦ 依指示改寫", formal: "更正式", shorter: "更短", friendlier: "更友善",
      undo: "↶ 復原", style: "草稿風格", body: "內文", includeQuote: "附上原信", quoteLabel: "原信內容",
      save: "存入本機草稿", saveUpdate: "更新本機草稿", copy: "複製內文", cancel: "關閉",
      localOnly: "只存本機草稿，TooPowerInbox 設計上不寄信。快捷鍵：Ctrl／⌘＋S 儲存、Esc 關閉。",
      saved: "已存入本機草稿", learned: "已從你的修改學到語氣（共 {n} 筆樣本）", unchanged: "改寫後沒有變化",
      writing: "起草中…", rewriting: "改寫中…", failed: "操作失敗：", needText: "內文是空的",
      needInstr: "先在上面輸入指示", dirty: "草稿還沒存，確定關閉？", copied: "已複製",
      setTitle: "撰寫設定", styleHint: "AI 起草與改寫預設用這個風格；撰寫器裡可以單封切換。",
      font: "中日韓字型", fontHint: "只用本機已安裝的字型，不會下載任何東西；沒有安裝時自動退回下一個字型。",
      fontScope: "套用範圍", scopeCompose: "只有撰寫器", scopeApp: "整個介面", fontSize: "字級",
      preview: "繁體中文：撰寫器字型預覽 · 简体中文预览 · 日本語のプレビュー · 한국어 미리보기 · Aa 123",
      voice: "學到的語氣", voiceHint: "你修改 AI 草稿後存檔，修改前後會存成語氣樣本，寫進 persona（更了解你），之後起草會照你的習慣。",
      samples: "樣本", noVoice: "還沒有樣本：讓 AI 起草、改成你的說法、存草稿，就會開始學。",
      before: "AI 原稿", after: "你改成", forget: "忘記", forgetAll: "全部忘記",
      forgetConfirm: "確定刪除所有語氣樣本？persona 裡學到的語氣也會一起移除。", forgotten: "已刪除",
      settingsSaved: "撰寫設定已儲存", close: "關閉",
    },
    en: {
      compose: "✎ Compose", settings: "⚙ Compose settings", newMail: "New mail", reply: "↩ Reply", forward: "↪ Forward",
      titleNew: "New mail", titleReply: "Reply", titleForward: "Forward",
      from: "From account", to: "To", cc: "Cc", bcc: "Bcc", ccToggle: "Cc / Bcc", subject: "Subject",
      aiPlaceholder: "Tell AI what to write or how to change it (e.g. say yes by Friday, more formal)",
      aiWrite: "✦ AI draft", aiRewrite: "✦ Rewrite as told", formal: "More formal", shorter: "Shorter", friendlier: "Friendlier",
      undo: "↶ Undo", style: "Draft style", body: "Body", includeQuote: "Include original", quoteLabel: "Original message",
      save: "Save to local drafts", saveUpdate: "Update local draft", copy: "Copy body", cancel: "Close",
      localOnly: "Saved as a local draft only; TooPowerInbox never sends mail. Shortcuts: Ctrl/⌘+S save, Esc close.",
      saved: "Saved to local drafts", learned: "Learned from your edits ({n} samples)", unchanged: "The rewrite changed nothing",
      writing: "Drafting…", rewriting: "Rewriting…", failed: "Failed: ", needText: "The body is empty",
      needInstr: "Type an instruction above first", dirty: "This draft is not saved. Close anyway?", copied: "Copied",
      setTitle: "Compose settings", styleHint: "AI drafts and rewrites use this style by default; switch per mail in the composer.",
      font: "CJK font", fontHint: "Uses fonts already installed on this machine; nothing is downloaded. Missing fonts fall back to the next one.",
      fontScope: "Apply to", scopeCompose: "Composer only", scopeApp: "Whole interface", fontSize: "Size",
      preview: "繁體中文：撰寫器字型預覽 · 简体中文预览 · 日本語のプレビュー · 한국어 미리보기 · Aa 123",
      voice: "Learned voice", voiceHint: "When you edit an AI draft and save it, the before/after pair becomes a voice sample in your persona (Know you better), and later drafts follow your habits.",
      samples: "samples", noVoice: "No samples yet: let AI draft, change it to how you'd say it, save the draft.",
      before: "AI draft", after: "You changed it to", forget: "Forget", forgetAll: "Forget all",
      forgetConfirm: "Delete every voice sample? The learned voice in your persona goes too.", forgotten: "Deleted",
      settingsSaved: "Compose settings saved", close: "Close",
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
  const toolbar = document.querySelector(".toolbar");
  if (!toolbar || typeof state !== "object" || window.__tpiCompose) return;
  window.__tpiCompose = true;

  const css = document.createElement("style");
  css.textContent = `
    .tpi-back { position: fixed; inset: 0; background: rgba(10,8,6,.62); display: none; align-items: center; justify-content: center; z-index: 65; }
    .tpi-back.open { display: flex; }
    .tpi-cmp { width: min(760px, 94vw); max-height: 92vh; display: flex; flex-direction: column; background: var(--panel); border: 1px solid #3a332a; border-radius: 14px; box-shadow: var(--shadow); }
    .tpi-cmp-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--line); }
    .tpi-cmp-head b { font-size: 15px; }
    .tpi-cmp-head .x { margin-left: auto; background: transparent; border: none; color: var(--muted); font-size: 17px; }
    .tpi-cmp-main { padding: 12px 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; min-height: 0; }
    .tpi-f { display: grid; grid-template-columns: 92px 1fr; gap: 8px; align-items: center; font-size: 12.5px; color: var(--muted); }
    .tpi-f input, .tpi-f select, .tpi-ai input, .tpi-cmp select, .tpi-set select, .tpi-set input[type=number] { background: #171410; border: 1px solid var(--line); border-radius: 8px; padding: 7px 10px; outline: none; color: var(--ink); min-width: 0; }
    .tpi-f input:focus, .tpi-ai input:focus, .tpi-cmp-body:focus { border-color: #4a4136; }
    .tpi-linkbtn { background: none; border: none; color: var(--accent); font-size: 12px; padding: 0; justify-self: start; }
    .tpi-ai { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; padding: 8px; border: 1px dashed #4a4136; border-radius: 10px; background: rgba(196,165,116,.04); }
    .tpi-ai input { flex: 1 1 260px; }
    .tpi-ai .btn { font-size: 12px; padding: 5px 10px; }
    .tpi-ai select { font-size: 12px; padding: 5px 8px; }
    .tpi-cmp-body { width: 100%; min-height: 240px; background: #171410; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; outline: none; resize: vertical; line-height: 1.75; color: var(--ink); }
    .tpi-cmp-quote { white-space: pre-wrap; font-size: 12.5px; color: var(--muted); border-left: 2px solid var(--line); padding: 4px 10px; margin-top: 6px; max-height: 180px; overflow: auto; }
    .tpi-cmp details summary { cursor: pointer; font-size: 12px; color: var(--muted); }
    .tpi-cmp-meta { display: flex; gap: 10px; align-items: center; font-size: 11.5px; color: var(--muted); flex-wrap: wrap; }
    .tpi-cmp-meta .src { border: 1px solid var(--line); border-radius: 999px; padding: 0 7px; }
    .tpi-cmp-meta .src.agent { color: var(--ok); border-color: #48603f; }
    .tpi-cmp-meta .src.heur { color: var(--need); border-color: #6b4a3a; }
    .tpi-warn { font-size: 12px; color: var(--need); }
    .tpi-cmp-foot { display: flex; gap: 8px; align-items: center; padding: 10px 16px 14px; border-top: 1px solid var(--line); }
    .tpi-cmp-foot .note { color: var(--muted); font-size: 11.5px; margin-right: auto; }
    .tpi-set { width: min(680px, 94vw); max-height: 90vh; overflow-y: auto; background: var(--panel); border: 1px solid #3a332a; border-radius: 14px; box-shadow: var(--shadow); padding: 16px 20px; }
    .tpi-set h3 { margin: 0 0 4px; font-size: 16px; }
    .tpi-set h4 { margin: 18px 0 6px; font-size: 13.5px; color: var(--accent2); border-bottom: 1px dashed #3a332a; padding-bottom: 4px; }
    .tpi-set .hint { margin-top: 2px; }
    .tpi-styles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    .tpi-style { border: 1px solid var(--line); border-radius: 10px; padding: 9px 10px; cursor: pointer; background: #171410; font-size: 12.5px; }
    .tpi-style.on { border-color: var(--accent); background: rgba(196,165,116,.08); }
    .tpi-style b { display: block; font-size: 13.5px; margin-bottom: 3px; }
    .tpi-style pre { white-space: pre-wrap; font: inherit; font-size: 11.5px; color: var(--muted); margin: 6px 0 0; }
    .tpi-preview { border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; margin-top: 8px; background: #171410; line-height: 1.8; }
    .tpi-row { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; margin-top: 8px; font-size: 12.5px; }
    .tpi-trait { font-size: 12.5px; padding: 3px 0; }
    .tpi-sample { border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; margin: 6px 0; font-size: 12px; }
    .tpi-sample .lbl { color: var(--muted); font-size: 11px; margin-top: 4px; }
    .tpi-sample pre { white-space: pre-wrap; font: inherit; margin: 2px 0; max-height: 110px; overflow: auto; }
    .tpi-sample .btn { font-size: 11px; padding: 2px 8px; float: right; }`;
  document.head.appendChild(css);

  const fontStyle = document.createElement("style");
  fontStyle.id = "tpi-compose-font";
  document.head.appendChild(fontStyle);

  const cfg = { style: "balanced", font: "system", font_scope: "compose", font_size: 15, font_stack: "", font_lang: "", styles: [], fonts: [] };
  const SAFE_STACK = /^[\w\s",.-]*$/;
  function applyFont() {
    const stack = SAFE_STACK.test(cfg.font_stack || "") ? cfg.font_stack : "";
    const size = Math.max(12, Math.min(24, Number(cfg.font_size) || 15));
    let rules = `.tpi-cmp-body, .tpi-cmp-quote { font-size: ${size}px; ${stack ? `font-family: ${stack};` : ""} }`;
    if (stack && cfg.font_scope === "app") {
      rules += `\nbody, .msg .body, .bubble, .modal textarea, .tpi-cmp input { font-family: ${stack} !important; }`;
    }
    fontStyle.textContent = rules;
    const ta = document.getElementById("tpiCmpBody");
    if (ta) ta.lang = cfg.font_lang || document.documentElement.lang;
  }
  async function loadSettings() {
    try { Object.assign(cfg, await getJSON("/api/compose/settings?lang=" + langParam())); applyFont(); } catch {}
    return cfg;
  }

  /* ── entry points ── */
  const newBtn = document.createElement("button");
  newBtn.className = "btn";
  newBtn.id = "tpiComposeBtn";
  toolbar.insertBefore(newBtn, document.getElementById("cpBtn"));
  newBtn.onclick = () => openComposer("new");

  const setBtn = document.createElement("button");
  setBtn.className = "langbtn";
  setBtn.id = "tpiComposeSettingsBtn";
  const foot = document.querySelector(".sidefoot");
  if (foot) foot.insertBefore(setBtn, document.getElementById("langBtn") || null);
  setBtn.onclick = () => openSettings();
  const relabel = () => { newBtn.textContent = t("compose"); setBtn.textContent = t("settings"); };
  relabel();

  /* ── composer ── */
  const back = document.createElement("div");
  back.className = "tpi-back";
  back.id = "tpiCmpBack";
  document.body.appendChild(back);
  const cmp = { open: false, busy: false, kind: "new", id: null, account: "", to: "", cc: "", bcc: "", subject: "", text: "",
    quote: "", includeQuote: true, source_id: "", ai_body: "", style: "", label: "", source: "", warnings: [], undo: [], saved: "", showCc: false };

  const accounts = () => {
    const list = (state.cfg?.accounts || []).map((a) => a.email).filter(Boolean);
    return list.length ? list : ["you@example.com"];
  };
  const snapshot = () => JSON.stringify([cmp.to, cmp.cc, cmp.bcc, cmp.subject, cmp.text, cmp.includeQuote]);

  function readForm() {
    if (!cmp.open) return;
    const v = (id) => document.getElementById(id)?.value ?? "";
    cmp.account = v("tpiCmpFrom"); cmp.to = v("tpiCmpTo"); cmp.cc = v("tpiCmpCc"); cmp.bcc = v("tpiCmpBcc");
    cmp.subject = v("tpiCmpSubject"); cmp.text = v("tpiCmpBody"); cmp.style = v("tpiCmpStyle") || cmp.style;
    const q = document.getElementById("tpiCmpIncQuote"); if (q) cmp.includeQuote = q.checked;
  }

  function renderComposer() {
    cmp.busy = false;
    const active = document.activeElement;
    const refocus = active && back.contains(active) ? active.id || "tpiCmpBody" : "";
    const title = { new: t("titleNew"), reply: t("titleReply"), forward: t("titleForward") }[cmp.kind];
    const accs = accounts();
    if (!cmp.account || !accs.includes(cmp.account)) accs.unshift(cmp.account || accs[0]);
    const styles = cfg.styles.length ? cfg.styles : [{ id: "professional", name: "Professional" }, { id: "balanced", name: "Balanced" }, { id: "casual", name: "Casual" }];
    back.innerHTML = `
      <div class="tpi-cmp" role="dialog" aria-label="${h(title)}">
        <div class="tpi-cmp-head"><b>✎ ${h(title)}</b><span class="muted" style="font-size:12px">${cmp.id ? "#" + h(cmp.id) : ""}</span><button class="x" data-c="close" title="${h(t("close"))}">✕</button></div>
        <div class="tpi-cmp-main">
          <label class="tpi-f"><span>${h(t("from"))}</span><select id="tpiCmpFrom">${[...new Set(accs.filter(Boolean))].map((a) => `<option ${a === cmp.account ? "selected" : ""}>${h(a)}</option>`).join("")}</select></label>
          <label class="tpi-f"><span>${h(t("to"))}</span><input id="tpiCmpTo" value="${h(cmp.to)}" placeholder="name@example.com" /></label>
          <div class="tpi-f" id="tpiCmpCcRow" style="${cmp.showCc ? "" : "display:none"}"><span>${h(t("cc"))}</span><input id="tpiCmpCc" value="${h(cmp.cc)}" /></div>
          <div class="tpi-f" id="tpiCmpBccRow" style="${cmp.showCc ? "" : "display:none"}"><span>${h(t("bcc"))}</span><input id="tpiCmpBcc" value="${h(cmp.bcc)}" /></div>
          <div class="tpi-f"><span></span><button class="tpi-linkbtn" data-c="cc">${h(t("ccToggle"))}</button></div>
          <label class="tpi-f"><span>${h(t("subject"))}</span><input id="tpiCmpSubject" value="${h(cmp.subject)}" /></label>
          <div class="tpi-ai">
            <input id="tpiCmpInstr" placeholder="${h(t("aiPlaceholder"))}" />
            <button class="btn primary" data-c="write">${h(t("aiWrite"))}</button>
            <button class="btn" data-c="rewrite">${h(t("aiRewrite"))}</button>
            <button class="btn" data-tone="formal">${h(t("formal"))}</button>
            <button class="btn" data-tone="shorter">${h(t("shorter"))}</button>
            <button class="btn" data-tone="friendlier">${h(t("friendlier"))}</button>
            <button class="btn ghost" data-c="undo" ${cmp.undo.length ? "" : "disabled"}>${h(t("undo"))}</button>
            <label style="font-size:12px;color:var(--muted)">${h(t("style"))}
              <select id="tpiCmpStyle">${styles.map((s) => `<option value="${h(s.id)}" ${s.id === (cmp.style || cfg.style) ? "selected" : ""}>${h(s.name)}</option>`).join("")}</select></label>
          </div>
          <textarea id="tpiCmpBody" class="tpi-cmp-body" aria-label="${h(t("body"))}"></textarea>
          <div class="tpi-cmp-meta">${cmp.label ? `<span class="src ${cmp.source === "agent" ? "agent" : "heur"}">${h(cmp.label)}</span>` : ""}<span id="tpiCmpBusy"></span></div>
          ${cmp.warnings.map((w) => `<div class="tpi-warn">⚠ ${h(w)}</div>`).join("")}
          ${cmp.quote ? `<details ${cmp.kind === "forward" ? "open" : ""}><summary><label><input type="checkbox" id="tpiCmpIncQuote" ${cmp.includeQuote ? "checked" : ""}/> ${h(t("includeQuote"))}</label> · ${h(t("quoteLabel"))}</summary><div class="tpi-cmp-quote">${h(cmp.quote)}</div></details>` : ""}
        </div>
        <div class="tpi-cmp-foot">
          <span class="note">${h(t("localOnly"))}</span>
          <button class="btn ghost" data-c="close">${h(t("cancel"))}</button>
          <button class="btn" data-c="copy">${h(t("copy"))}</button>
          <button class="btn primary" data-c="save">${h(cmp.id ? t("saveUpdate") : t("save"))}</button>
        </div>
      </div>`;
    const ta = document.getElementById("tpiCmpBody");
    ta.value = cmp.text;
    applyFont();
    if (refocus) (document.getElementById(refocus) || ta).focus();
  }

  function setBusy(label) {
    cmp.busy = !!label;
    const el = document.getElementById("tpiCmpBusy");
    if (el) el.textContent = label || "";
    back.querySelectorAll(".tpi-ai .btn, [data-c=save]").forEach((b) => { b.disabled = !!label || (b.dataset.c === "undo" && !cmp.undo.length); });
  }

  async function openComposer(kind, opts = {}) {
    readForm();
    if (cmp.open && snapshot() !== cmp.saved && !window.confirm(t("dirty"))) return;
    if (!cfg.styles.length) await loadSettings();
    let d;
    try {
      if (opts.draftId) {
        const x = await getJSON("/api/compose/draft/" + encodeURIComponent(opts.draftId));
        d = { ...x, text: x.text, includeQuote: !!x.quote };
      } else {
        d = await postJSON("/api/compose/start", { kind, item_id: opts.itemId || "", account: opts.account || state.account || "" });
        d.text = opts.body || "";
        d.ai_body = opts.aiBody || "";
        d.id = null;
        d.includeQuote = true;
      }
    } catch (e) { notify(t("failed") + e.message, true); return; }
    Object.assign(cmp, {
      open: true, kind: d.kind || kind, id: d.id || null, account: d.account || accounts()[0], to: d.to || "", cc: d.cc || "",
      bcc: d.bcc || "", subject: d.subject || "", text: d.text || "", quote: d.quote || "", includeQuote: d.includeQuote !== false,
      source_id: d.source_id || "", ai_body: d.ai_body || "", style: d.style || cfg.style, label: "", source: "",
      warnings: d.warnings || [], undo: [], showCc: !!(d.cc || d.bcc),
    });
    renderComposer();
    cmp.saved = opts.body ? "" : snapshot();
    back.classList.add("open");
    const focusId = cmp.kind === "forward" || !cmp.to ? "tpiCmpTo" : "tpiCmpBody";
    document.getElementById(focusId)?.focus();
  }
  window.openComposer = openComposer;

  function closeComposer(force) {
    readForm();
    if (!force && snapshot() !== cmp.saved && !window.confirm(t("dirty"))) return;
    cmp.open = false;
    back.classList.remove("open");
    back.innerHTML = "";
  }

  function replaceText(text, label, source) {
    cmp.undo.push(cmp.text);
    cmp.text = text;
    cmp.ai_body = text;
    cmp.label = label || "";
    cmp.source = source || "";
    renderComposer();
  }

  async function aiWrite() {
    readForm();
    const instruction = document.getElementById("tpiCmpInstr").value.trim();
    setBusy(t("writing"));
    try {
      const r = await postJSON("/api/compose/write", { kind: cmp.kind, item_id: cmp.source_id, instruction, style: cmp.style, to: cmp.to, subject: cmp.subject, body: cmp.text });
      if (r.subject_suggestion && !cmp.subject) cmp.subject = r.subject_suggestion;
      replaceText(r.text, r.label + (r.error ? " · " + r.error : ""), r.source);
      document.getElementById("tpiCmpInstr").value = instruction;
    } catch (e) { notify(t("failed") + e.message, true); setBusy(""); }
  }

  async function aiRewrite(tone) {
    readForm();
    const instruction = document.getElementById("tpiCmpInstr").value.trim();
    if (!cmp.text.trim()) { notify(t("needText"), true); return; }
    if (!tone && !instruction) { notify(t("needInstr"), true); return; }
    setBusy(t("rewriting"));
    try {
      const r = await postJSON("/api/compose/rewrite", { body: cmp.text, tone: tone || "", instruction: tone ? "" : instruction, style: cmp.style });
      if (r.note) notify(r.note, true);
      if (r.changed === false) { notify(t("unchanged")); setBusy(""); return; }
      replaceText(r.text, r.label + (r.error ? " · " + r.error : ""), r.source);
      document.getElementById("tpiCmpInstr").value = instruction;
    } catch (e) { notify(t("failed") + e.message, true); setBusy(""); }
  }

  async function saveDraft() {
    readForm();
    setBusy("…");
    try {
      const r = await postJSON("/api/compose/draft", {
        id: cmp.id || undefined, kind: cmp.kind, account: cmp.account, to: cmp.to, cc: cmp.cc, bcc: cmp.bcc,
        subject: cmp.subject, text: cmp.text, quote: cmp.includeQuote ? cmp.quote : "", ai_body: cmp.ai_body,
        style: cmp.style, font: cfg.font, source_id: cmp.source_id,
      });
      cmp.id = r.draft.id;
      cmp.saved = snapshot();
      notify(r.learned?.learned ? t("saved") + " · " + t("learned").replace("{n}", r.learned.samples) : t("saved"));
      (r.warnings || []).forEach((w) => notify(w, true));
      renderComposer();
      if (typeof refreshCounts === "function") refreshCounts();
      if (state.view === "drafts" && typeof loadDrafts === "function") loadDrafts();
    } catch (e) { notify(t("failed") + e.message, true); setBusy(""); }
  }

  back.addEventListener("click", async (ev) => {
    if (ev.target === back) return closeComposer();
    const b = ev.target.closest("button");
    if (!b || cmp.busy) return;
    const c = b.dataset.c;
    if (c === "close") closeComposer();
    else if (c === "cc") { readForm(); cmp.showCc = !cmp.showCc; ["tpiCmpCcRow", "tpiCmpBccRow"].forEach((id) => { document.getElementById(id).style.display = cmp.showCc ? "" : "none"; }); }
    else if (c === "write") aiWrite();
    else if (c === "rewrite") aiRewrite("");
    else if (b.dataset.tone) aiRewrite(b.dataset.tone);
    else if (c === "undo" && cmp.undo.length) { readForm(); cmp.text = cmp.undo.pop(); renderComposer(); }
    else if (c === "copy") {
      readForm();
      try { await navigator.clipboard.writeText(cmp.text); notify(t("copied")); } catch { notify(t("failed"), true); }
    } else if (c === "save") saveDraft();
  });
  back.addEventListener("change", (ev) => { if (ev.target.id === "tpiCmpStyle") cmp.style = ev.target.value; });
  /* capture on document: focus can sit on <body> after a re-render, outside the dialog */
  document.addEventListener("keydown", (ev) => {
    if (!cmp.open || setBack.classList.contains("open")) return;
    if ((ev.ctrlKey || ev.metaKey) && (ev.key === "s" || ev.key === "Enter")) {
      ev.preventDefault(); ev.stopImmediatePropagation();
      if (!cmp.busy) saveDraft();
    } else if (ev.key === "Escape") {
      ev.preventDefault(); ev.stopImmediatePropagation();
      closeComposer();
    }
  }, true);
  back.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && ev.target.id === "tpiCmpInstr") { ev.preventDefault(); if (!cmp.busy) (cmp.text.trim() || document.getElementById("tpiCmpBody").value.trim() ? aiRewrite("") : aiWrite()); }
  });

  /* ── settings + voice ── */
  const setBack = document.createElement("div");
  setBack.className = "tpi-back";
  setBack.id = "tpiCmpSetBack";
  document.body.appendChild(setBack);
  let voice = null;

  async function openSettings() {
    await loadSettings();
    try { voice = await getJSON("/api/compose/voice"); } catch { voice = null; }
    renderSettings();
    setBack.classList.add("open");
  }

  function renderSettings() {
    const traits = voice ? (isZh() ? voice.traits_zh : voice.traits_en) || [] : [];
    const font = cfg.fonts.find((f) => f.id === cfg.font) || {};
    const stack = SAFE_STACK.test(font.stack || "") ? font.stack : "";
    setBack.innerHTML = `
      <div class="tpi-set" role="dialog" aria-label="${h(t("setTitle"))}">
        <div style="display:flex;align-items:center"><h3>⚙ ${h(t("setTitle"))}</h3><button class="btn ghost" data-s="close" style="margin-left:auto">✕</button></div>
        <h4>${h(t("style"))}</h4>
        <div class="tpi-styles">${cfg.styles.map((s) => `
          <div class="tpi-style ${s.id === cfg.style ? "on" : ""}" data-style="${h(s.id)}"><b>${h(s.name)}</b>${h(s.description)}<pre>${h(s.sample)}</pre></div>`).join("")}</div>
        <p class="hint">${h(t("styleHint"))}</p>
        <h4>${h(t("font"))}</h4>
        <select id="tpiSetFont" style="width:100%">${cfg.fonts.map((f) => `<option value="${h(f.id)}" ${f.id === cfg.font ? "selected" : ""}>${h(f.name)}</option>`).join("")}</select>
        <div class="tpi-preview" id="tpiSetPreview" lang="${h(font.lang || document.documentElement.lang)}" style="font-size:${Number(cfg.font_size) || 15}px;${stack ? `font-family:${h(stack)}` : ""}">${h(t("preview"))}</div>
        <div class="tpi-row">
          <span>${h(t("fontScope"))}</span>
          <label><input type="radio" name="tpiScope" value="compose" ${cfg.font_scope === "compose" ? "checked" : ""}/> ${h(t("scopeCompose"))}</label>
          <label><input type="radio" name="tpiScope" value="app" ${cfg.font_scope === "app" ? "checked" : ""}/> ${h(t("scopeApp"))}</label>
          <label>${h(t("fontSize"))} <input type="number" id="tpiSetSize" min="12" max="24" value="${Number(cfg.font_size) || 15}" style="width:70px"/></label>
        </div>
        <p class="hint">${h(t("fontHint"))}</p>
        <h4>${h(t("voice"))} · ${voice ? Number(voice.samples) || 0 : 0} ${h(t("samples"))}</h4>
        <p class="hint">${h(t("voiceHint"))}</p>
        ${traits.length ? traits.map((x) => `<div class="tpi-trait">· ${h(x)}</div>`).join("") : `<p class="muted" style="font-size:12.5px">${h(t("noVoice"))}</p>`}
        ${(voice?.recent || []).map((x) => `
          <div class="tpi-sample"><button class="btn ghost" data-forget="${h(x.id)}">${h(t("forget"))}</button>
            <div class="lbl">${h(t("before"))}</div><pre>${h(x.ai)}</pre>
            <div class="lbl">${h(t("after"))}</div><pre>${h(x.final)}</pre></div>`).join("")}
        ${voice && voice.samples ? `<p><button class="btn ghost" data-s="forgetAll">${h(t("forgetAll"))}</button></p>` : ""}
      </div>`;
  }

  async function saveSettings(changes) {
    try {
      Object.assign(cfg, await postJSON("/api/compose/settings", changes));
      applyFont();
      renderSettings();
      notify(t("settingsSaved"));
    } catch (e) { notify(t("failed") + e.message, true); }
  }

  setBack.addEventListener("click", async (ev) => {
    if (ev.target === setBack) { setBack.classList.remove("open"); return; }
    const card = ev.target.closest("[data-style]");
    if (card) return saveSettings({ style: card.dataset.style });
    const b = ev.target.closest("button");
    if (!b) return;
    if (b.dataset.s === "close") setBack.classList.remove("open");
    else if (b.dataset.forget || b.dataset.s === "forgetAll") {
      if (b.dataset.s === "forgetAll" && !window.confirm(t("forgetConfirm"))) return;
      try {
        const r = await postJSON("/api/compose/voice/forget", b.dataset.forget ? { id: Number(b.dataset.forget) } : { all: true });
        voice = r.voice;
        renderSettings();
        notify(t("forgotten"));
      } catch (e) { notify(t("failed") + e.message, true); }
    }
  });
  setBack.addEventListener("change", (ev) => {
    const el = ev.target;
    if (el.id === "tpiSetFont") saveSettings({ font: el.value });
    else if (el.name === "tpiScope") saveSettings({ font_scope: el.value });
    else if (el.id === "tpiSetSize") saveSettings({ font_size: Number(el.value) });
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && setBack.classList.contains("open")) {
      ev.preventDefault(); ev.stopImmediatePropagation();
      setBack.classList.remove("open");
    }
  }, true);

  /* ── hooks into the core UI ── */
  function addThreadButtons(id) {
    const bar = document.querySelector("#pane .actionbar");
    if (!bar || bar.querySelector("[data-cmp]") || state.selected?.id !== id) return;
    const mk = (kind, label) => {
      const b = document.createElement("button");
      b.className = "btn";
      b.dataset.cmp = kind;
      b.textContent = label;
      b.onclick = () => openComposer(kind, { itemId: id });
      return b;
    };
    bar.prepend(mk("reply", t("reply")), mk("forward", t("forward")));
  }
  const coreOpenThread = window.openThread;
  if (typeof coreOpenThread === "function") {
    window.openThread = async (id, ...rest) => {
      const out = await coreOpenThread(id, ...rest);
      addThreadButtons(id);
      return out;
    };
  }
  window.showDraftEditor = (idx) => {
    const d = (state.drafts || [])[idx];
    if (d) openComposer(d.kind || "new", { draftId: d.id });
  };
  window.openDraftModal = (d) => {
    if (d && d.id) return openComposer(d.kind || "new", { draftId: d.id });
    const item = state.selected;
    if (item) return openComposer("reply", { itemId: item.id, body: d?.body || "", aiBody: d?.body || "" });
    return openComposer("new", { body: d?.body || "", aiBody: d?.body || "" });
  };

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName) || cmp.open || setBack.classList.contains("open")) return;
    if (document.getElementById("modalback")?.classList.contains("open")) return;
    if (e.key === "n") { e.preventDefault(); openComposer("new"); }
    else if ((e.key === "r" || e.key === "f") && state.selected?.id && state.view === "mail") {
      e.preventDefault();
      openComposer(e.key === "r" ? "reply" : "forward", { itemId: state.selected.id });
    }
  });

  new MutationObserver(async () => {
    relabel();
    await loadSettings();
    if (cmp.open) { readForm(); renderComposer(); }
    if (setBack.classList.contains("open")) renderSettings();
    const bar = document.querySelector("#pane .actionbar");
    bar?.querySelectorAll("[data-cmp]").forEach((b) => { b.textContent = t(b.dataset.cmp); });
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

  loadSettings();
  if (state.selected?.id) addThreadButtons(state.selected.id);
  const hash = new URLSearchParams(location.hash.slice(1));
  if (hash.get("compose")) {
    const kind = hash.get("compose");
    openComposer(["reply", "forward"].includes(kind) ? kind : "new", { itemId: hash.get("thread") ? decodeURIComponent(hash.get("thread")) : "" });
  }
})();
