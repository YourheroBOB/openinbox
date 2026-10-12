/* Mail operations: folders (Inbox / Starred / Drafts / Sent / Archive / Trash), star /
   archive / trash / move (local state), mark all read across accounts, print view,
   BYO-agent inline translation, new-mail notifications (/api/new-since polling),
   account settings (accounts.json) and per-account signatures. */
(() => {
  "use strict";
  const S = {
    zh: {
      fnames: { inbox: "收件匣", starred: "已加星號", drafts: "草稿", sent: "寄件備份", archive: "封存", trash: "垃圾桶" },
      folders: "資料夾", allRead: "✓ 全部標為已讀", allReadConfirm: "把所有帳號的未讀信都標為已讀？（只改本機狀態）",
      allReadOne: "把這個帳號的未讀信都標為已讀？（只改本機狀態）",
      notifyOn: "🔔 新信通知：開", notifyOff: "🔕 新信通知：關", notifyDenied: "瀏覽器拒絕通知權限，改用頁面內提示",
      notifyUnsupported: "這個瀏覽器不支援 Notification API，改用頁面內提示", newMail: "新信", newMailN: "封新信",
      star: "☆ 加星號", unstar: "★ 取消星號", archive: "封存", trash: "刪除", restore: "移回收件匣",
      purge: "永久刪除（本機）", purgeConfirm: "從本機所有資料夾隱藏這封信？遠端信箱不受影響。",
      emptyTrash: "清空垃圾桶", emptyTrashConfirm: "清空垃圾桶？信會從本機所有資料夾隱藏，遠端信箱不受影響。",
      moveTo: "移到…", print: "🖨 列印／PDF", translate: "譯 翻譯", translating: "翻譯中…", hideTr: "隱藏譯文",
      trTitle: "譯文", noLlm: "未接 LLM", failed: "失敗：", to: "給 ", empty: "這個資料夾沒有信。",
      emptyDrafts: "草稿是空的。按 n 開新信。", starTitle: "加／取消星號（s）",
      keys: "e 封存 · s 星號 · # 刪除",
      navSettings: "帳號設定", settingsTitle: "帳號設定", settingsHint: "新增、移除、排序帳號都寫進 accounts.json；第一個是主帳號。密碼永遠不寫進檔案。",
      mode: "模式", primary: "主帳號", makePrimary: "設為主帳號", up: "↑", down: "↓", remove: "移除",
      removeConfirm: "從 accounts.json 移除這個帳號？本機快取的信會保留。",
      signature: "簽名", sigPlaceholder: "每個帳號自己的簽名；開新信時自動附上", saveSig: "儲存簽名",
      importSig: "從檔案匯入…", clearSig: "清除", sigHint: "可匯入 .txt、.md、.sig 或 .html（HTML 會轉成純文字）。",
      addTitle: "新增帳號", email: "信箱", label: "名稱", driver: "連線方式", host: "IMAP 主機", port: "埠",
      passwordEnv: "密碼環境變數（password_env）", addPrimary: "設為主帳號", add: "新增",
      noPassword: "IMAP 密碼不寫進 accounts.json：先 export 環境變數，這裡只填變數名稱。",
      drivers: { demo: "示範資料", gog: "Gmail（gog）", gsk: "Outlook（gsk）", imap: "IMAP 唯讀" },
      insertSig: "✍ 附上簽名", noSig: "這個寄件帳號還沒有簽名，到「帳號設定」設定。", saved: "已儲存",
      noAccounts: "accounts.json 還沒有帳號。",
    },
    en: {
      fnames: { inbox: "Inbox", starred: "Starred", drafts: "Drafts", sent: "Sent", archive: "Archive", trash: "Trash" },
      folders: "Folders", allRead: "✓ Mark all read", allReadConfirm: "Mark every unread mail in all accounts as read? (local state only)",
      allReadOne: "Mark every unread mail in this account as read? (local state only)",
      notifyOn: "🔔 New-mail alerts: on", notifyOff: "🔕 New-mail alerts: off", notifyDenied: "The browser blocked notifications; using in-page alerts",
      notifyUnsupported: "No Notification API in this browser; using in-page alerts", newMail: "New mail", newMailN: "new messages",
      star: "☆ Star", unstar: "★ Unstar", archive: "Archive", trash: "Delete", restore: "Move to Inbox",
      purge: "Delete forever (local)", purgeConfirm: "Hide this message from every folder on this machine? The remote mailbox is untouched.",
      emptyTrash: "Empty trash", emptyTrashConfirm: "Empty the trash? Messages are hidden from every local folder; the remote mailbox is untouched.",
      moveTo: "Move to…", print: "🖨 Print / PDF", translate: "Translate", translating: "Translating…", hideTr: "Hide translation",
      trTitle: "Translation", noLlm: "No LLM wired", failed: "Failed: ", to: "To ", empty: "Nothing in this folder.",
      emptyDrafts: "No drafts. Press n to write one.", starTitle: "Star / unstar (s)",
      keys: "e archive · s star · # delete",
      navSettings: "Account settings", settingsTitle: "Account settings", settingsHint: "Adding, removing and reordering accounts writes accounts.json; the first one is primary. Passwords are never written to the file.",
      mode: "Mode", primary: "Primary", makePrimary: "Make primary", up: "↑", down: "↓", remove: "Remove",
      removeConfirm: "Remove this account from accounts.json? Its cached mail stays on this machine.",
      signature: "Signature", sigPlaceholder: "Each account's own signature; added to new mail automatically", saveSig: "Save signature",
      importSig: "Import from file…", clearSig: "Clear", sigHint: "Import a .txt, .md, .sig or .html file (HTML becomes plain text).",
      addTitle: "Add account", email: "Email", label: "Name", driver: "Driver", host: "IMAP host", port: "Port",
      passwordEnv: "Password env var (password_env)", addPrimary: "Make primary", add: "Add",
      noPassword: "IMAP passwords never go into accounts.json: export an environment variable and enter only its name here.",
      drivers: { demo: "Demo data", gog: "Gmail (gog)", gsk: "Outlook (gsk)", imap: "IMAP read-only" },
      insertSig: "✍ Add signature", noSig: "This From account has no signature yet; set one in Account settings.", saved: "Saved",
      noAccounts: "No accounts in accounts.json yet.",
    },
  };
  const isZh = () => document.documentElement.lang.startsWith("zh");
  const t = (k) => S[isZh() ? "zh" : "en"][k] ?? k;
  const langParam = () => (isZh() ? "zh-Hant" : "en");
  const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const notify = (msg, isErr) => (typeof toast === "function" ? toast(msg, isErr) : console.log(msg));
  const getJSON = async (path) => {
    const r = await fetch(path);
    const d = await r.json();
    if (!r.ok && d.error) throw new Error(d.error);
    return d;
  };
  const postJSON = async (path, body) => {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: langParam(), ...body }) });
    const d = await r.json();
    if (!r.ok || d.ok === false && d.error) throw new Error(d.error || String(r.status));
    return d;
  };
  const list = document.getElementById("list");
  const pane = document.getElementById("pane");
  const nav = document.getElementById("nav");
  const acctBox = document.getElementById("accounts");
  if (!list || !pane || !nav || !acctBox || typeof state !== "object" || window.__tpiMailops) return;
  window.__tpiMailops = true;

  const FOLDERS = ["inbox", "starred", "drafts", "sent", "archive", "trash"];
  const ICONS = { inbox: "📥", starred: "★", drafts: "✎", sent: "➤", archive: "🗄", trash: "🗑" };
  const mo = {
    folder: localStorage.getItem("tpi-mailops-folder") || "inbox", folders: [], seq: 0, accounts: [], mode: "demo",
    cursor: null, notify: localStorage.getItem("tpi-mailops-notify") === "1", languages: [],
    target: localStorage.getItem("tpi-mailops-target") || "", item: null,
  };
  if (!FOLDERS.includes(mo.folder)) mo.folder = "inbox";

  const css = document.createElement("style");
  css.textContent = `
    .tmo-folders button { font-size: 13px; }
    .tmo-folders .ic { display: inline-block; width: 18px; color: var(--muted); }
    .tmo-tools { display: flex; flex-direction: column; gap: 4px; margin-top: 6px; }
    .tmo-tools button { width: 100%; text-align: left; background: transparent; border: 1px solid var(--line); color: var(--muted); padding: 5px 9px; border-radius: 8px; font-size: 12px; }
    .tmo-tools button:hover { color: var(--ink); border-color: var(--accent); }
    .tmo-tools button.on { color: var(--accent2); border-color: var(--accent); }
    .row .tmo-star { margin-left: auto; flex: none; color: var(--muted); padding: 0 4px; font-size: 14px; line-height: 1; cursor: pointer; }
    .row .tmo-star.on { color: var(--accent2); }
    .row .tmo-star:hover { color: var(--ink); }
    .tmo-fhead { display: flex; align-items: center; gap: 8px; padding: 7px 14px; border-bottom: 1px solid var(--line); color: var(--muted); font-size: 12px; }
    .tmo-fhead b { color: var(--ink); font-weight: 600; }
    .tmo-fhead .sp { flex: 1; }
    .tmo-fhead button { background: transparent; border: 1px solid var(--line); border-radius: 7px; color: var(--muted); font-size: 11.5px; padding: 2px 8px; }
    .tmo-fhead button:hover { color: var(--ink); border-color: var(--accent); }
    .actionbar .tmo-sep { width: 1px; background: var(--line); margin: 0 2px; }
    .actionbar select.tmo-sel { background: var(--panel); border: 1px solid var(--line); border-radius: 9px; padding: 5px 8px; font-size: 12.5px; }
    .tmo-tr { border: 1px solid var(--line); border-left: 3px solid var(--accent); border-radius: 10px; padding: 10px 14px; margin: 0 0 16px; background: var(--panel); }
    .tmo-tr.warn { border-left-color: var(--need); }
    .tmo-tr .hd { display: flex; gap: 8px; align-items: center; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    .tmo-tr .hd .x { margin-left: auto; background: none; border: none; color: var(--muted); font-size: 12px; text-decoration: underline; }
    .tmo-tr .txt { white-space: pre-wrap; word-break: break-word; line-height: 1.7; font-size: 14px; }
    .tmo-set .acc { border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; margin-bottom: 12px; background: var(--panel); }
    .tmo-set .acc .top { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .tmo-set .acc .nm { font-weight: 650; }
    .tmo-set .badge2 { font-size: 10.5px; border: 1px solid var(--line); border-radius: 999px; padding: 0 7px; color: var(--accent2); }
    .tmo-set .badge2.pri { border-color: var(--accent); color: var(--accent); }
    .tmo-set .acc .acts { margin-left: auto; display: flex; gap: 4px; }
    .tmo-set .acc .acts .btn { font-size: 11.5px; padding: 3px 9px; }
    .tmo-set textarea { width: 100%; min-height: 84px; margin-top: 8px; background: #171410; border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; outline: none; resize: vertical; line-height: 1.6; }
    .tmo-set .sigacts { display: flex; gap: 6px; margin-top: 6px; align-items: center; flex-wrap: wrap; }
    .tmo-set .sigacts .btn { font-size: 12px; padding: 4px 10px; }
    .tmo-set .form { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .tmo-set .form label { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--muted); }
    .tmo-set .form input, .tmo-set .form select { background: #171410; border: 1px solid var(--line); border-radius: 8px; padding: 7px 9px; outline: none; color: var(--ink); }
    .tmo-set .form .imap { display: contents; }
    .tmo-set .form .imap.off { display: none; }
    .tmo-set .form .full { grid-column: 1 / -1; }
    .tmo-set h3 { font-size: 14px; margin: 18px 0 10px; }`;
  document.head.appendChild(css);

  /* ── sidebar: folders, mark all read, notifications ── */
  const side = document.createElement("div");
  side.id = "tmoSide";
  side.innerHTML = `<div class="label" data-tmo="folders"></div><div class="nav tmo-folders" id="tmoFolders"></div>
    <div class="tmo-tools"><button id="tmoAllRead"></button><button id="tmoNotify"></button></div>`;
  acctBox.parentElement.parentElement.insertBefore(side, acctBox.parentElement);
  const folderBox = side.querySelector("#tmoFolders");

  function folderName(id) {
    return mo.folders.find((f) => f.id === id)?.name || t("fnames")[id] || id;
  }

  function renderFolders() {
    side.querySelector("[data-tmo=folders]").textContent = t("folders");
    const byId = Object.fromEntries(mo.folders.map((f) => [f.id, f]));
    folderBox.innerHTML = FOLDERS.map((id) => {
      const f = byId[id] || { total: 0, unread: 0 };
      const n = id === "inbox" ? f.unread : (id === "drafts" || id === "starred" ? f.total : 0);
      const on = state.view === "mail" && mo.folder === id;
      return `<button data-folder="${id}" class="${on ? "on" : ""}"><span><span class="ic">${ICONS[id]}</span>${h(folderName(id))}</span><span class="cnt">${n || ""}</span></button>`;
    }).join("");
    side.querySelector("#tmoAllRead").textContent = t("allRead");
    const nb = side.querySelector("#tmoNotify");
    nb.textContent = mo.notify ? t("notifyOn") : t("notifyOff");
    nb.classList.toggle("on", mo.notify);
  }

  async function refreshFolders() {
    const q = new URLSearchParams({ lang: langParam() });
    if (state.account) q.set("account", state.account);
    try { mo.folders = (await getJSON("/api/mailops/folders?" + q)).folders || []; } catch { return; }
    renderFolders();
  }

  folderBox.onclick = (e) => {
    const b = e.target.closest("[data-folder]"); if (!b) return;
    mo.folder = b.dataset.folder;
    localStorage.setItem("tpi-mailops-folder", mo.folder);
    state.selected = null;
    if (state.view !== "mail" && typeof setView === "function") window.setView("mail");
    else window.loadInbox();
    renderFolders();
  };

  side.querySelector("#tmoAllRead").onclick = async () => {
    if (!window.confirm(state.account ? t("allReadOne") : t("allReadConfirm"))) return;
    try {
      const d = await postJSON("/api/mailops/mark-all-read", { account: state.account || "" });
      notify(d.note);
    } catch (e) { notify(t("failed") + e.message, true); return; }
    reloadAll();
  };

  side.querySelector("#tmoNotify").onclick = async () => {
    if (!mo.notify) {
      if (!("Notification" in window)) notify(t("notifyUnsupported"));
      else if (Notification.permission !== "granted") {
        let p = "denied";
        try { p = await Notification.requestPermission(); } catch {}
        if (p !== "granted") notify(t("notifyDenied"));
      }
    }
    mo.notify = !mo.notify;
    localStorage.setItem("tpi-mailops-notify", mo.notify ? "1" : "0");
    renderFolders();
  };

  function reloadAll() {
    if (state.view === "mail") window.loadInbox();
    if (typeof refreshCounts === "function") window.refreshCounts();
    else refreshFolders();
  }

  /* ── mail list: the folder view replaces the core inbox list ── */
  const shortDT = (s) => (typeof fmtDT === "function" ? fmtDT(s) : String(s || "")).slice(5, 16);
  const who = (addr) => (typeof fromLabel === "function" ? fromLabel(addr) : String(addr || ""));

  function rowHtml(e, i) {
    const peer = mo.folder === "sent" || mo.folder === "drafts" || e.folder === "sent" || e.kind === "draft"
      ? t("to") + who(e.to_addr || "—") : who(e.from_addr);
    const avatar = typeof avatarHtml === "function" ? avatarHtml(e.kind === "draft" || e.folder === "sent" ? e.to_addr : e.from_addr) : "";
    const star = e.kind === "draft" ? "" : `<span class="tmo-star ${e.starred ? "on" : ""}" data-star title="${h(t("starTitle"))}">${e.starred ? "★" : "☆"}</span>`;
    return `<div class="row ${e.unread ? "unread" : ""}" data-id="${h(e.id)}" data-i="${i}">
      <div class="dot ${h(e.category)}"></div>
      <div>
        <div class="rowline">${avatar}<span class="from">${h(peer)}</span>${star}</div>
        <div class="subj">${h(e.subject || "—")}</div>
      </div>
      <div class="meta">${h(shortDT(e.date_raw))}<br>${h((e.account || "").split("@")[0])}</div>
    </div>`;
  }

  function folderHead(count) {
    const extra = mo.folder === "trash" && count ? `<button data-do="emptyTrash">${h(t("emptyTrash"))}</button>` : "";
    return `<div class="tmo-fhead"><b>${ICONS[mo.folder]} ${h(folderName(mo.folder))}</b><span>${count}</span><span class="sp"></span>${extra}<span>${h(t("keys"))}</span></div>`;
  }

  const coreLoadInbox = window.loadInbox;
  window.loadInbox = async (...args) => {
    if (state.view !== "mail") return typeof coreLoadInbox === "function" ? coreLoadInbox(...args) : undefined;
    const q = new URLSearchParams({ folder: mo.folder, limit: "120", category: state.category || "all" });
    if (state.account) q.set("account", state.account);
    const qBox = document.getElementById("q");
    const text = state.q || (qBox ? qBox.value.trim() : "");
    if (text) q.set("q", text);
    const seq = ++mo.seq;
    let d;
    try { d = await getJSON("/api/mailops/list?" + q); }
    catch (e) { list.innerHTML = `<div class="empty">${h(t("failed") + e.message)}</div>`; return; }
    if (seq !== mo.seq || state.view !== "mail") return;
    state.emails = d.emails || [];
    state.selIdx = -1;
    const emptyMsg = mo.folder === "drafts" ? t("emptyDrafts") : t("empty");
    list.innerHTML = folderHead(state.emails.length) + (state.emails.map(rowHtml).join("") || `<div class="empty">${h(emptyMsg)}</div>`);
    list.onclick = onListClick;
    refreshFolders();
  };

  function onListClick(ev) {
    if (ev.target.closest("[data-do=emptyTrash]")) { emptyTrash(); return; }
    const row = ev.target.closest(".row[data-i]"); if (!row) return;
    const mail = state.emails[parseInt(row.dataset.i, 10)]; if (!mail) return;
    if (ev.target.closest("[data-star]")) { ev.stopPropagation(); act([mail.id], mail.starred ? "unstar" : "star"); return; }
    state.selIdx = parseInt(row.dataset.i, 10);
    list.querySelectorAll(".row").forEach((r) => r.classList.toggle("on", r === row));
    if (mail.kind === "draft") return openDraftRow(mail);
    window.openThread(mail.id);
  }

  function openDraftRow(mail) {
    state.drafts = state.emails.filter((e) => e.kind === "draft").map((e) => ({ ...e, id: e.draft_id, kind: e.draft_kind }));
    const idx = state.drafts.findIndex((d) => d.id === mail.draft_id);
    if (typeof window.showDraft === "function" && idx >= 0) window.showDraft(idx);
  }

  async function emptyTrash() {
    if (!window.confirm(t("emptyTrashConfirm"))) return;
    try { notify((await postJSON("/api/mailops/empty-trash", { account: state.account || "" })).note); }
    catch (e) { notify(t("failed") + e.message, true); }
    reloadAll();
  }

  async function act(ids, action, folder) {
    let d;
    try { d = await postJSON("/api/mailops/action", { ids, action, folder: folder || "" }); }
    catch (e) { notify(t("failed") + e.message, true); return null; }
    const leaves = ["archive", "trash", "move", "purge", "restore"].includes(action);
    const sel = state.selected?.id;
    await window.loadInbox();
    if (typeof refreshCounts === "function") window.refreshCounts();
    if (sel && ids.includes(sel)) {
      if (leaves) notify(d.note);
      decorateThread(sel);
    }
    return d;
  }

  window.toggleUnread = async (id, unread) => { await act([id], unread ? "unread" : "read"); };

  /* ── thread pane: actions, print, translate ── */
  async function openVirtual(id) {
    pane.innerHTML = "<p class='muted'>…</p>";
    let d;
    try { d = await getJSON("/api/mailops/item?id=" + encodeURIComponent(id) + "&lang=" + langParam()); }
    catch (e) { pane.innerHTML = `<p class="muted">${h(e.message)}</p>`; return; }
    state.selected = d;
    pane.innerHTML = `
      <h2 class="mh">${h(d.subject || "—")}</h2>
      <p class="muted" style="margin:0">${h(t("to"))}${h(d.to_addr || "—")}${d.cc_addr ? " · Cc " + h(d.cc_addr) : ""}　·　${h(String(d.date_raw || "").slice(0, 26))}　·　${h(d.account || "")}</p>
      <div class="actionbar"></div>
      <div class="msg"><div class="msghead">${typeof avatarHtml === "function" ? avatarHtml(d.from_addr) : ""}<span class="who">${h(who(d.from_addr))}</span></div>
      <div class="body">${h(d.body_text || d.snippet || "—")}</div></div>`;
  }

  const coreOpenThread = window.openThread;
  window.openThread = async (id, ...rest) => {
    const row = (state.emails || []).find((e) => e.id === id);
    let out;
    if (row && row.source === "sent_fixture") out = await openVirtual(id);
    else {
      out = typeof coreOpenThread === "function" ? await coreOpenThread(id, ...rest) : undefined;
      if (row && row.unread) {
        row.unread = false;
        postJSON("/api/mailops/action", { ids: [id], action: "read" }).then(() => refreshFolders()).catch(() => {});
      }
    }
    decorateThread(id);
    return out;
  };

  async function decorateThread(id) {
    let item;
    try { item = await getJSON("/api/mailops/item?id=" + encodeURIComponent(id)); } catch { return; }
    const bar = pane.querySelector(".actionbar");
    if (!bar || state.selected?.id !== id) return;
    mo.item = item;
    bar.querySelectorAll("[data-mo]").forEach((n) => n.remove());
    const mk = (kind, label, cls) => {
      const b = document.createElement("button");
      b.className = "btn " + (cls || "");
      b.dataset.mo = kind;
      b.textContent = label;
      return b;
    };
    const sep = document.createElement("span");
    sep.className = "tmo-sep"; sep.dataset.mo = "sep";
    const nodes = [sep, mk("star", item.starred ? t("unstar") : t("star"))];
    if (item.folder === "trash") nodes.push(mk("restore", t("restore")), mk("purge", t("purge"), "ghost"));
    else {
      if (item.folder !== "archive") nodes.push(mk("archive", t("archive")));
      else nodes.push(mk("restore", t("restore")));
      nodes.push(mk("trash", t("trash")));
    }
    const move = document.createElement("select");
    move.className = "tmo-sel"; move.dataset.mo = "move";
    move.innerHTML = `<option value="">${h(t("moveTo"))}</option>` + ["inbox", "archive", "trash"]
      .filter((f) => f !== item.folder).map((f) => `<option value="${f}">${h(folderName(f))}</option>`).join("");
    nodes.push(move, mk("print", t("print")));
    const lang = document.createElement("select");
    lang.className = "tmo-sel"; lang.dataset.mo = "lang";
    const target = mo.target || (isZh() ? "zh-Hant" : "en");
    lang.innerHTML = (mo.languages.length ? mo.languages : [{ id: "zh-Hant", name: "繁體中文" }, { id: "en", name: "English" }])
      .map((l) => `<option value="${h(l.id)}" ${l.id === target ? "selected" : ""}>${h(l.name)}</option>`).join("");
    nodes.push(mk("translate", t("translate")), lang);
    bar.append(...nodes);
    bar.querySelectorAll("button[data-mo]").forEach((b) => { b.onclick = () => threadAction(b.dataset.mo, id, b); });
    move.onchange = () => { if (move.value) act([id], "move", move.value); };
    lang.onchange = () => { mo.target = lang.value; localStorage.setItem("tpi-mailops-target", mo.target); };
  }

  async function threadAction(kind, id, btn) {
    const item = mo.item && mo.item.id === id ? mo.item : null;
    if (kind === "star") return act([id], item?.starred ? "unstar" : "star");
    if (kind === "archive" || kind === "trash" || kind === "restore") return act([id], kind);
    if (kind === "purge") { if (window.confirm(t("purgeConfirm"))) act([id], "purge"); return; }
    if (kind === "print") {
      window.open(`/mailops/print?id=${encodeURIComponent(id)}&lang=${langParam()}&auto=1`, "_blank", "noopener");
      return;
    }
    if (kind === "translate") return translate(id, btn);
  }

  async function translate(id, btn) {
    const old = pane.querySelector(".tmo-tr");
    if (old) { old.remove(); btn.textContent = t("translate"); return; }
    const target = pane.querySelector("select[data-mo=lang]")?.value || mo.target || (isZh() ? "zh-Hant" : "en");
    btn.disabled = true; btn.textContent = t("translating");
    let d;
    try {
      const r = await fetch("/api/mailops/translate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, target, lang: langParam() }) });
      d = await r.json();
      if (!r.ok) throw new Error(d.error || String(r.status));
    } catch (e) { notify(t("failed") + e.message, true); btn.disabled = false; btn.textContent = t("translate"); return; }
    btn.disabled = false;
    if (state.selected?.id !== id) return;
    const box = document.createElement("div");
    box.className = "tmo-tr" + (d.ok ? "" : " warn");
    if (d.ok) {
      box.innerHTML = `<div class="hd"><span>譯 ${h(t("trTitle"))} · ${h(d.target_name)} · ${h(d.driver)}</span><button class="x">${h(t("hideTr"))}</button></div>
        ${d.subject ? `<div style="font-weight:650;margin-bottom:4px">${h(d.subject)}</div>` : ""}<div class="txt">${h(d.text)}</div>
        <div class="muted" style="font-size:11.5px;margin-top:6px">${h(d.note || "")}</div>`;
      btn.textContent = t("hideTr");
    } else {
      box.innerHTML = `<div class="hd"><span>⚠ ${h(d.needs_agent ? t("noLlm") : t("failed") + (d.error || ""))}</span><button class="x">✕</button></div><div class="txt">${h(d.note || d.error || "")}</div>`;
      btn.textContent = t("translate");
    }
    box.querySelector(".x").onclick = () => { box.remove(); btn.textContent = t("translate"); };
    const msg = pane.querySelector(".msg");
    if (msg) msg.before(box); else pane.append(box);
  }

  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
    if (document.getElementById("modalback")?.classList.contains("open") || document.getElementById("tpiCmpBack")?.classList.contains("open")) return;
    const id = state.selected?.id;
    if (state.view !== "mail" || !id || !mo.item || mo.item.id !== id) return;
    if (e.key === "e") { e.preventDefault(); act([id], mo.item.folder === "archive" ? "restore" : "archive"); }
    else if (e.key === "s") { e.preventDefault(); act([id], mo.item.starred ? "unstar" : "star"); }
    else if (e.key === "#") { e.preventDefault(); act([id], mo.item.folder === "trash" ? "purge" : "trash"); }
  });

  /* ── new-mail notifications: /api/new-since polling ── */
  async function poll() {
    const q = new URLSearchParams();
    if (mo.cursor != null) q.set("cursor", String(mo.cursor));
    let d;
    try { d = await getJSON("/api/new-since?" + q); } catch { return; }
    mo.cursor = d.cursor;
    if (!d.count) return;
    const first = d.emails[d.emails.length - 1] || {};
    if (mo.notify) {
      const title = d.count === 1 ? `${t("newMail")} · ${who(first.from_addr)}` : `${d.count} ${t("newMailN")}`;
      const body = d.count === 1 ? first.subject || "" : d.emails.slice(-3).map((e) => "· " + (e.subject || "—")).join("\n");
      if ("Notification" in window && Notification.permission === "granted") {
        try {
          const n = new Notification(title, { body, tag: "tpi-new-" + d.cursor });
          n.onclick = () => { window.focus(); if (d.count === 1 && first.id) window.openThread(first.id); n.close(); };
        } catch { notify(title + " — " + body); }
      } else notify(title + " — " + body);
    }
    reloadAll();
  }
  poll();
  setInterval(poll, Math.max(5000, parseInt(localStorage.getItem("tpi-mailops-poll-ms") || "30000", 10) || 30000));

  /* ── account settings view ── */
  const navBtn = document.createElement("button");
  navBtn.dataset.view = "mailops-accounts";
  const navLabel = document.createElement("span");
  const navCnt = document.createElement("span");
  navCnt.className = "cnt";
  navBtn.append(navLabel, navCnt);
  nav.appendChild(navBtn);

  async function loadAccounts() {
    try {
      const d = await getJSON("/api/mailops/accounts");
      mo.accounts = d.accounts || [];
      mo.mode = d.mode;
      navCnt.textContent = mo.accounts.length || "";
    } catch {}
  }

  async function afterAccountChange(d) {
    if (d) { mo.accounts = d.accounts || []; mo.mode = d.mode; navCnt.textContent = mo.accounts.length || ""; }
    try { state.cfg = await getJSON("/api/accounts"); } catch {}
    if (typeof renderAccounts === "function") window.renderAccounts();
    if (typeof refreshCounts === "function") window.refreshCounts();
    if (state.view === "mailops-accounts") renderSettings();
  }

  function renderSettings() {
    const drivers = S[isZh() ? "zh" : "en"].drivers;
    list.innerHTML = mo.accounts.map((a, i) => `
      <div class="row" data-acc="${i}">
        <div class="dot ${a.primary ? "needs_you" : "fyi"}"></div>
        <div><div class="rowline">${typeof avatarHtml === "function" ? avatarHtml(a.email) : ""}<span class="from">${h(a.label)}</span></div>
        <div class="subj">${h(a.email)}</div></div>
        <div class="meta">${a.primary ? h(t("primary")) + "<br>" : ""}${h(drivers[a.driver] || a.driver)}</div>
      </div>`).join("") || `<div class="empty">${h(t("noAccounts"))}</div>`;
    list.onclick = (e) => {
      const row = e.target.closest("[data-acc]"); if (!row) return;
      pane.querySelector(`.acc[data-i="${row.dataset.acc}"]`)?.scrollIntoView({ block: "start", behavior: "smooth" });
    };
    const n = mo.accounts.length;
    pane.innerHTML = `<div class="tmo-set">
      <h2 class="mh">${h(t("settingsTitle"))}</h2>
      <p class="muted" style="margin:0 0 14px">${h(t("settingsHint"))} · ${h(t("mode"))}: <code>${h(mo.mode)}</code></p>
      ${mo.accounts.map((a, i) => `
        <div class="acc" data-i="${i}" data-email="${h(a.email)}">
          <div class="top">
            <span class="nm">${h(a.label)}</span><span class="muted">${h(a.email)}</span>
            <span class="badge2">${h(drivers[a.driver] || a.driver)}</span>
            ${a.primary ? `<span class="badge2 pri">${h(t("primary"))}</span>` : ""}
            <span class="acts">
              ${a.primary ? "" : `<button class="btn" data-a="primary">${h(t("makePrimary"))}</button>`}
              <button class="btn ghost" data-a="up" ${i === 0 ? "disabled" : ""}>${t("up")}</button>
              <button class="btn ghost" data-a="down" ${i === n - 1 ? "disabled" : ""}>${t("down")}</button>
              <button class="btn ghost" data-a="remove">${h(t("remove"))}</button>
            </span>
          </div>
          <textarea data-sig placeholder="${h(t("sigPlaceholder"))}" aria-label="${h(t("signature"))}">${h(a.signature)}</textarea>
          <div class="sigacts">
            <button class="btn primary" data-a="saveSig">${h(t("saveSig"))}</button>
            <button class="btn" data-a="importSig">${h(t("importSig"))}</button>
            <button class="btn ghost" data-a="clearSig">${h(t("clearSig"))}</button>
            <input type="file" data-file accept=".txt,.text,.md,.sig,.html,.htm,text/plain,text/html" hidden />
            <span class="muted" style="font-size:11.5px">${h(t("sigHint"))}</span>
          </div>
        </div>`).join("") || `<p class="muted">${h(t("noAccounts"))}</p>`}
      <h3>${h(t("addTitle"))}</h3>
      <div class="form" id="tmoAdd">
        <label>${h(t("email"))}<input name="email" type="email" placeholder="name@example.com" /></label>
        <label>${h(t("label"))}<input name="label" placeholder="Work" /></label>
        <label>${h(t("driver"))}<select name="driver">${Object.entries(drivers).map(([k, v]) => `<option value="${k}" ${k === "imap" ? "selected" : ""}>${h(v)}</option>`).join("")}</select></label>
        <label style="flex-direction:row;align-items:center;gap:6px;margin-top:18px"><input type="checkbox" name="primary" /> ${h(t("addPrimary"))}</label>
        <div class="imap">
          <label>${h(t("host"))}<input name="host" placeholder="imap.example.com" /></label>
          <label>${h(t("port"))}<input name="port" inputmode="numeric" placeholder="993" /></label>
          <label class="full">${h(t("passwordEnv"))}<input name="password_env" placeholder="TPI_IMAP_PASSWORD_WORK" /></label>
          <div class="full muted" style="font-size:11.5px">${h(t("noPassword"))}</div>
        </div>
        <div class="full"><button class="btn primary" data-a="add">${h(t("add"))}</button></div>
      </div>
    </div>`;
    const form = pane.querySelector("#tmoAdd");
    const syncImap = () => form.querySelector(".imap").classList.toggle("off", form.querySelector("[name=driver]").value !== "imap");
    form.querySelector("[name=driver]").onchange = syncImap;
    syncImap();
    pane.onclick = settingsClick;
    pane.querySelectorAll("input[data-file]").forEach((inp) => { inp.onchange = () => importSig(inp); });
  }

  async function settingsClick(e) {
    if (state.view !== "mailops-accounts") return;
    const b = e.target.closest("[data-a]"); if (!b) return;
    const card = b.closest(".acc");
    const email = card?.dataset.email;
    const a = b.dataset.a;
    try {
      if (a === "add") {
        const form = pane.querySelector("#tmoAdd");
        const v = (n) => form.querySelector(`[name=${n}]`).value.trim();
        const body = { email: v("email"), label: v("label"), driver: v("driver"), primary: form.querySelector("[name=primary]").checked };
        if (body.driver === "imap") Object.assign(body, { host: v("host"), port: v("port"), password_env: v("password_env") });
        const d = await postJSON("/api/mailops/accounts/add", body);
        notify(d.note);
        return afterAccountChange(d);
      }
      if (a === "primary") return afterAccountChange(await postJSON("/api/mailops/accounts/primary", { email }));
      if (a === "up" || a === "down") {
        const order = mo.accounts.map((x) => x.email);
        const i = order.indexOf(email), j = a === "up" ? i - 1 : i + 1;
        if (i < 0 || j < 0 || j >= order.length) return;
        [order[i], order[j]] = [order[j], order[i]];
        return afterAccountChange(await postJSON("/api/mailops/accounts/reorder", { order }));
      }
      if (a === "remove") {
        if (!window.confirm(t("removeConfirm"))) return;
        return afterAccountChange(await postJSON("/api/mailops/accounts/remove", { email }));
      }
      if (a === "saveSig" || a === "clearSig") {
        const signature = a === "clearSig" ? "" : card.querySelector("[data-sig]").value;
        const d = await postJSON("/api/mailops/signature", { email, signature });
        notify(d.note || t("saved"));
        return afterAccountChange(d);
      }
      if (a === "importSig") card.querySelector("input[data-file]").click();
    } catch (err) { notify(t("failed") + err.message, true); }
  }

  async function importSig(inp) {
    const file = inp.files && inp.files[0];
    const email = inp.closest(".acc")?.dataset.email;
    inp.value = "";
    if (!file || !email) return;
    try {
      const content = await file.text();
      const d = await postJSON("/api/mailops/signature/import", { email, filename: file.name, content });
      notify(d.note + " (" + d.imported_from + ")");
      afterAccountChange(d);
    } catch (err) { notify(t("failed") + err.message, true); }
  }

  const coreSetView = window.setView;
  if (typeof coreSetView === "function") {
    window.setView = (v, ...rest) => {
      const out = coreSetView(v, ...rest);
      if (v === "mailops-accounts") loadAccounts().then(renderSettings);
      else if (pane.onclick === settingsClick) pane.onclick = null;
      renderFolders();
      return out;
    };
  }

  /* ── composer: per-account signature ── */
  const cmpBack = document.getElementById("tpiCmpBack");
  const sigFor = (email) => (mo.accounts.find((a) => a.email === email) || {}).signature || "";
  function insertSig(force) {
    const ta = document.getElementById("tpiCmpBody");
    const from = document.getElementById("tpiCmpFrom");
    if (!ta) return;
    const sig = sigFor(from?.value || "");
    if (!sig) { if (force) notify(t("noSig"), true); return; }
    if (ta.value.includes(sig)) return;
    ta.value = (ta.value.replace(/\s+$/, "") || "") + "\n\n-- \n" + sig;
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    if (force) ta.focus();
  }
  function addSigButton() {
    const foot = cmpBack?.querySelector(".tpi-cmp-foot");
    if (!foot || foot.querySelector("[data-tmo-sig]")) return;
    const b = document.createElement("button");
    b.className = "btn ghost";
    b.dataset.tmoSig = "1";
    b.textContent = t("insertSig");
    b.onclick = () => insertSig(true);
    foot.insertBefore(b, foot.querySelector("[data-c=close]") || null);
  }
  if (cmpBack) {
    let wasOpen = cmpBack.classList.contains("open");
    new MutationObserver(() => {
      addSigButton();
      const open = cmpBack.classList.contains("open");
      if (open && !wasOpen) {
        const isNew = !String(cmpBack.querySelector(".tpi-cmp-head .muted")?.textContent || "").startsWith("#");
        if (isNew) insertSig(false);
      }
      wasOpen = open;
    }).observe(cmpBack, { attributes: true, attributeFilter: ["class"], childList: true });
  }

  /* ── language + wiring ── */
  function relabel() {
    navLabel.textContent = t("navSettings");
    refreshFolders();
    cmpBack?.querySelectorAll("[data-tmo-sig]").forEach((b) => { b.textContent = t("insertSig"); });
    getJSON("/api/mailops/languages?lang=" + langParam()).then((d) => { mo.languages = d.languages || []; }).catch(() => {});
    if (state.view === "mailops-accounts") renderSettings();
    else if (state.view === "mail") {
      window.loadInbox();
      if (state.selected?.id) decorateThread(state.selected.id);
    }
  }
  new MutationObserver(relabel).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

  const coreRefreshCounts = window.refreshCounts;
  if (typeof coreRefreshCounts === "function") {
    window.refreshCounts = async (...args) => { const out = await coreRefreshCounts(...args); refreshFolders(); return out; };
  }

  navLabel.textContent = t("navSettings");
  renderFolders();
  refreshFolders();
  loadAccounts();
  getJSON("/api/mailops/languages?lang=" + langParam()).then((d) => { mo.languages = d.languages || []; }).catch(() => {});
  const hash = new URLSearchParams(location.hash.slice(1));
  if (FOLDERS.includes(hash.get("folder"))) mo.folder = hash.get("folder");
  if (hash.get("view") === "mailops-accounts") window.setView("mailops-accounts");
  else if (state.view === "mail") window.loadInbox().then(() => { if (state.selected?.id) decorateThread(state.selected.id); });
})();
