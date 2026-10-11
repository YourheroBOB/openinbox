/* Clear local cache: sidebar button → POST /api/cache/clear. */
(() => {
  "use strict";
  const S = {
    zh: {
      label: "清除本機快取",
      title: "刪除這台機器上快取的信件、行程與衍生卡片；草稿與筆記卡保留。",
      confirm: "確定清除本機快取？\n快取的信件、行程、Copilot 紀錄與衍生卡片會刪除；草稿與你寫的筆記卡保留。\n之後按「同步」可重新抓信。",
      done: "本機快取已清除",
      fail: "清除失敗：",
    },
    en: {
      label: "Clear local cache",
      title: "Delete cached mail, events and derived cards on this machine; drafts and note cards are kept.",
      confirm: "Clear the local cache?\nCached mail, events, Copilot history and derived cards are deleted; drafts and your note cards are kept.\nHit Sync afterwards to fetch mail again.",
      done: "Local cache cleared",
      fail: "Clear failed: ",
    },
  };
  const t = (k) => S[document.documentElement.lang.startsWith("zh") ? "zh" : "en"][k];
  const notify = (msg, isErr) => (typeof toast === "function" ? toast(msg, isErr) : console.log(msg));

  const foot = document.querySelector(".sidefoot");
  if (!foot || document.getElementById("cacheClearBtn")) return;
  const btn = document.createElement("button");
  btn.id = "cacheClearBtn";
  btn.className = "langbtn";
  const label = () => { btn.textContent = t("label"); btn.title = t("title"); };
  label();
  foot.insertBefore(btn, document.getElementById("langBtn") || null);
  new MutationObserver(label).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

  btn.onclick = async () => {
    if (!window.confirm(t("confirm"))) return;
    btn.disabled = true;
    try {
      const r = await fetch("/api/cache/clear", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lang: document.documentElement.lang }),
      });
      const data = await r.json();
      if (!r.ok || data.error) throw new Error(data.error || String(r.status));
      notify(t("done"));
      if (typeof state === "object" && typeof setView === "function") { state.selected = null; setView(state.view); }
      if (typeof refreshCounts === "function") refreshCounts();
    } catch (e) {
      notify(t("fail") + e.message, true);
    } finally {
      btn.disabled = false;
    }
  };
})();
