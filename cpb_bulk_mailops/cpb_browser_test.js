/* Local Chrome CDP walk-through; only disposable, fictional test data is used. */
"use strict";
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const [chrome, base, profile] = process.argv.slice(2);
assert.equal(new URL(base).hostname, "127.0.0.1");
const proc = spawn(chrome, ["--headless=new", "--no-sandbox", "--disable-gpu", "--no-first-run",
  "--remote-debugging-port=0", "--user-data-dir=" + profile, "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let ws;

async function main() {
  const portFile = path.join(profile, "DevToolsActivePort");
  for (let i = 0; i < 150 && !fs.existsSync(portFile); i++) await sleep(100);
  assert.ok(fs.existsSync(portFile), "Chrome DevTools did not start");
  const port = fs.readFileSync(portFile, "utf8").split("\n")[0].trim();
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws = new WebSocket(pages.find((page) => page.type === "page").webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let seq = 0;
  const pending = new Map(), exceptions = [], checks = [], requests = new Set();
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      message.error ? reject(new Error(message.error.message)) : resolve(message.result);
    } else if (message.method === "Runtime.exceptionThrown") {
      exceptions.push(message.params.exceptionDetails.exception?.description || message.params.exceptionDetails.text);
    } else if (message.method === "Network.requestWillBeSent" && message.params.request.url.startsWith(base)) {
      requests.add(message.params.requestId);
    } else if (["Network.loadingFinished", "Network.loadingFailed"].includes(message.method)) {
      requests.delete(message.params.requestId);
    }
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  const js = async (source) => {
    const result = await send("Runtime.evaluate", {
      expression: `(async () => { ${source} })()`, awaitPromise: true, returnByValue: true,
    });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  };
  const until = async (condition) => {
    assert.ok(await js(`for (let i = 0; i < 200; i++) {
      if (${condition}) return true; await new Promise((r) => setTimeout(r, 50)); } return false;`), condition);
  };
  const check = async (name, condition) => {
    assert.ok(await js(`return !!(${condition});`), name);
    checks.push(name);
  };
  const pick = async (value) => {
    await js(`const select = document.querySelector('[data-cpb=action]'); select.value = ${JSON.stringify(value)};
      select.dispatchEvent(new Event('change', { bubbles: true }));`);
  };
  const folder = async (value) => {
    await js(`document.querySelector('[data-folder=${value}]').click();`);
    await until(`localStorage.getItem('tpi-mailops-folder') === '${value}' &&
      document.querySelector('[data-folder=${value}].on')`);
    await until(value === "drafts" ? `state.emails.some(e => e.kind === 'draft')` :
      `state.emails.every(e => e.folder === '${value}') && document.querySelector('.cpb-bulk-check')`);
  };
  const reload = async () => {
    await js("await window.loadInbox();");
    await until("document.querySelector('#cpb-bulk-toolbar')");
  };
  const apply = async () => {
    await js("document.querySelector('[data-cpb=apply]').click();");
    await until("!document.querySelector('#cpb-bulk-toolbar') || document.querySelector('#cpb-bulk-toolbar').getAttribute('aria-busy') === 'false'");
  };

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Network.enable");
  await send("Page.navigate", { url: base + "/" });
  await until("window.__tpiMailops && document.querySelectorAll('.cpb-bulk-check').length >= 2");
  await js(`window.__cpbPosts = []; window.__cpbConfirms = []; window.__cpbAllow = true;
    window.confirm = (text) => { window.__cpbConfirms.push(text); return window.__cpbAllow; };
    window.__cpbFetch = window.fetch;
    window.fetch = async (url, options) => {
      if (url === '/api/mailops/action' && options?.method === 'POST') {
        window.__cpbPosts.push(JSON.parse(options.body));
      }
      return window.__cpbFetch(url, options);
    };`);
  await check("toolbar is bilingual and local-only", "document.querySelector('[data-cpb=hint]').textContent.includes('本機')");
  await check("Apply starts disabled", "document.querySelector('[data-cpb=apply]').disabled");
  await check("displayed list is capped at 120, not the whole mailbox", "state.emails.length === 120");
  await js("document.querySelector('[data-cpb=all]').click();");
  await check("select-all respects the exact 120-message display limit",
    "document.querySelectorAll('.cpb-bulk-check:checked').length === 120");
  await js("document.querySelector('[data-cpb=clear]').click();");
  await js("window.__cpbBeforeSelected = state.selected?.id; document.querySelector('.cpb-bulk-check').click();");
  await check("checkbox does not open a thread", "state.selected?.id === window.__cpbBeforeSelected");
  await check("partial selection has indeterminate select-all", "document.querySelector('[data-cpb=all]').indeterminate");
  await js("document.querySelector('.cpb-bulk-check').focus();");
  await send("Input.dispatchKeyEvent", { type: "keyDown", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
  await send("Input.dispatchKeyEvent", { type: "keyUp", key: " ", code: "Space", windowsVirtualKeyCode: 32 });
  await check("Space toggles selection without opening mail",
    "!document.querySelector('.cpb-bulk-check').checked && state.selected?.id === window.__cpbBeforeSelected");
  await js("document.querySelector('.cpb-bulk-check').click();");
  await js("document.querySelectorAll('.cpb-bulk-check')[1].click();");
  await check("two rows selected", "document.querySelectorAll('.cpb-bulk-check:checked').length === 2");
  await pick("archive");
  await js("window.__cpbAllow = false;");
  await apply();
  await check("cancelled confirmation never posts", "window.__cpbPosts.length === 0");
  await check("cancel preserves selection", "document.querySelectorAll('.cpb-bulk-check:checked').length === 2");
  await js("window.__cpbAllow = true; window.__cpbArchived = [...document.querySelectorAll('.cpb-bulk-check:checked')].map(x => x.closest('.row').dataset.id);");
  await apply();
  await check("archive sends exactly the selected IDs", "JSON.stringify(window.__cpbPosts[0].ids) === JSON.stringify(window.__cpbArchived)");
  await check("processed rows leave Inbox", "window.__cpbArchived.every(id => !state.emails.some(e => e.id === id))");
  await check("success resets selection", "document.querySelector('[data-cpb=count]').textContent.includes('0')");
  await check("confirmation states count and local-only effect", "window.__cpbConfirms.at(-1).includes('2') && window.__cpbConfirms.at(-1).includes('本機')");

  await folder("archive");
  await js("document.querySelector('[data-cpb=all]').click();");
  await check("select-all selects only displayed rows", "document.querySelectorAll('.cpb-bulk-check:checked').length === state.emails.length");
  await pick("move:inbox");
  await apply();
  await until("state.emails.length === 0 && !document.querySelector('#cpb-bulk-toolbar')");
  checks.push("move restores both archived messages");
  await folder("inbox");
  await js("document.querySelector('.cpb-bulk-check').click();");
  await reload();
  await check("list rebuild clears selection even with identical IDs", "!document.querySelector('.cpb-bulk-check:checked')");
  await js("document.querySelector('.cpb-bulk-check').click(); document.getElementById('langBtn').click();");
  await until("document.querySelector('[data-cpb=all-label]').textContent === 'Select all displayed messages'");
  await reload();
  await check("language-triggered list rebuild clears selection", "document.querySelector('[data-cpb=count]').textContent === '0 selected'");
  await check("English labels cover the operation chooser",
    "document.querySelector('[data-cpb=action] option[value=read]').textContent === 'Mark read'");
  await js("document.querySelector('.cpb-bulk-check').click();");
  await pick("star");
  await apply();
  await check("star updates local list", "state.emails[0].starred");
  await js("document.querySelector('.cpb-bulk-check').click();");
  await pick("unstar");
  await apply();
  await check("unstar updates local list", "!state.emails[0].starred");
  await js("document.querySelector('.cpb-bulk-check').click();");
  await pick("read");
  await apply();
  await check("read updates local list", "!state.emails[0].unread");
  await js("document.querySelector('.cpb-bulk-check').click();");
  await pick("unread");
  await apply();
  await check("unread updates local list", "state.emails[0].unread");
  await js("document.querySelector('.cpb-bulk-check').click(); window.__cpbAllow = false;");
  await pick("trash");
  const beforeTrash = await js("return window.__cpbPosts.length;");
  await apply();
  await check("cancelled Trash confirmation never mutates mail", `window.__cpbPosts.length === ${beforeTrash}`);
  await js("window.__cpbAllow = true; window.__cpbTrashed = document.querySelector('.cpb-bulk-check').closest('.row').dataset.id;");
  await apply();
  await check("Trash affects only the selected message", "!state.emails.some(e => e.id === window.__cpbTrashed)");
  await folder("trash");
  await js("document.querySelector('[data-cpb=all]').click();");
  await pick("move:inbox");
  await apply();
  await folder("inbox");

  await js("document.querySelector('.cpb-bulk-check').click(); state.account = 'no-mail@example.com';");
  await pick("archive");
  const beforeStale = await js("return window.__cpbPosts.length;");
  await apply();
  await check("changed filter cannot submit a stale selection", `window.__cpbPosts.length === ${beforeStale}`);
  await js("state.account = ''; await window.loadInbox();");
  await until("document.querySelector('.cpb-bulk-check')");
  await js("document.querySelector('[data-cpb=all]').click(); document.querySelector('[data-cpb=clear]').click();");
  await check("Clear selection works", "!document.querySelector('.cpb-bulk-check:checked')");

  await folder("drafts");
  await check("local drafts cannot be selected", "!document.querySelector('.cpb-bulk-check') && !document.querySelector('#cpb-bulk-toolbar')");
  await folder("sent");
  await js("document.querySelector('.cpb-bulk-check').click();");
  await check("virtual Sent disables unsupported read changes", "document.querySelector('[data-cpb=action] option[value=unread]').disabled");
  await pick("unread");
  await check("unsupported read action cannot be submitted", "document.querySelector('[data-cpb=apply]').disabled");
  await pick("star");
  await apply();
  await check("virtual Sent supports starring", "state.emails[0].starred");
  await folder("inbox");

  await js(`window.__cpbFailure = 'partial';
    window.fetch = async (url, options) => {
      if (url === '/api/mailops/action' && options?.method === 'POST' && window.__cpbFailure) {
        const body = JSON.parse(options.body);
        window.__cpbPosts.push(body);
        if (window.__cpbFailure === 'network') throw new Error('Synthetic network failure');
        if (window.__cpbFailure === 'invalid') return new Response(JSON.stringify({ok: true, changed: [], unknown: []}));
        if (window.__cpbFailure === 'http') return new Response(JSON.stringify({error: 'Synthetic refusal'}), {status: 403});
        if (window.__cpbFailure === 'partial') return new Response(JSON.stringify({
          ok: true, changed: body.ids.slice(0, 1), unknown: body.ids.slice(1),
        }));
        if (window.__cpbFailure === 'delayed') {
          await new Promise(resolve => { window.__cpbResolve = resolve; });
          return new Response(JSON.stringify({ok: true, changed: body.ids, unknown: []}));
        }
      }
      return window.__cpbFetch(url, options);
    };
    document.querySelectorAll('.cpb-bulk-check')[0].click();
    document.querySelectorAll('.cpb-bulk-check')[1].click();`);
  await pick("archive");
  await apply();
  await check("partial success is visibly an error with exact counts",
    "document.querySelector('.toast:last-child').classList.contains('err') && document.querySelector('.toast:last-child').textContent.includes('Updated 1; 1')");
  for (const mode of ["network", "http", "invalid"]) {
    await js(`window.__cpbFailure = '${mode}'; document.querySelector('.cpb-bulk-check').click();`);
    await pick("archive");
    await apply();
    await check(mode + " failure is explicit", "document.querySelector('.toast:last-child').classList.contains('err')");
    await check(mode + " failure preserves selection", "document.querySelectorAll('.cpb-bulk-check:checked').length === 1");
    await js("document.querySelector('[data-cpb=clear]').click();");
  }
  await js("window.__cpbFailure = 'delayed'; document.querySelector('.cpb-bulk-check').click();");
  await pick("archive");
  await js("document.querySelector('[data-cpb=apply]').click();");
  await until("window.__cpbResolve");
  const beforeDouble = await js("return window.__cpbPosts.length;");
  await js("document.querySelector('[data-cpb=apply]').click();");
  await check("busy disables controls and duplicate requests",
    `window.__cpbPosts.length === ${beforeDouble} && document.querySelector('[data-cpb=all]').disabled && document.querySelector('.cpb-bulk-check').disabled`);
  await js("window.setView('brain'); window.__cpbResolve();");
  await until("!document.querySelector('#cpb-bulk-toolbar')");
  await check("completion after navigation does not overwrite other views", "state.view === 'brain' && !document.querySelector('.cpb-bulk-check')");
  await js("window.__cpbFailure = ''; window.setView('mail');");
  await until("document.querySelector('.cpb-bulk-check')");
  await check("returning to Mail starts with no selection", "!document.querySelector('.cpb-bulk-check:checked')");
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await check("toolbar fits a narrow screen", "document.querySelector('#cpb-bulk-toolbar').scrollWidth <= document.querySelector('#cpb-bulk-toolbar').clientWidth");
  for (let i = 0; i < 200; i++) {
    await sleep(50);
    if (!requests.size) {
      await sleep(100);
      if (!requests.size) break;
    }
  }
  assert.equal(requests.size, 0, "local requests must finish before closing Chrome");
  assert.deepEqual(exceptions, [], "browser runtime exceptions");
  console.log(JSON.stringify({ checks, exceptions }));
}

main().then(() => {
  ws?.close();
  proc.kill("SIGTERM");
}).catch((error) => {
  console.error(error.stack);
  ws?.close();
  proc.kill("SIGTERM");
  process.exitCode = 1;
});
