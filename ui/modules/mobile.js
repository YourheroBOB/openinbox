/* Installable PWA + narrow-screen layout: service worker, install button, drawer nav, list ↔ detail, bottom tab bar. */
(() => {
  "use strict";
  const S = {
    zh: {
      install: "📲 安裝 App",
      installTitle: "安裝成 App：Mac、Windows、iOS、Android 都用這一個，不需要原生 App。",
      installed: "已安裝 TooPowerInbox App",
      iosHint: "在 Safari 點「分享」→「加入主畫面」即可安裝成 App。",
      menu: "選單",
      mail: "郵件",
      calendar: "日曆",
      drafts: "草稿",
      copilot: "Copilot",
      back: "‹ 返回",
      offline: "離線中：連不到 TooPowerInbox 伺服器。App 只快取介面，不離線保存信件；恢復連線後會重新載入。",
      retry: "重試",
      online: "已恢復連線",
      updated: "App 已更新，重新整理即套用新版。",
      swFail: "離線快取未啟用：",
    },
    en: {
      install: "📲 Install app",
      installTitle: "Install as an app: one app for Mac, Windows, iOS and Android, no native app needed.",
      installed: "TooPowerInbox app installed",
      iosHint: "In Safari tap Share → Add to Home Screen to install the app.",
      menu: "Menu",
      mail: "Mail",
      calendar: "Calendar",
      drafts: "Drafts",
      copilot: "Copilot",
      back: "‹ Back",
      offline: "Offline: can't reach the TooPowerInbox server. The app caches only its interface, never your mail; it reloads once you're back.",
      retry: "Retry",
      online: "Back online",
      updated: "App updated. Reload to use the new version.",
      swFail: "Offline cache not enabled: ",
    },
  };
  const isZh = () => document.documentElement.lang.startsWith("zh");
  const t = (k) => S[isZh() ? "zh" : "en"][k];
  const notify = (msg, isErr) => (typeof toast === "function" ? toast(msg, isErr) : console.log(msg));
  const el = (id) => document.getElementById(id);
  const body = document.body;
  const root = document.documentElement;
  if (window.__tpiMobile || typeof state !== "object" || !el("app")) return;
  window.__tpiMobile = true;

  const BREAKPOINT = 760;
  const css = document.createElement("style");
  css.id = "tpi-mobile-css";
  css.textContent = `
    .tpi-m-tabbar, .tpi-m-bar, .tpi-m-scrim { display: none; }
    .tpi-m-offline { display: none; position: fixed; top: calc(8px + env(safe-area-inset-top)); left: 50%; transform: translateX(-50%); z-index: 90;
      width: min(560px, calc(100vw - 20px)); align-items: center; gap: 10px; padding: 9px 12px; font-size: 12.5px; line-height: 1.45;
      background: #2e221b; border: 1px solid #6b4a3a; border-radius: 10px; color: var(--ink); box-shadow: var(--shadow); }
    .tpi-m-offline span { flex: 1; }
    body.tpi-offline .tpi-m-offline { display: flex; }
    #tpiInstallBtn[hidden] { display: none; }
    @media (max-width: ${BREAKPOINT}px) {
      :root { --tpi-tab: calc(58px + env(safe-area-inset-bottom)); }
      html, body { overscroll-behavior: none; -webkit-tap-highlight-color: transparent; }
      input, textarea, select { font-size: 16px; }
      #app, #app[class] { display: block; grid-template-columns: none !important; height: 100vh; height: 100dvh; position: relative; }
      aside { position: fixed; top: 0; bottom: 0; left: 0; width: min(86vw, 320px); z-index: 50; background: var(--bg); box-shadow: var(--shadow);
        padding-top: calc(18px + env(safe-area-inset-top)); padding-bottom: calc(12px + env(safe-area-inset-bottom));
        transform: translateX(-104%); visibility: hidden; }
      body.tpi-m-nav aside { transform: none; visibility: visible; }
      .tpi-m-scrim { position: fixed; inset: 0; background: rgba(10,8,6,.55); z-index: 45; }
      body.tpi-m-nav .tpi-m-scrim { display: block; }
      main { position: absolute; top: 0; left: 0; right: 0; bottom: var(--tpi-tab); border-right: none; }
      .toolbar { flex-wrap: wrap; padding: calc(8px + env(safe-area-inset-top)) 10px 8px; gap: 6px; }
      .toolbar input { flex: 1 1 150px; min-width: 0; }
      #cpBtn { display: none; }
      .tabs { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; padding: 8px 10px; }
      .tabs::-webkit-scrollbar { display: none; }
      .tabs button { flex: none; min-height: 34px; }
      .list, .pane { overscroll-behavior-y: contain; -webkit-overflow-scrolling: touch; }
      .row { padding: 12px 14px; min-height: 58px; }
      .btn { min-height: 38px; }
      section { position: fixed; inset: 0; z-index: 30; background: #171410;
        transform: translateX(104%); visibility: hidden; }
      body.tpi-m-detail section, body.tpi-m-cp section { transform: none; visibility: visible; }
      body.tpi-m-anim aside, body.tpi-m-anim section { transition: transform .25s ease, visibility 0s linear .25s; }
      body.tpi-m-anim.tpi-m-nav aside, body.tpi-m-anim.tpi-m-detail section, body.tpi-m-anim.tpi-m-cp section { transition: transform .25s ease; }
      .tpi-m-bar { display: flex; align-items: center; gap: 8px; padding: calc(6px + env(safe-area-inset-top)) 8px 6px; border-bottom: 1px solid var(--line); flex: none; }
      .tpi-m-bar button { background: transparent; border: none; color: var(--accent); font-size: 15px; padding: 8px 10px; min-height: 40px; }
      .pane { padding: 14px 14px calc(28px + env(safe-area-inset-bottom)); }
      .actionbar { gap: 6px; }
      #copilot { left: 0; border-left: none; padding-top: env(safe-area-inset-top); padding-bottom: env(safe-area-inset-bottom); }
      .cp-head .x { font-size: 20px; padding: 6px 12px; }
      .tpi-m-tabbar { display: flex; position: fixed; left: 0; right: 0; bottom: 0; height: var(--tpi-tab); padding-bottom: env(safe-area-inset-bottom);
        background: var(--panel); border-top: 1px solid var(--line); z-index: 40; }
      body.tpi-m-detail .tpi-m-tabbar, body.tpi-m-cp .tpi-m-tabbar { display: none; }
      .tpi-m-tabbar button { flex: 1; min-width: 0; background: transparent; border: none; color: var(--muted); display: flex; flex-direction: column;
        align-items: center; justify-content: center; gap: 2px; font-size: 11px; padding: 4px 2px; }
      .tpi-m-tabbar button .ic { font-size: 19px; line-height: 1; }
      .tpi-m-tabbar button.on { color: var(--accent); }
      #toasts { left: 12px; right: 12px; bottom: calc(var(--tpi-tab) + 10px); align-items: center; }
      .toast { max-width: 100%; }
      #modalback .modal, .tpi-back > [role="dialog"] { width: 100vw !important; max-width: 100vw !important; height: 100vh; height: 100dvh;
        max-height: 100dvh !important; border-radius: 0 !important; border: none !important; padding-top: env(safe-area-inset-top); padding-bottom: env(safe-area-inset-bottom); }
      #modalback .modal { padding: calc(14px + env(safe-area-inset-top)) 14px calc(14px + env(safe-area-inset-bottom)); }
      #modalback .modal textarea { min-height: 45vh; }
      .tpi-cmp-main { flex: 1; }
      .tpi-f { grid-template-columns: 72px minmax(0, 1fr); }
      .tpi-cmp-foot { flex-wrap: wrap; justify-content: flex-end; padding-bottom: calc(12px + env(safe-area-inset-bottom)); }
      .tpi-cmp-foot .note { flex: 1 1 100%; margin-right: 0; }
      .tcal-wk-head, .tcal-wk-allday, .tcal-wk-body { min-width: 620px; }
      .tcal-mo { grid-auto-rows: minmax(64px, 1fr); }
    }`;
  document.head.appendChild(css);

  const mq = window.matchMedia(`(max-width: ${BREAKPOINT}px)`);
  const narrow = () => mq.matches;
  const cpOpen = () => !!el("copilot")?.classList.contains("open");

  /* ── chrome: scrim, back bar, bottom tab bar, offline banner, install button ── */
  const scrim = document.createElement("div");
  scrim.className = "tpi-m-scrim";
  body.appendChild(scrim);

  const bar = document.createElement("div");
  bar.className = "tpi-m-bar";
  bar.innerHTML = `<button type="button" id="tpiBackBtn"></button>`;
  const section = el("pane")?.parentElement;
  if (section) section.insertBefore(bar, el("pane"));

  const TABS = [["mail", "✉"], ["calendar", "▦"], ["drafts", "✎"], ["copilot", "✦"], ["menu", "☰"]];
  const tabbar = document.createElement("nav");
  tabbar.className = "tpi-m-tabbar";
  tabbar.id = "tpiTabbar";
  tabbar.innerHTML = TABS.map(([k, ic]) => `<button type="button" data-tab="${k}"><span class="ic">${ic}</span><span class="tl"></span></button>`).join("");
  body.appendChild(tabbar);

  const banner = document.createElement("div");
  banner.className = "tpi-m-offline";
  banner.setAttribute("role", "status");
  banner.innerHTML = `<span></span><button type="button" class="btn"></button>`;
  body.appendChild(banner);

  const installBtn = document.createElement("button");
  installBtn.id = "tpiInstallBtn";
  installBtn.className = "langbtn";
  installBtn.hidden = true;
  const foot = document.querySelector(".sidefoot");
  if (foot) foot.insertBefore(installBtn, el("langBtn") || null);

  const backBtn = bar.querySelector("button");
  function relabel() {
    backBtn.textContent = t("back");
    tabbar.querySelectorAll("button").forEach((b) => { b.querySelector(".tl").textContent = t(b.dataset.tab); b.title = t(b.dataset.tab); });
    banner.querySelector("span").textContent = t("offline");
    banner.querySelector("button").textContent = t("retry");
    installBtn.textContent = t("install");
    installBtn.title = t("installTitle");
    const link = document.querySelector('link[rel="manifest"]');
    if (link) link.setAttribute("href", "/manifest.webmanifest" + (isZh() ? "" : "?lang=en"));
  }
  relabel();
  new MutationObserver(relabel).observe(root, { attributes: true, attributeFilter: ["lang"] });

  /* ── layers (drawer, detail, copilot) with one history entry each, so the phone's back gesture closes them ── */
  const layers = [];
  let skipPop = 0;
  const CLASS = { nav: "tpi-m-nav", detail: "tpi-m-detail", cp: "tpi-m-cp" };

  function show(name, on) {
    body.classList.toggle(CLASS[name], on);
    if (name === "cp" && !on && cpOpen() && typeof toggleCopilot === "function") toggleCopilot(false);
    markTabs();
  }
  function openLayer(name) {
    if (!narrow() || layers.includes(name)) return;
    layers.push(name);
    history.pushState({ tpiMobile: name }, "");
    show(name, true);
  }
  function closeLayers(names, viaPop) {
    const hit = names.filter((n) => layers.includes(n));
    if (!hit.length) return;
    hit.forEach((n) => { layers.splice(layers.indexOf(n), 1); show(n, false); });
    if (!viaPop) { skipPop += 1; history.go(-hit.length); }
  }
  const closeLayer = (name) => closeLayers([name]);
  window.addEventListener("popstate", () => {
    if (skipPop > 0) { skipPop -= 1; return; }
    const top = layers[layers.length - 1];
    if (top) closeLayers([top], true);
  });
  window.tpiMobile = {
    narrow, layers: () => layers.slice(),
    openDetail: () => openLayer("detail"), closeDetail: () => closeLayer("detail"),
    openMenu: () => openLayer("nav"), closeMenu: () => closeLayer("nav"),
  };

  function markTabs() {
    const cur = cpOpen() ? "copilot" : layers.includes("nav") ? "menu" : state.view;
    tabbar.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.tab === cur));
  }

  function onModeChange() {
    if (narrow()) {
      if (cpOpen()) openLayer("cp");
    } else {
      layers.splice(0).forEach((n) => body.classList.remove(CLASS[n]));
    }
    body.classList.toggle("tpi-m", narrow());
    markTabs();
  }
  mq.addEventListener ? mq.addEventListener("change", onModeChange) : mq.addListener(onModeChange);

  /* ── hooks into the core views ── */
  const coreSetView = window.setView;
  if (typeof coreSetView === "function") {
    window.setView = (v, ...rest) => {
      const out = coreSetView(v, ...rest);
      closeLayers(["nav", "detail"]);
      markTabs();
      return out;
    };
  }
  const coreOpenThread = window.openThread;
  if (typeof coreOpenThread === "function") {
    window.openThread = (...args) => { openLayer("detail"); return coreOpenThread(...args); };
  }

  const cp = el("copilot");
  if (cp) new MutationObserver(() => {
    if (!narrow()) return;
    if (cpOpen()) openLayer("cp"); else closeLayer("cp");
  }).observe(cp, { attributes: true, attributeFilter: ["class"] });

  /* rows and calendar cells that render into #pane open the detail screen */
  const DETAIL_TARGETS = ".row, [data-id], .tcal-ev, .tcal-chip, .tcal-mo .cell, .tcal-day";
  let armedUntil = 0;
  const list = el("list");
  if (list) list.addEventListener("click", (e) => {
    if (!narrow()) return;
    const hit = e.target.closest(DETAIL_TARGETS);
    if (!hit || !list.contains(hit)) return;
    const ctl = e.target.closest("button, input, select, textarea, a, label");
    if (ctl && ctl !== hit && hit.contains(ctl)) return;
    armedUntil = Date.now() + 1500;
  }, true);
  const pane = el("pane");
  if (pane) new MutationObserver(() => {
    if (armedUntil > Date.now()) { armedUntil = 0; openLayer("detail"); }
  }).observe(pane, { childList: true, subtree: true, characterData: true });

  backBtn.onclick = () => closeLayer("detail");
  scrim.onclick = () => closeLayer("nav");
  const aside = document.querySelector("aside");
  if (aside) aside.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (b && !b.closest(".sidefoot") && aside.contains(b)) closeLayer("nav");
  });

  tabbar.onclick = (e) => {
    const b = e.target.closest("button[data-tab]");
    if (!b) return;
    const tab = b.dataset.tab;
    if (tab === "menu") { layers.includes("nav") ? closeLayer("nav") : openLayer("nav"); return; }
    if (tab === "copilot") { if (typeof toggleCopilot === "function") toggleCopilot(); return; }
    if (cpOpen() && typeof toggleCopilot === "function") toggleCopilot(false);
    if (typeof setView === "function") window.setView(tab);
  };

  /* ── server reachability ── */
  let offline = false;
  function setOffline(off) {
    const was = offline;
    offline = off;
    body.classList.toggle("tpi-offline", off);
    if (was && !off) {
      notify(t("online"));
      if (typeof refreshCounts === "function") refreshCounts();
      if (typeof setView === "function" && !layers.includes("detail")) window.setView(state.view);
    }
  }
  async function checkServer() {
    try {
      const r = await fetch("/api/health", { cache: "no-store" });
      setOffline(!r.ok);
    } catch {
      setOffline(true);
    }
  }
  banner.querySelector("button").onclick = checkServer;
  window.addEventListener("offline", () => setOffline(true));
  window.addEventListener("online", checkServer);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") checkServer(); });
  if (navigator.onLine === false) setOffline(true);

  /* ── install ── */
  const standalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  let deferred = window.__tpiInstall || null;
  const syncInstall = () => { installBtn.hidden = standalone() || !(deferred || ios); };
  window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; syncInstall(); });
  window.addEventListener("appinstalled", () => { deferred = null; window.__tpiInstall = null; syncInstall(); notify(t("installed")); });
  installBtn.onclick = async () => {
    if (!deferred) { notify(t("iosHint")); return; }
    const prompt = deferred;
    deferred = null;
    window.__tpiInstall = null;
    syncInstall();
    prompt.prompt();
    await prompt.userChoice.catch(() => null);
  };
  body.classList.toggle("tpi-standalone", standalone());
  syncInstall();

  /* ── service worker ── */
  if ("serviceWorker" in navigator && window.isSecureContext) {
    root.dataset.tpiSw = "pending";
    const hadController = !!navigator.serviceWorker.controller;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).then((reg) => {
      root.dataset.tpiSw = "registered";
      reg.addEventListener("updatefound", () => {
        const w = reg.installing;
        if (w) w.addEventListener("statechange", () => { if (w.state === "activated" && hadController) notify(t("updated")); });
      });
    }).catch((e) => {
      root.dataset.tpiSw = "error";
      console.warn(t("swFail") + e.message);
    });
  } else {
    root.dataset.tpiSw = "unsupported";
  }

  onModeChange();
  requestAnimationFrame(() => requestAnimationFrame(() => body.classList.add("tpi-m-anim")));
  if (narrow() && new URLSearchParams(location.hash.slice(1)).get("thread")) openLayer("detail");
})();
