/* BYOK token usage (GET /api/usage): every call to your own model, logged to data/usage.jsonl.
   Totals, per driver / model / feature / day, recent calls, clear. */
(() => {
  "use strict";
  const S = {
    zh: {
      nav: "📊 用量", title: "BYOK 用量", intro: "每次呼叫你自己的模型（agent.json）都會記一筆到本機檔案，只記 token 數與中繼資料，不記內容與金鑰。",
      days: "期間", d7: "7 天", d30: "30 天", d90: "90 天", d365: "一年",
      calls: "呼叫", prompt: "輸入 token", completion: "輸出 token", total: "總 token", estimated: "估算", errors: "失敗",
      byDriver: "依 driver", byModel: "依模型", byFeature: "依功能", byDay: "依日期", recent: "最近呼叫",
      none: "這段期間沒有用量紀錄。", allTime: "全部累計", file: "紀錄檔", clear: "清除紀錄",
      clearConfirm: "清除所有用量紀錄？這只會清空本機的 usage.jsonl。", failed: "失敗：", exact: "實數", est: "估",
      when: "時間", feature: "功能", driver: "driver", model: "模型", ok: "成功", fail: "失敗", ms: "毫秒",
    },
    en: {
      nav: "📊 Usage", title: "BYOK usage", intro: "Every call to your own model (agent.json) adds one line to a local file: token counts and metadata only, never content or keys.",
      days: "Period", d7: "7 days", d30: "30 days", d90: "90 days", d365: "1 year",
      calls: "Calls", prompt: "Prompt tokens", completion: "Completion tokens", total: "Total tokens", estimated: "Estimated", errors: "Errors",
      byDriver: "By driver", byModel: "By model", byFeature: "By feature", byDay: "By day", recent: "Recent calls",
      none: "No usage recorded in this period.", allTime: "All time", file: "Log file", clear: "Clear log",
      clearConfirm: "Clear all usage records? This only empties the local usage.jsonl.", failed: "Failed: ", exact: "exact", est: "est.",
      when: "When", feature: "Feature", driver: "Driver", model: "Model", ok: "ok", fail: "failed", ms: "ms",
    },
  };
  const isZh = () => document.documentElement.lang.startsWith("zh");
  const t = (k) => S[isZh() ? "zh" : "en"][k];
  const langParam = () => (isZh() ? "zh-Hant" : "en");
  const h = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const notify = (msg, isErr) => (typeof toast === "function" ? toast(msg, isErr) : console.log(msg));
  const n = (x) => Number(x || 0).toLocaleString();
  const nav = document.getElementById("nav");
  if (!nav || typeof state !== "object" || window.__tpiUsage) return;
  window.__tpiUsage = true;

  const css = document.createElement("style");
  css.textContent = `
    .us-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 12px 0; }
    .us-card { border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; background: var(--panel); }
    .us-card .big { font-size: 21px; color: var(--accent2); } .us-card .muted { font-size: 12px; }
    .us-sec { margin: 16px 0 6px; font-size: 13px; color: var(--accent2); border-bottom: 1px dashed #3a332a; padding-bottom: 4px; }
    .us-tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; }
    .us-tbl th, .us-tbl td { text-align: left; padding: 5px 6px; border-bottom: 1px solid #221e1a; }
    .us-tbl th { color: var(--muted); font-weight: 500; } .us-tbl td.num, .us-tbl th.num { text-align: right; font-variant-numeric: tabular-nums; }
    .us-bar { height: 6px; background: var(--accent); border-radius: 3px; min-width: 2px; }
    .us-day { display: grid; grid-template-columns: 86px 1fr 70px; gap: 8px; align-items: center; padding: 7px 14px; border-bottom: 1px solid #221e1a; font-size: 12px; }
    .us-pill { font-size: 10px; border: 1px solid var(--line); border-radius: 999px; padding: 0 5px; color: var(--muted); }
    .us-pill.fail { color: var(--need); border-color: #6b4a3a; }
    .us-days button.on { border-color: var(--accent); color: var(--ink); }`;
  document.head.appendChild(css);

  const navBtn = document.createElement("button");
  navBtn.dataset.view = "usage";
  const navLabel = document.createElement("span");
  const navCnt = document.createElement("span");
  navCnt.className = "cnt";
  navBtn.append(navLabel, navCnt);
  nav.appendChild(navBtn);
  const relabel = () => { navLabel.textContent = t("nav"); };
  relabel();

  const view = { days: 30, data: null };
  const $list = () => document.getElementById("list");
  const $pane = () => document.getElementById("pane");

  async function load() {
    try {
      const r = await fetch(`/api/usage?days=${view.days}&limit=100&lang=${langParam()}`);
      view.data = await r.json();
    } catch (e) { $pane().innerHTML = `<p class='muted'>${h(t("failed") + e.message)}</p>`; return; }
    navCnt.textContent = view.data.totals?.calls ? n(view.data.totals.total_tokens) : "";
    render();
  }

  const table = (rows) => rows.length ? `<table class="us-tbl"><tr><th></th><th class="num">${h(t("calls"))}</th><th class="num">${h(t("prompt"))}</th><th class="num">${h(t("completion"))}</th><th class="num">${h(t("total"))}</th><th class="num">${h(t("estimated"))}</th><th class="num">${h(t("errors"))}</th></tr>
    ${rows.map((g) => `<tr><td>${h(g.key)}</td><td class="num">${n(g.calls)}</td><td class="num">${n(g.prompt_tokens)}</td><td class="num">${n(g.completion_tokens)}</td><td class="num">${n(g.total_tokens)}</td><td class="num">${n(g.estimated_calls)}</td><td class="num">${n(g.errors)}</td></tr>`).join("")}</table>`
    : `<p class="muted" style="font-size:12.5px">${h(t("none"))}</p>`;

  function render() {
    const d = view.data || {};
    const tot = d.totals || {};
    const days = d.by_day || [];
    const max = Math.max(1, ...days.map((x) => x.total_tokens || 0));
    $list().innerHTML = days.slice().reverse().map((x) => `
      <div class="us-day"><span>${h(x.key)}</span><div class="us-bar" style="width:${Math.round(((x.total_tokens || 0) / max) * 100)}%"></div><span style="text-align:right">${n(x.total_tokens)}</span></div>`).join("")
      || `<div class="empty">${h(t("none"))}</div>`;
    $pane().innerHTML = `
      <h2 class="mh">${h(t("title"))}</h2>
      <p class="muted" style="margin:0">${h(t("intro"))}</p>
      <p class="muted" style="font-size:12px">${h(d.note || "")}</p>
      <div class="actionbar us-days">${[7, 30, 90, 365].map((x) => `<button class="btn ${x === view.days ? "on" : "ghost"}" data-days="${x}">${h(t("d" + x))}</button>`).join("")}</div>
      <div class="us-grid">
        <div class="us-card"><div class="muted">${h(t("calls"))}</div><div class="big">${n(tot.calls)}</div><div class="muted">${h(t("errors"))} ${n(tot.errors)}</div></div>
        <div class="us-card"><div class="muted">${h(t("total"))}</div><div class="big">${n(tot.total_tokens)}</div><div class="muted">${h(t("prompt"))} ${n(tot.prompt_tokens)} · ${h(t("completion"))} ${n(tot.completion_tokens)}</div></div>
        <div class="us-card"><div class="muted">${h(t("estimated"))}</div><div class="big">${n(tot.estimated_calls)}</div><div class="muted">${h(t("allTime"))} ${n(d.all_time?.total_tokens)}</div></div>
      </div>
      <div class="us-sec">${h(t("byDriver"))}</div>${table(d.by_driver || [])}
      <div class="us-sec">${h(t("byModel"))}</div>${table(d.by_model || [])}
      <div class="us-sec">${h(t("byFeature"))}</div>${table(d.by_feature || [])}
      <div class="us-sec">${h(t("recent"))}</div>
      ${(d.recent || []).length ? `<table class="us-tbl"><tr><th>${h(t("when"))}</th><th>${h(t("feature"))}</th><th>${h(t("driver"))}</th><th>${h(t("model"))}</th><th class="num">${h(t("total"))}</th><th class="num">${h(t("ms"))}</th><th></th></tr>
        ${d.recent.map((r) => `<tr><td>${h(String(r.ts).replace("T", " ").slice(0, 19))}</td><td>${h(r.feature)}</td><td>${h(r.driver)}</td><td>${h(r.model)}</td><td class="num">${n(r.total_tokens)}</td><td class="num">${n(r.ms)}</td>
          <td><span class="us-pill">${h(r.estimated ? t("est") : t("exact"))}</span>${r.ok ? "" : ` <span class="us-pill fail" title="${h(r.error || "")}">${h(t("fail"))}</span>`}</td></tr>`).join("")}</table>`
        : `<p class="muted" style="font-size:12.5px">${h(t("none"))}</p>`}
      <p class="hint">${h(t("file"))}: <code>${h(d.file || "")}</code></p>
      <div class="actionbar"><button class="btn ghost" data-do="clear">${h(t("clear"))}</button></div>`;
    $pane().onclick = async (ev) => {
      const b = ev.target.closest("button");
      if (!b) return;
      if (b.dataset.days) { view.days = Number(b.dataset.days); return load(); }
      if (b.dataset.do === "clear") {
        if (!window.confirm(t("clearConfirm"))) return;
        try {
          const r = await fetch("/api/usage/clear", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ lang: langParam() }) });
          const out = await r.json();
          if (!r.ok || out.error) throw new Error(out.error || String(r.status));
          notify(out.note);
          load();
        } catch (e) { notify(t("failed") + e.message, true); }
      }
    };
  }

  const coreSetView = window.setView;
  if (typeof coreSetView === "function") {
    window.setView = (v, ...rest) => {
      const out = coreSetView(v, ...rest);
      if (v === "usage") load();
      return out;
    };
  }
  new MutationObserver(() => {
    relabel();
    if (state.view === "usage") load();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

  if (new URLSearchParams(location.hash.slice(1)).get("view") === "usage") window.setView("usage");
})();
