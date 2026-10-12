/* Drive headless Chrome over CDP for test_tpi_mobile_ui.py:
 *   node _tpi_mobile_cdp.js <chrome> <base-url> <profile-dir>                     phone layout walk-through
 *   node _tpi_mobile_cdp.js <chrome> <base-url> <profile-dir> offline <server-pid> kills the server, checks the offline UI */
"use strict";
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

const [chrome, base, profile, mode, serverPid] = process.argv.slice(2);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const proc = spawn(chrome, ["--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run", "--remote-debugging-port=0",
  "--user-data-dir=" + profile, "about:blank"], { stdio: "ignore" });

async function devtoolsPort() {
  const file = path.join(profile, "DevToolsActivePort");
  for (let i = 0; i < 150; i++) {
    if (fs.existsSync(file)) {
      const port = fs.readFileSync(file, "utf8").split("\n")[0].trim();
      if (port) return port;
    }
    await sleep(100);
  }
  throw new Error("Chrome did not open a DevTools port");
}

async function main() {
  const port = await devtoolsPort();
  let page;
  for (let i = 0; i < 50 && !page; i++) {
    const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    page = list.find((t) => t.type === "page");
    if (!page) await sleep(100);
  }
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let seq = 0;
  const pending = new Map();
  const exceptions = [];
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) {
      const { res, rej } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? rej(new Error(msg.error.message)) : res(msg.result);
    } else if (msg.method === "Runtime.exceptionThrown") {
      exceptions.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
    }
  };
  const send = (method, params = {}) => new Promise((res, rej) => {
    const id = ++seq;
    pending.set(id, { res, rej });
    ws.send(JSON.stringify({ id, method, params }));
  });
  const js = async (expr) => {
    const r = await send("Runtime.evaluate", { expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(expr.slice(0, 80) + " → " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    return r.result.value;
  };
  const until = async (cond, ms = 10000) => {
    const ok = await js(`for (let i = 0; i < ${ms / 50}; i++) { if (${cond}) return true; await new Promise((r) => setTimeout(r, 50)); } return false;`);
    if (!ok) throw new Error("timed out waiting for " + cond);
  };
  const shot = async (name) => {
    if (!process.env.TPI_SHOTS) return;
    const r = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(process.env.TPI_SHOTS, name + ".png"), Buffer.from(r.data, "base64"));
  };
  const out = {};
  const has = (c) => `document.body.classList.contains(${JSON.stringify(c)})`;

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await send("Page.navigate", { url: base + "/" });
  await until(`window.__tpiMobile && document.querySelectorAll("#list .row").length > 0 && document.getElementById("tpiTabbar")`);
  await until(`document.documentElement.dataset.tpiSw === "registered"`);

  if (mode === "offline") {
    await send("Page.reload");
    await until(`window.__tpiMobile && navigator.serviceWorker.controller`);
    process.kill(Number(serverPid), "SIGTERM");
    await sleep(500);
    await js(`document.dispatchEvent(new Event("visibilitychange"));`);
    await until(`${has("tpi-offline")}`);
    out.banner = await js(`return getComputedStyle(document.querySelector(".tpi-m-offline")).display;`);
    out.bannerText = await js(`return document.querySelector(".tpi-m-offline span").textContent;`);
    await send("Page.navigate", { url: base + "/" });
    await sleep(300);
    await until(`document.getElementById("retry") && document.querySelector("h1")`);
    out.offlinePath = await js(`return location.pathname;`);
    out.offlineH1 = await js(`return document.querySelector("h1").textContent;`);
    out.offlineBody = await js(`return document.body.innerText;`);
    console.log(JSON.stringify(out));
    ws.close();
    return;
  }

  out.narrow = await js(`return ${has("tpi-m")};`);
  out.tabbar = await js(`return getComputedStyle(document.getElementById("tpiTabbar")).display;`);
  out.tabs = await js(`return [...document.querySelectorAll("#tpiTabbar button")].map((b) => b.dataset.tab);`);
  out.asideHidden = await js(`return getComputedStyle(document.querySelector("aside")).visibility;`);
  out.sectionHidden = await js(`return getComputedStyle(document.querySelector("section")).visibility;`);
  out.mainWidth = await js(`return Math.round(document.querySelector("main").getBoundingClientRect().width);`);
  out.docOverflowX = await js(`return document.documentElement.scrollWidth > window.innerWidth;`);
  await shot("1-list");

  await js(`document.querySelector("#list .row").click();`);
  await until(`${has("tpi-m-detail")} && document.querySelector("#pane h2")`);
  await sleep(400);
  out.detailLeft = await js(`return Math.round(document.querySelector("section").getBoundingClientRect().left);`);
  out.detailTitle = await js(`return document.querySelector("#pane h2").textContent;`);
  out.tabbarInDetail = await js(`return getComputedStyle(document.getElementById("tpiTabbar")).display;`);
  out.backLabel = await js(`return document.querySelector(".tpi-m-bar button").textContent;`);
  await shot("2-detail");
  await js(`history.back();`);
  await until(`!${has("tpi-m-detail")}`);
  out.afterBackLayers = await js(`return tpiMobile.layers();`);

  await js(`document.querySelector("#list .row").click();`);
  await until(`${has("tpi-m-detail")}`);
  await js(`document.querySelector(".tpi-m-bar button").click();`);
  await until(`!${has("tpi-m-detail")}`);
  await sleep(300);
  out.afterBackButtonHistory = await js(`return history.state;`);

  await js(`document.querySelector('#tpiTabbar [data-tab="menu"]').click();`);
  await until(`${has("tpi-m-nav")}`);
  await sleep(400);
  out.drawerLeft = await js(`return Math.round(document.querySelector("aside").getBoundingClientRect().left);`);
  await shot("3-drawer");
  await js(`document.querySelector('#nav button[data-view="drafts"]').click();`);
  await until(`!${has("tpi-m-nav")} && state.view === "drafts"`);
  out.activeTab = await js(`return document.querySelector("#tpiTabbar button.on")?.dataset.tab;`);

  await js(`document.querySelector('#tpiTabbar [data-tab="calendar"]').click();`);
  await until(`state.view === "calendar"`);
  out.calendarWide = await js(`return document.getElementById("app").classList.contains("tcal-cal-wide");`);
  out.calendarMainWidth = await js(`return Math.round(document.querySelector("main").getBoundingClientRect().width);`);
  await sleep(300);
  await shot("4-calendar");

  await js(`document.querySelector('#tpiTabbar [data-tab="copilot"]').click();`);
  await until(`${has("tpi-m-cp")} && document.getElementById("copilot").classList.contains("open")`);
  await sleep(400);
  await shot("5-copilot");
  out.copilotRect = await js(`const r = document.getElementById("copilot").getBoundingClientRect(); return [Math.round(r.left), Math.round(r.width)];`);
  await js(`history.back();`);
  await until(`!${has("tpi-m-cp")} && !document.getElementById("copilot").classList.contains("open")`);
  out.layersEnd = await js(`return tpiMobile.layers();`);

  out.composeRect = await js(`const b = document.getElementById("tpiComposeBtn"); if (!b) return null; b.click();
    for (let i = 0; i < 100 && !document.querySelector(".tpi-back.open [role=dialog]"); i++) await new Promise((r) => setTimeout(r, 50));
    const d = document.querySelector(".tpi-back.open [role=dialog]"); if (!d) return null;
    const r = d.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];`);
  await shot("7-compose");
  await js(`document.querySelector(".tpi-back.open [data-c=close]")?.click();`);
  await sleep(200);

  await js(`document.getElementById("langBtn").click();`);
  await sleep(100);
  out.enLabels = await js(`return [...document.querySelectorAll("#tpiTabbar .tl")].map((x) => x.textContent);`);
  out.enManifest = await js(`return document.querySelector('link[rel="manifest"]').getAttribute("href");`);
  await js(`document.getElementById("langBtn").click();`);
  await sleep(100);
  out.zhLabels = await js(`return [...document.querySelectorAll("#tpiTabbar .tl")].map((x) => x.textContent);`);

  await send("Page.reload");
  await until(`window.__tpiMobile && navigator.serviceWorker.controller && document.querySelectorAll("#list .row").length > 0`);
  await sleep(500);
  out.controlled = await js(`return !!navigator.serviceWorker.controller;`);
  out.cached = await js(`const urls = []; for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) urls.push(new URL(r.url).pathname); return urls;`);
  out.cacheNames = await js(`return caches.keys();`);
  out.installErrors = (await send("Page.getInstallabilityErrors")).installabilityErrors;
  const man = await send("Page.getAppManifest");
  out.manifestErrors = man.errors;
  out.manifestUrl = man.url;

  await send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
  await sleep(300);
  out.wideNarrow = await js(`return ${has("tpi-m")};`);
  out.wideTabbar = await js(`return getComputedStyle(document.getElementById("tpiTabbar")).display;`);
  out.wideSection = await js(`return getComputedStyle(document.querySelector("section")).visibility;`);
  await shot("6-wide");

  out.exceptions = exceptions;
  console.log(JSON.stringify(out));
  ws.close();
}

main().then(() => { proc.kill("SIGKILL"); process.exit(0); })
  .catch((e) => { console.error(e.stack || String(e)); proc.kill("SIGKILL"); process.exit(1); });
