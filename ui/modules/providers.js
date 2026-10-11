/* Unified inbox accounts: sidebar account filter with driver badge, counts and
   credential hints (GET /api/providers); account tag on every mail row. */
(() => {
  "use strict";
  const S = {
    zh: {
      all: "所有收件匣", unread: "未讀", total: "封", readonly: "唯讀",
      notConfigured: "已不在 accounts.json，只剩本機快取",
      missing: "缺密碼：請 export 環境變數 ", plaintext: "accounts.json 不可放明文密碼，請改用 password_env",
      lastErr: "上次同步失敗：", lastOk: "上次同步抓到 ",
      check: "測試連線", checking: "連線中…", checkFail: "連線失敗：",
      drivers: { demo: "示範", gog: "Gmail", gsk: "Outlook", imap: "IMAP", icloud: "iCloud" },
    },
    en: {
      all: "All inboxes", unread: "unread", total: "mails", readonly: "read-only",
      notConfigured: "No longer in accounts.json; local cache only",
      missing: "Missing password: export env var ", plaintext: "No plaintext password in accounts.json; use password_env",
      lastErr: "Last sync failed: ", lastOk: "Last sync fetched ",
      check: "Test connection", checking: "Connecting…", checkFail: "Connection failed: ",
      drivers: { demo: "Demo", gog: "Gmail", gsk: "Outlook", imap: "IMAP", icloud: "iCloud" },
    },
  };
  const isZh = () => document.documentElement.lang.startsWith("zh");
  const t = (k) => S[isZh() ? "zh" : "en"][k];
  const notify = (msg, isErr) => (typeof toast === "function" ? toast(msg, isErr) : console.log(msg));
  const box = document.getElementById("accounts");
  if (!box || typeof state !== "object" || window.__tpiProviders) return;
  window.__tpiProviders = true;

  const css = document.createElement("style");
  css.textContent = `
    .acct .tpi-acct { display: block; }
    .acct .tpi-acct .top { display: flex; align-items: center; gap: 6px; }
    .acct .tpi-acct .nm { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink); }
    .acct .tpi-acct .sub { display: block; font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .acct .tpi-acct .warn { display: block; font-size: 11px; color: var(--need); white-space: normal; overflow-wrap: anywhere; }
    .tpi-badge { font-size: 10px; border: 1px solid var(--line); border-radius: 999px; padding: 0 6px; color: var(--accent2); flex: none; }
    .tpi-n { font-size: 11px; color: var(--accent); flex: none; }
    .tpi-check { display: inline-block; cursor: pointer; color: var(--accent); font-size: 11px; text-decoration: underline; }
    .row .meta .tpi-tag { display: inline-block; max-width: 110px; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; border: 1px solid var(--line); border-radius: 999px; padding: 0 6px; font-size: 10.5px; color: var(--accent2); }`;
  document.head.appendChild(css);

  let accounts = [];
  const byEmail = () => Object.fromEntries(accounts.map((a) => [a.email, a]));
  const badge = (a) => {
    const key = a.platform === "icloud" ? "icloud" : (a.driver || a.platform);
    return S[isZh() ? "zh" : "en"].drivers[key] || key || "?";
  };
  const tagText = (a) => (a.label === badge(a) ? a.label : `${a.label} · ${badge(a)}`);
  const el = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };

  function pick(email) {
    state.account = email;
    render();
    if (typeof setView === "function" && state.view !== "mail") setView("mail");
    else if (typeof loadInbox === "function") loadInbox();
  }

  function warnings(a) {
    const out = [];
    if (!a.configured) out.push(t("notConfigured"));
    if (a.credentials === "missing") out.push(t("missing") + a.password_env);
    else if (a.credentials === "plaintext_rejected") out.push(t("plaintext"));
    else if (a.last_sync?.error) out.push(t("lastErr") + a.last_sync.error);
    return out;
  }

  async function checkConn(a, btn) {
    if (btn.dataset.busy) return;
    btn.dataset.busy = "1"; btn.textContent = t("checking");
    try {
      const r = await fetch("/api/providers/check", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: a.email, lang: document.documentElement.lang }),
      });
      const d = await r.json();
      if (!d.ok) throw new Error(d.error || String(r.status));
      notify(d.note);
    } catch (e) {
      notify(t("checkFail") + e.message, true);
    } finally {
      delete btn.dataset.busy; btn.textContent = t("check");
    }
  }

  function render() {
    box.innerHTML = "";
    const all = el("button", "tpi-acct");
    const allTop = el("span", "top");
    allTop.append(el("span", "nm", t("all")));
    const sum = accounts.reduce((n, a) => n + (a.unread || 0), 0);
    if (sum) allTop.append(el("span", "tpi-n", String(sum)));
    all.append(allTop);
    all.classList.toggle("on", !state.account);
    all.onclick = () => pick("");
    box.append(all);
    for (const a of accounts) {
      const b = el("button", "tpi-acct");
      b.dataset.account = a.email;
      const top = el("span", "top");
      top.append(el("span", "nm", a.label || a.email), el("span", "tpi-badge", badge(a)));
      if (a.unread) top.append(el("span", "tpi-n", String(a.unread)));
      b.append(top);
      const sub = el("span", "sub muted", `${a.email} · ${a.total || 0} ${t("total")}`);
      b.append(sub);
      const warn = warnings(a);
      if (warn.length) b.append(el("span", "warn", warn.join(" · ")));
      if (a.driver === "imap" && a.configured) {
        const c = el("span", "tpi-check", t("check"));
        c.setAttribute("role", "button");
        c.tabIndex = 0;
        c.onclick = (e) => { e.stopPropagation(); checkConn(a, c); };
        c.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); checkConn(a, c); } };
        b.append(c);
      }
      b.title = [a.email, a.host, a.readonly ? t("readonly") : "",
        a.last_sync && !a.last_sync.error ? t("lastOk") + a.last_sync.count : ""].filter(Boolean).join("\n");
      b.classList.toggle("on", a.email === state.account);
      b.onclick = () => pick(a.email);
      box.append(b);
    }
  }

  function tagRows() {
    const map = byEmail();
    document.querySelectorAll("#list .row[data-i]").forEach((row) => {
      const mail = state.emails?.[parseInt(row.dataset.i, 10)];
      const meta = row.querySelector(".meta");
      if (!mail || !meta || meta.querySelector(".tpi-tag")) return;
      const last = meta.lastChild;
      const a = map[mail.account];
      const tag = el("span", "tpi-tag", a ? tagText(a) : (mail.account || "").split("@")[0]);
      tag.title = mail.account || "";
      if (last && last.nodeType === Node.TEXT_NODE) last.replaceWith(tag); else meta.append(tag);
    });
  }

  async function refresh() {
    try {
      const d = await (await fetch("/api/providers?lang=" + encodeURIComponent(document.documentElement.lang))).json();
      accounts = d.accounts || [];
    } catch { return; }
    render(); tagRows();
  }

  const coreLoadInbox = window.loadInbox;
  if (typeof coreLoadInbox === "function") {
    window.loadInbox = async (...args) => { const out = await coreLoadInbox(...args); tagRows(); return out; };
  }
  const coreRefreshCounts = window.refreshCounts;
  if (typeof coreRefreshCounts === "function") {
    window.refreshCounts = async (...args) => { const out = await coreRefreshCounts(...args); refresh(); return out; };
  }
  window.renderAccounts = render;

  const want = new URLSearchParams(location.hash.slice(1)).get("account");
  if (want != null) state.account = want;
  new MutationObserver(() => { render(); document.querySelectorAll("#list .tpi-tag").forEach((n) => n.remove()); tagRows(); })
    .observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
  refresh().then(() => { if (want != null && typeof loadInbox === "function") loadInbox(); });
})();
