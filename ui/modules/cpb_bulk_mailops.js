/* Additive folder multi-select; all mutations use the existing local mailops API. */
(() => {
  "use strict";
  const list = document.getElementById("list");
  if (!list || typeof state !== "object" || window.__cpbBulkMailops) return;
  window.__cpbBulkMailops = true;

  const strings = {
    zh: {
      title: "批次操作", all: "全選目前顯示的信件", selected: "已選 {n} 封",
      hint: "只改本機狀態；全選僅限目前顯示的信件，不含本機草稿。",
      choose: "選擇動作", apply: "套用", clear: "取消選取", select: "選取信件",
      archive: "封存", trash: "移到垃圾桶", star: "加星號", unstar: "取消星號",
      read: "標為已讀", unread: "標為未讀", inbox: "移到收件匣",
      moveArchive: "移到封存", moveTrash: "移到垃圾桶",
      confirm: "對已選的 {n} 封信套用「{action}」？只改本機狀態，遠端信箱不變。",
      done: "已處理 {n} 封信。只改本機狀態，遠端信箱不變。",
      partial: "已處理 {n} 封；另有 {missing} 封在本機找不到，未處理。請檢查重新載入的列表。",
      failed: "批次操作失敗：", invalid: "伺服器回應不完整，請重新整理確認本機狀態。",
      refreshFailed: "操作已儲存，但列表更新失敗：",
      virtual: "示範寄件備份不支援已讀／未讀變更；請先取消選取這些信件。",
      busy: "處理中",
    },
    en: {
      title: "Bulk actions", all: "Select all displayed messages", selected: "{n} selected",
      hint: "Local state only. Select all covers displayed messages, not local drafts.",
      choose: "Choose action", apply: "Apply", clear: "Clear selection", select: "Select message",
      archive: "Archive", trash: "Move to Trash", star: "Star", unstar: "Unstar",
      read: "Mark read", unread: "Mark unread", inbox: "Move to Inbox",
      moveArchive: "Move to Archive", moveTrash: "Move to Trash",
      confirm: "Apply '{action}' to {n} selected messages? Local state only; the remote mailbox is untouched.",
      done: "Updated {n} messages. Local state only; the remote mailbox is untouched.",
      partial: "Updated {n}; {missing} messages were not found locally and were not changed. Check the refreshed list.",
      failed: "Bulk action failed: ", invalid: "Incomplete server response. Refresh to verify local state.",
      refreshFailed: "Changes saved, but refreshing the list failed: ",
      virtual: "Demo Sent messages do not support read/unread changes; deselect them first.",
      busy: "Working",
    },
  };
  const lang = () => document.documentElement.lang.startsWith("zh") ? "zh" : "en";
  const t = (key, values = {}) => strings[lang()][key].replace(/\{(\w+)\}/g, (_, k) => String(values[k]));
  const operations = [
    ["archive", "archive"], ["trash", "trash"], ["star", "star"], ["unstar", "unstar"],
    ["read", "read"], ["unread", "unread"], ["move:inbox", "inbox"],
    ["move:archive", "moveArchive"], ["move:trash", "moveTrash"],
  ];
  const selected = new Set();
  let rows = [], scope = "", busy = false, toolbar = null;
  const notify = (text, error = false) => toast(text, error);
  const context = () => JSON.stringify([
    state.view, state.account, state.category, state.q,
    document.getElementById("q")?.value || "", localStorage.getItem("tpi-mailops-folder") || "inbox",
  ]);

  const css = document.createElement("style");
  css.textContent = `
    #cpb-bulk-toolbar { padding: 10px 14px; border-bottom: 1px solid var(--line); }
    #cpb-bulk-toolbar .cpb-bulk-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
    #cpb-bulk-toolbar label { display: flex; align-items: center; gap: 5px; font-size: 12px; }
    #cpb-bulk-toolbar select { max-width: 100%; background: var(--panel); color: var(--ink);
      border: 1px solid var(--line); border-radius: 7px; padding: 5px; }
    #cpb-bulk-toolbar p { margin: 6px 0 0; font-size: 11px; color: var(--muted); }
    #cpb-bulk-toolbar button:disabled { opacity: .5; cursor: default; }
    #list .row.cpb-bulk-row { grid-template-columns: 20px 14px minmax(0, 1fr) auto; }
    #list .cpb-bulk-check { width: 18px; height: 18px; margin: 2px 0; accent-color: var(--accent); }
    #list .cpb-bulk-picked { background: var(--panel); box-shadow: inset 3px 0 var(--accent); }`;
  document.head.appendChild(css);

  function createToolbar() {
    const box = document.createElement("div");
    box.id = "cpb-bulk-toolbar";
    box.setAttribute("role", "group");
    box.innerHTML = `<div class="cpb-bulk-controls">
      <label><input type="checkbox" data-cpb="all"><span data-cpb="all-label"></span></label>
      <span data-cpb="count" aria-live="polite"></span>
      <select data-cpb="action"></select>
      <button class="btn" data-cpb="apply"></button>
      <button class="btn ghost" data-cpb="clear"></button></div>
      <p data-cpb="hint"></p><p data-cpb="virtual"></p>`;
    box.querySelector("[data-cpb=all]").onchange = (e) => {
      selected.clear();
      if (e.target.checked) rows.forEach((row) => selected.add(row.dataset.id));
      sync();
    };
    box.querySelector("[data-cpb=clear]").onclick = () => { selected.clear(); sync(); };
    box.querySelector("[data-cpb=action]").onchange = sync;
    box.querySelector("[data-cpb=apply]").onclick = run;
    for (const event of ["click", "keydown"]) box.addEventListener(event, (e) => e.stopPropagation());
    return box;
  }

  function renderControls() {
    if (!toolbar) return;
    toolbar.setAttribute("aria-label", t("title"));
    const get = (key) => toolbar.querySelector(`[data-cpb=${key}]`);
    get("all-label").textContent = t("all");
    get("count").textContent = t("selected", { n: selected.size });
    get("hint").textContent = t("hint");
    get("clear").textContent = t("clear");
    get("apply").textContent = t(busy ? "busy" : "apply");
    const action = get("action");
    const previous = action.value;
    action.replaceChildren(new Option(t("choose"), ""), ...operations.map(([value, key]) => new Option(t(key), value)));
    action.value = previous;
    action.setAttribute("aria-label", t("choose"));
    const hasVirtual = rows.some((row) => selected.has(row.dataset.id) &&
      state.emails[Number(row.dataset.i)]?.source === "sent_fixture");
    for (const option of action.options) {
      option.disabled = hasVirtual && ["read", "unread"].includes(option.value);
    }
    get("virtual").textContent = hasVirtual ? t("virtual") : "";
    get("virtual").hidden = !hasVirtual;
    get("all").checked = rows.length > 0 && selected.size === rows.length;
    get("all").indeterminate = selected.size > 0 && selected.size < rows.length;
    get("all").disabled = busy || !rows.length;
    get("clear").disabled = busy || !selected.size;
    action.disabled = busy || !selected.size;
    get("apply").disabled = busy || !selected.size || !action.value ||
      (hasVirtual && ["read", "unread"].includes(action.value));
    toolbar.setAttribute("aria-busy", String(busy));
  }

  function reconcile() {
    const active = state.view === "mail" && window.__tpiMailops && list.querySelector(".tmo-fhead");
    const next = active ? [...list.querySelectorAll(".row[data-id][data-i]")].filter((row) => {
      const item = state.emails[Number(row.dataset.i)];
      return item?.id === row.dataset.id && item.kind !== "draft" &&
        ["cache", "sent_fixture"].includes(item.source);
    }) : [];
    const nextScope = context();
    // A rebuilt list or changed filter starts a new selection, even if IDs happen to match.
    if (nextScope !== scope || next.length !== rows.length || next.some((row, i) => row !== rows[i])) {
      selected.clear();
    }
    rows = next;
    scope = nextScope;
    if (!active || !rows.length) {
      toolbar?.remove();
      toolbar = null;
      return;
    }
    if (!toolbar?.isConnected) {
      toolbar = createToolbar();
      list.querySelector(".tmo-fhead").after(toolbar);
    }
    for (const row of rows) {
      let input = row.querySelector(".cpb-bulk-check");
      if (!input) {
        input = document.createElement("input");
        input.type = "checkbox";
        input.className = "cpb-bulk-check";
        row.prepend(input);
        row.classList.add("cpb-bulk-row");
        for (const event of ["click", "keydown"]) input.addEventListener(event, (e) => e.stopPropagation());
        input.onchange = () => {
          if (input.checked) selected.add(row.dataset.id);
          else selected.delete(row.dataset.id);
          sync();
        };
      }
      input.checked = selected.has(row.dataset.id);
      input.disabled = busy;
      input.setAttribute("aria-label", t("select"));
      row.classList.toggle("cpb-bulk-picked", input.checked);
    }
    renderControls();
  }

  const observer = new MutationObserver(sync);
  function sync() {
    observer.disconnect();
    reconcile();
    observer.observe(list, { childList: true, subtree: true });
  }

  async function run() {
    sync();
    if (busy || !toolbar || toolbar.querySelector("[data-cpb=apply]").disabled) return;
    const value = toolbar.querySelector("[data-cpb=action]").value;
    const [action, folder = ""] = value.split(":");
    const ids = [...selected];
    const key = operations.find(([op]) => op === value)[1];
    if (!window.confirm(t("confirm", { n: ids.length, action: t(key) }))) return;
    busy = true;
    sync();
    let saved = false;
    try {
      const response = await fetch("/api/mailops/action", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids, action, folder, lang: lang() === "zh" ? "zh-Hant" : "en" }),
      });
      const data = await response.json();
      if (!response.ok || data.ok !== true) throw new Error(data.error || String(response.status));
      const reported = [...(Array.isArray(data.changed) ? data.changed : []),
        ...(Array.isArray(data.unknown) ? data.unknown : [])];
      if (!Array.isArray(data.changed) || !Array.isArray(data.unknown) ||
          reported.length !== ids.length || new Set(reported).size !== ids.length ||
          reported.some((id) => !ids.includes(id)) || !data.changed.length) {
        throw new Error(t("invalid"));
      }
      saved = true;
      selected.clear();
      notify(data.unknown.length
        ? t("partial", { n: data.changed.length, missing: data.unknown.length })
        : t("done", { n: data.changed.length }), data.unknown.length > 0);
      if (state.view === "mail") await window.loadInbox();
      if (typeof window.refreshCounts === "function") await window.refreshCounts();
    } catch (error) {
      notify(t(saved ? "refreshFailed" : "failed") + error.message, true);
    } finally {
      busy = false;
      sync();
    }
  }

  new MutationObserver(sync).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
  sync();
})();
