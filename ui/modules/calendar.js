/* Unified calendar view (replaces the core "calendar" list): week / month grid with extra time-zone
   columns, local create / edit / delete, RSVP chips, AI booking (create_event writes a .ics invite
   draft, never sent), colleague ICS feeds (URL or file) and a free/busy panel. */
(() => {
  "use strict";
  const S = {
    zh: {
      title: "行事曆", week: "週", month: "月", today: "今天", prev: "‹ 上一段", next: "下一段 ›",
      newEvent: "＋ 新增行程", aiBook: "✦ AI 代訂", freebusy: "同事空檔", zones: "時區", invites: "邀請草稿",
      allDay: "整天", more: "還有", items: "筆", loading: "載入中…", failed: "操作失敗：",
      edit: "編輯", del: "刪除", save: "儲存", cancel: "取消", close: "關閉", back: "← 返回",
      fTitle: "標題", fStart: "開始", fEnd: "結束", fTz: "時區", fLocation: "地點", fAttendees: "與會者（信箱，逗號分隔）",
      fRepeat: "重複", fDesc: "說明", fInvite: "產生 .ics 邀請草稿（不寄出）", fAllDay: "整天行程",
      repeat: { "": "不重複", daily: "每天", weekdays: "平日", weekly: "每週", monthly: "每月", custom: "自訂" },
      editTitle: "編輯行程", newTitle: "新增行程", readOnly: "同步來的行程在這裡唯讀；可以改你的回覆狀態。",
      saved: "已存到本機行事曆", deleted: "已刪除", confirmDel: "確定刪除這個行程？",
      organizer: "主辦", attendees: "與會者", yourRsvp: "你的回覆", rsvpReply: "同時產生 .ics 回覆草稿（不寄出）",
      accept: "接受", maybe: "未定", decline: "婉拒", needs: "待回覆", rsvpSaved: "回覆狀態已記在本機",
      status: { accepted: "已接受", tentative: "未定", declined: "已婉拒", "needs-action": "待回覆", organizer: "主辦" },
      source: { sync: "同步", local: "本機", agent: "AI 代訂", ics: "匯入", demo: "示範" },
      timesIn: "各時區時間", invite: "邀請草稿", download: "下載 .ics", noInvites: "還沒有邀請草稿。",
      notSent: "不會寄出：下載後自行附在信裡。", conflicts: "時間衝突", warnings: "提醒",
      aiTitle: "✦ AI 代訂（create_event）", aiHint: "用一句話描述，例如：下週二下午三點和 pat@example.com 討論 Q4 規劃 45 分鐘",
      aiPreview: "解析", aiBookNow: "建立並產生 .ics 草稿", aiNoStart: "沒有找到開始時間，請補上或改用表單。",
      aiSlot: "自動挑的空檔", aiOpenForm: "改用表單微調", parsedBy: "解析方式",
      zonesTitle: "時區設定", primaryTz: "主要時區", extraTz: "額外時區欄（最多 3 個）", weekStart: "每週開始",
      monday: "週一", sunday: "週日", addZone: "＋ 加時區", remove: "移除",
      fbTitle: "同事空檔（free/busy）", fbHint: "只用來顯示忙碌時段，不會寫進你的行事曆。", minutes: "會議長度",
      weekends: "含週末", freeSlots: "大家都有空", useSlot: "用這個時段", noSlots: "這段期間找不到共同空檔。",
      busy: "忙碌", me: "我", feeds: "同事行事曆", noFeeds: "還沒有匯入同事行事曆。",
      importUrl: "用網址訂閱 ICS", importFile: "匯入 ICS 檔", feedName: "名稱", feedEmail: "信箱（選填）",
      allowPrivate: "允許內網／http 位址", add: "匯入", demoFeeds: "載入示範同事（虛構）", refresh: "重新整理",
      importMine: "把收到的邀請 .ics 加進我的行事曆", imported: "已匯入", events: "行程", fbBlocks: "忙碌區段",
      privateBusy: "（忙碌）", hours: "小時", upcoming: "這段期間的行程",
    },
    en: {
      title: "Calendar", week: "Week", month: "Month", today: "Today", prev: "‹ Prev", next: "Next ›",
      newEvent: "+ New event", aiBook: "✦ AI booking", freebusy: "Free/busy", zones: "Time zones", invites: "Invite drafts",
      allDay: "All day", more: "more", items: "items", loading: "Loading…", failed: "Failed: ",
      edit: "Edit", del: "Delete", save: "Save", cancel: "Cancel", close: "Close", back: "← Back",
      fTitle: "Title", fStart: "Start", fEnd: "End", fTz: "Time zone", fLocation: "Location", fAttendees: "Attendees (emails, comma-separated)",
      fRepeat: "Repeat", fDesc: "Description", fInvite: "Write a .ics invite draft (not sent)", fAllDay: "All-day event",
      repeat: { "": "Does not repeat", daily: "Daily", weekdays: "Weekdays", weekly: "Weekly", monthly: "Monthly", custom: "Custom" },
      editTitle: "Edit event", newTitle: "New event", readOnly: "Synced events are read-only here; you can set your RSVP.",
      saved: "Saved to the local calendar", deleted: "Deleted", confirmDel: "Delete this event?",
      organizer: "Organizer", attendees: "Attendees", yourRsvp: "Your RSVP", rsvpReply: "Also write a .ics reply draft (not sent)",
      accept: "Accept", maybe: "Maybe", decline: "Decline", needs: "Needs reply", rsvpSaved: "RSVP recorded locally",
      status: { accepted: "Accepted", tentative: "Maybe", declined: "Declined", "needs-action": "Needs reply", organizer: "Organizer" },
      source: { sync: "Synced", local: "Local", agent: "AI booked", ics: "Imported", demo: "Demo" },
      timesIn: "Times by zone", invite: "Invite draft", download: "Download .ics", noInvites: "No invite drafts yet.",
      notSent: "Nothing is sent: download it and attach it yourself.", conflicts: "Conflicts", warnings: "Warnings",
      aiTitle: "✦ AI booking (create_event)", aiHint: "Describe it in one line, e.g. Book 45 min with pat@example.com next Tuesday at 3pm about Q4 roadmap",
      aiPreview: "Parse", aiBookNow: "Book and write .ics draft", aiNoStart: "No start time found; add one or use the form.",
      aiSlot: "Picked free slot", aiOpenForm: "Fine-tune in the form", parsedBy: "Parsed by",
      zonesTitle: "Time zone settings", primaryTz: "Primary time zone", extraTz: "Extra zone columns (up to 3)", weekStart: "Week starts on",
      monday: "Monday", sunday: "Sunday", addZone: "+ Add zone", remove: "Remove",
      fbTitle: "Colleague free/busy", fbHint: "Used only to show busy time; nothing is added to your calendar.", minutes: "Meeting length",
      weekends: "Include weekends", freeSlots: "Everyone is free", useSlot: "Use this slot", noSlots: "No common free slot in this range.",
      busy: "Busy", me: "Me", feeds: "Colleague calendars", noFeeds: "No colleague calendars imported yet.",
      importUrl: "Subscribe by ICS URL", importFile: "Import an ICS file", feedName: "Name", feedEmail: "Email (optional)",
      allowPrivate: "Allow private / http addresses", add: "Import", demoFeeds: "Load demo colleagues (fictional)", refresh: "Refresh",
      importMine: "Add a received invite .ics to my calendar", imported: "Imported", events: "events", fbBlocks: "busy blocks",
      privateBusy: "(busy)", hours: "h", upcoming: "In this range",
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
    if (!r.ok || d.error) { const e = new Error(d.error || String(r.status)); e.data = d; throw e; }
    return d;
  };
  const el = (id) => document.getElementById(id);
  const nav = el("nav");
  if (!nav || typeof state !== "object" || window.__tpiCalendar) return;
  window.__tpiCalendar = true;

  const HOUR = 44;
  const css = document.createElement("style");
  css.textContent = `
    #app.tcal-cal-wide { grid-template-columns: 234px minmax(560px, 1fr) minmax(340px, 31vw); }
    .tcal-cal { display: flex; flex-direction: column; height: 100%; min-height: 0; }
    .tcal-cal-bar { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 10px 12px; border-bottom: 1px solid var(--line); }
    .tcal-cal-bar .ttl { font-size: 15px; margin: 0 6px; white-space: nowrap; }
    .tcal-cal-bar .btn { font-size: 12px; padding: 4px 9px; }
    .tcal-cal-bar .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 9px; overflow: hidden; }
    .tcal-cal-bar .seg button { background: transparent; border: none; padding: 4px 10px; font-size: 12px; color: var(--muted); }
    .tcal-cal-bar .seg button.on { background: #2a241d; color: var(--ink); }
    .tcal-cal-bar .sp { flex: 1; }
    .tcal-wk { flex: 1; min-height: 0; overflow: auto; position: relative; }
    .tcal-wk-head, .tcal-wk-allday, .tcal-wk-body { display: grid; }
    .tcal-wk-head { position: sticky; top: 0; z-index: 4; background: #171410; border-bottom: 1px solid var(--line); }
    .tcal-wk-allday { position: sticky; z-index: 3; background: #171410; border-bottom: 1px solid var(--line); }
    .tcal-wk-head > div { padding: 5px 4px; font-size: 11.5px; text-align: center; color: var(--muted); border-left: 1px solid #221e1a; }
    .tcal-wk-head .zone { font-size: 10px; line-height: 1.25; }
    .tcal-wk-head .zone b { color: var(--accent2); font-weight: 600; display: block; }
    .tcal-wk-head .d.today { color: var(--accent); }
    .tcal-wk-head .d b { display: block; font-size: 15px; color: var(--ink); font-weight: 500; }
    .tcal-wk-head .d.today b { color: var(--accent); }
    .tcal-wk-allday > div { min-height: 22px; border-left: 1px solid #221e1a; padding: 2px; font-size: 10.5px; color: var(--muted); }
    .tcal-gut { position: relative; border-left: 1px solid #221e1a; }
    .tcal-gut .hl { position: absolute; right: 4px; font-size: 10px; color: var(--muted); transform: translateY(-6px); white-space: nowrap; }
    .tcal-gut .hl.shift { color: #7d7468; }
    .tcal-day { position: relative; border-left: 1px solid #221e1a; cursor: crosshair; }
    .tcal-day.weekend { background: rgba(255,255,255,.012); }
    .tcal-day .hr { position: absolute; left: 0; right: 0; border-top: 1px solid #201c18; pointer-events: none; }
    .tcal-day .off { position: absolute; left: 0; right: 0; background: rgba(0,0,0,.18); pointer-events: none; }
    .tcal-now { position: absolute; left: 0; right: 0; border-top: 2px solid var(--bad); z-index: 2; pointer-events: none; }
    .tcal-ev { position: absolute; box-sizing: border-box; border-radius: 6px; padding: 2px 5px; font-size: 11px; line-height: 1.3; overflow: hidden; cursor: pointer;
      text-align: left; background: #3a3020; border: 1px solid #5a4a30; border-left: 3px solid var(--accent); color: var(--ink); z-index: 1; }
    .tcal-ev:hover { z-index: 3; box-shadow: 0 4px 14px rgba(0,0,0,.45); }
    .tcal-ev .tm { color: var(--accent2); font-size: 10px; }
    .tcal-ev.short { white-space: nowrap; text-overflow: ellipsis; padding-top: 1px; }
    .tcal-ev.short .tm { display: inline; margin-right: 4px; }
    .tcal-chip { display: block; border-radius: 5px; padding: 1px 5px; margin: 1px 0; font-size: 10.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer;
      background: #3a3020; border: 1px solid #5a4a30; border-left: 3px solid var(--accent); color: var(--ink); }
    .tcal-src-sync { border-left-color: #8a9aa8 !important; background: #232a30 !important; border-color: #3a4650 !important; }
    .tcal-src-agent { border-left-color: var(--ok) !important; }
    .tcal-src-ics { border-left-color: #b48ead !important; }
    .tcal-st-tentative { background-image: repeating-linear-gradient(135deg, transparent 0 6px, rgba(255,255,255,.06) 6px 12px) !important; }
    .tcal-st-needs-action { background: transparent !important; border-style: dashed !important; }
    .tcal-st-declined { opacity: .45; text-decoration: line-through; }
    .tcal-rsvp { display: inline-block; font-size: 9.5px; border-radius: 999px; padding: 0 5px; margin-left: 3px; border: 1px solid var(--line); color: var(--muted); vertical-align: 1px; text-decoration: none; }
    .tcal-rsvp.accepted, .tcal-rsvp.organizer { color: var(--ok); border-color: #48603f; }
    .tcal-rsvp.tentative { color: var(--accent2); border-color: #6a5a3a; }
    .tcal-rsvp.declined { color: var(--bad); border-color: #6b3a32; }
    .tcal-rsvp.needs-action { color: var(--need); border-color: #6b4a3a; }
    .tcal-mo { flex: 1; min-height: 0; overflow: auto; display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); grid-template-rows: auto; grid-auto-rows: minmax(92px, 1fr); }
    .tcal-mo .wd { position: sticky; top: 0; background: #171410; text-align: center; font-size: 11px; color: var(--muted); padding: 4px; border-bottom: 1px solid var(--line); min-height: 0; }
    .tcal-mo .cell { border-right: 1px solid #221e1a; border-bottom: 1px solid #221e1a; padding: 3px 4px; min-width: 0; cursor: pointer; }
    .tcal-mo .cell.out { opacity: .45; }
    .tcal-mo .cell.weekend { background: rgba(255,255,255,.012); }
    .tcal-mo .cell .dn { font-size: 11.5px; color: var(--muted); display: inline-block; padding: 0 5px; border-radius: 999px; }
    .tcal-mo .cell.today .dn { background: var(--accent); color: #17130c; }
    .tcal-mo .cell .mr { font-size: 10px; color: var(--muted); padding-left: 4px; }
    .tcal-form { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
    .tcal-form label { font-size: 11.5px; color: var(--muted); display: flex; flex-direction: column; gap: 3px; }
    .tcal-form label.inline { flex-direction: row; align-items: center; gap: 6px; }
    .tcal-form input:not([type=checkbox]), .tcal-form select, .tcal-form textarea { background: #171410; border: 1px solid var(--line); border-radius: 8px; padding: 7px 9px; outline: none; color: var(--ink); }
    .tcal-form textarea { min-height: 64px; resize: vertical; }
    .tcal-form .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .tcal-form .acts { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
    .tcal-sec { margin: 16px 0 6px; font-size: 13px; color: var(--accent2); border-bottom: 1px dashed #3a332a; padding-bottom: 4px; }
    .tcal-li { display: flex; gap: 8px; align-items: center; padding: 5px 0; border-bottom: 1px solid #221e1a; font-size: 12.5px; flex-wrap: wrap; }
    .tcal-li .r { margin-left: auto; color: var(--muted); font-size: 11px; }
    .tcal-li .btn { font-size: 11px; padding: 2px 8px; }
    .tcal-note { font-size: 11.5px; color: var(--muted); padding: 7px 10px; border: 1px dashed #4a4136; border-radius: 8px; margin: 8px 0; }
    .tcal-warn { font-size: 12px; color: var(--need); margin: 4px 0; }
    .tcal-pre { white-space: pre-wrap; font-size: 11px; background: #120f0c; border: 1px solid var(--line); border-radius: 8px; padding: 8px; max-height: 220px; overflow: auto; font-family: ui-monospace, Menlo, monospace; }
    .tcal-rsvpbar { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin: 8px 0; }
    .tcal-rsvpbar .btn.on { border-color: var(--accent); color: var(--accent2); }
    .tcal-fb { display: grid; gap: 3px 6px; align-items: center; font-size: 11.5px; margin: 8px 0; }
    .tcal-fb .nm { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--ink); }
    .tcal-fb .dh { color: var(--muted); font-size: 10.5px; text-align: center; }
    .tcal-fb .trk { position: relative; height: 18px; background: #1e2a1d; border-radius: 4px; overflow: hidden; }
    .tcal-fb .trk.weekend { background: #1d1b18; }
    .tcal-fb .trk .b { position: absolute; top: 0; bottom: 0; background: #8a4a3c; border-left: 1px solid #b0604f; }
    .tcal-fb .trk .f { position: absolute; top: 0; bottom: 0; background: rgba(126,160,122,.55); }
    .tcal-zone { display: flex; gap: 6px; align-items: center; margin: 4px 0; }`;
  document.head.appendChild(css);

  const view = { mode: null, anchor: null, data: null, settings: null, pane: "home", detail: null, proposal: null, tzs: null };
  const pad = (n) => String(n).padStart(2, "0");
  const addMin = (local, minutes) => {
    const m = String(local).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!m) return local;
    const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) + minutes * 60000);
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  };
  const stTag = (st) => (st ? `<span class="tcal-rsvp ${h(st)}">${h(t("status")[st] || st)}</span>` : "");
  const evCls = (e) => `tcal-src-${h(e.source)} tcal-st-${h(e.my_status || "none")}`;
  const paneEl = () => el("pane");
  const listEl = () => el("list");

  async function ensureSettings() {
    if (!view.settings) view.settings = await getJSON("/api/cal/settings");
    if (!view.mode) view.mode = view.settings.view || "week";
    if (!view.anchor) view.anchor = view.settings.anchor;
    return view.settings;
  }

  async function load() {
    document.getElementById("app")?.classList.add("tcal-cal-wide");
    listEl().innerHTML = `<div class='empty'>${h(t("loading"))}</div>`;
    try {
      await ensureSettings();
      view.data = await getJSON(`/api/cal/view?view=${view.mode}&date=${encodeURIComponent(view.anchor)}`);
    } catch (e) {
      listEl().innerHTML = `<div class='empty'>${h(t("failed") + e.message)}</div>`;
      return;
    }
    const cnt = el("cnt-cal");
    if (cnt) cnt.textContent = view.data.count || "";
    renderGrid();
    renderPane();
  }

  function renderGrid() {
    const d = view.data;
    const bar = `<div class="tcal-cal-bar">
      <button class="btn" data-act="prev">${h(t("prev"))}</button>
      <button class="btn" data-act="today">${h(t("today"))}</button>
      <button class="btn" data-act="next">${h(t("next"))}</button>
      <span class="ttl">${h(d.title)}</span>
      <span class="seg"><button data-act="week" class="${view.mode === "week" ? "on" : ""}">${h(t("week"))}</button><button data-act="month" class="${view.mode === "month" ? "on" : ""}">${h(t("month"))}</button></span>
      <span class="sp"></span>
      <button class="btn primary" data-act="new">${h(t("newEvent"))}</button>
      <button class="btn" data-act="ai">${h(t("aiBook"))}</button>
      <button class="btn" data-act="fb">${h(t("freebusy"))}</button>
      <button class="btn ghost" data-act="zones">${h(t("zones"))}</button>
      <button class="btn ghost" data-act="invites">${h(t("invites"))}</button>
    </div>`;
    listEl().innerHTML = `<div class="tcal-cal">${bar}${view.mode === "week" ? weekHtml(d) : monthHtml(d)}</div>`;
    const box = listEl().querySelector(".tcal-wk");
    if (box) {
      const ad = box.querySelector(".tcal-wk-allday");
      const hd = box.querySelector(".tcal-wk-head");
      if (ad && hd) ad.style.top = hd.offsetHeight + "px";
      box.scrollTop = Math.max(0, ((view.settings?.work_start ?? 8) - 1) * HOUR);
    }
    listEl().onclick = onGridClick;
  }

  function weekHtml(d) {
    const zones = d.zones || [];
    const cols = `${zones.map(() => "52px").join(" ")} repeat(${d.days.length}, minmax(64px, 1fr))`;
    const ws = view.settings?.work_start ?? 9, we = view.settings?.work_end ?? 18;
    const head = zones.map((z) => `<div class="zone" title="${h(z.tz)}"><b>${h(z.city)}</b>${h(z.offset)}</div>`).join("") +
      d.days.map((day) => `<div class="d ${day.is_today ? "today" : ""}">${h(day.weekday)}<b>${h(day.day)}</b></div>`).join("");
    const allday = zones.map((z, i) => `<div>${i === 0 ? h(t("allDay")) : ""}</div>`).join("") +
      d.days.map((day) => `<div>${day.all_day.map((e) => `<span class="tcal-chip ${evCls(e)}" data-ev="${h(e.id)}" title="${h(e.title)}">${h(e.title)}${stTag(e.my_status)}</span>`).join("")}</div>`).join("");
    const gutters = zones.map((z, zi) => `<div class="tcal-gut" style="height:${24 * HOUR}px">${d.hours.map((hr) => {
      const lb = hr.labels[zi] || {};
      return hr.hour === 0 ? "" : `<span class="hl ${lb.shift ? "shift" : ""}" style="top:${hr.hour * HOUR}px">${h(lb.label)}${lb.shift ? (lb.shift > 0 ? "⁺¹" : "⁻¹") : ""}</span>`;
    }).join("")}</div>`).join("");
    const days = d.days.map((day) => {
      const lines = Array.from({ length: 24 }, (_, i) => `<div class="hr" style="top:${i * HOUR}px"></div>`).join("");
      const off = `<div class="off" style="top:0;height:${ws * HOUR}px"></div><div class="off" style="top:${we * HOUR}px;height:${(24 - we) * HOUR}px"></div>`;
      const now = day.date === d.now.date ? `<div class="tcal-now" style="top:${(d.now.minute / 60) * HOUR}px"></div>` : "";
      const evs = day.timed.map((e) => {
        const top = (e.top / 60) * HOUR, ht = Math.max(16, ((e.bottom - e.top) / 60) * HOUR - 2);
        const w = 100 / (e.ncols || 1);
        const short = ht < 34;
        const tip = `${e.time_label} ${e.title}${e.my_status ? " · " + (t("status")[e.my_status] || e.my_status) : ""}`;
        return `<div class="tcal-ev ${short ? "short" : ""} ${evCls(e)}" data-ev="${h(e.id)}" title="${h(tip)}" style="top:${top}px;height:${ht}px;left:calc(${w * (e.col || 0)}% + 1px);width:calc(${w}% - 3px)">` +
          (short ? `<span class="tm">${h(e.time_label)}</span>${h(e.title)}` : `<div class="tm">${h(e.time_label)}${stTag(e.my_status)}</div>${h(e.title)}`) + `</div>`;
      }).join("");
      return `<div class="tcal-day ${day.weekend ? "weekend" : ""}" data-day="${h(day.date)}" style="height:${24 * HOUR}px">${lines}${off}${now}${evs}</div>`;
    }).join("");
    return `<div class="tcal-wk"><div class="tcal-wk-head" style="grid-template-columns:${cols}">${head}</div>
      <div class="tcal-wk-allday" style="grid-template-columns:${cols}">${allday}</div>
      <div class="tcal-wk-body" style="grid-template-columns:${cols}">${gutters}${days}</div></div>`;
  }

  function monthHtml(d) {
    const head = d.days.slice(0, 7).map((day) => `<div class="wd">${h(day.weekday)}</div>`).join("");
    const cells = d.days.map((day) => {
      const shown = day.items.slice(0, 4).map((it) => `<span class="tcal-chip ${evCls(it)}" data-ev="${h(it.id)}" title="${h(it.title)}">${it.time_label ? h(it.time_label) + " " : ""}${h(it.title)}</span>`).join("");
      const more = day.items.length > 4 ? `<div class="mr">${h(t("more"))} ${day.items.length - 4} ${h(t("items"))}</div>` : "";
      return `<div class="cell ${day.in_month ? "" : "out"} ${day.is_today ? "today" : ""} ${day.weekend ? "weekend" : ""}" data-cell="${h(day.date)}"><span class="dn">${h(day.day)}</span>${shown}${more}</div>`;
    }).join("");
    return `<div class="tcal-mo">${head}${cells}</div>`;
  }

  function onGridClick(e) {
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act) {
      if (act === "prev" || act === "next") { view.anchor = view.data[act]; load(); }
      else if (act === "today") { view.anchor = view.data.today; load(); }
      else if (act === "week" || act === "month") { view.mode = act; postJSON("/api/cal/settings", { view: act }).catch(() => {}); load(); }
      else if (act === "new") openEditor(null, defaultStart());
      else if (act === "ai") showPane("ai");
      else if (act === "fb") showPane("fb");
      else if (act === "zones") showPane("zones");
      else if (act === "invites") showPane("invites");
      return;
    }
    const ev = e.target.closest("[data-ev]");
    if (ev) { openEvent(ev.dataset.ev); return; }
    const cell = e.target.closest("[data-cell]");
    if (cell) {
      if (e.target.classList.contains("dn")) { view.anchor = cell.dataset.cell; view.mode = "week"; load(); }
      else openEditor(null, cell.dataset.cell + "T09:00");
      return;
    }
    const day = e.target.closest(".tcal-day");
    if (day) {
      const rect = day.getBoundingClientRect();
      const minute = Math.max(0, Math.min(1410, Math.floor(((e.clientY - rect.top) / HOUR) * 2) * 30));
      openEditor(null, `${day.dataset.day}T${pad(Math.floor(minute / 60))}:${pad(minute % 60)}`);
    }
  }

  function defaultStart() {
    const day = view.data?.days.find((d) => d.date === view.data.today) ? view.data.today : view.anchor;
    const now = new Date();
    const hr = day === view.data?.today ? Math.min(22, now.getHours() + 1) : (view.settings?.work_start ?? 9);
    return `${day}T${pad(hr)}:00`;
  }

  function showPane(name, detail) {
    view.pane = name;
    if (detail !== undefined) view.detail = detail;
    renderPane();
  }

  function renderPane() {
    const p = view.pane;
    if (p === "event") return renderEvent();
    if (p === "edit") return renderEditor();
    if (p === "ai") return renderAi();
    if (p === "fb") return renderFreebusy();
    if (p === "zones") return renderZones();
    if (p === "invites") return renderInvites();
    const d = view.data;
    const upcoming = (d?.days || []).flatMap((day) => [...day.all_day, ...day.timed].map((e) => ({ ...e, date: day.date })));
    const seen = new Set();
    const rows = upcoming.filter((e) => { const k = e.id + e.instance; if (seen.has(k)) return false; seen.add(k); return true; });
    paneEl().innerHTML = `<h2 class="mh">${h(t("title"))}</h2>
      <p class="muted" style="margin:0">${h(d?.title || "")} · ${h(d?.tz || "")} · ${h(d?.count || 0)} ${h(t("items"))}</p>
      <div class="tcal-sec">${h(t("upcoming"))}</div>
      ${rows.map((e) => `<div class="tcal-li" data-ev="${h(e.id)}" style="cursor:pointer">
        <span>${h(e.start.replace("T", " ").slice(5, 16))}</span><b>${h(e.title)}</b>${stTag(e.my_status)}
        <span class="r">${h(t("source")[e.source] || e.source)}</span></div>`).join("") || `<p class="muted">—</p>`}
      <div class="tcal-note">${h(t("notSent"))}</div>`;
    paneEl().onclick = (e) => { const r = e.target.closest("[data-ev]"); if (r) openEvent(r.dataset.ev); };
  }

  async function openEvent(id) {
    try {
      const d = await getJSON(`/api/cal/event/${encodeURIComponent(id)}?x=1`);
      showPane("event", d);
    } catch (e) { notify(t("failed") + e.message, true); }
  }

  function renderEvent() {
    const d = view.detail, ev = d.event;
    const people = (ev.attendees || []).map((a) => `<div class="tcal-li"><span>${h(a.name || a.email)}</span><span class="muted">${h(a.name ? a.email : "")}</span>${stTag(a.status)}</div>`).join("");
    const counts = ev.rsvp_counts || {};
    const canRsvp = ev.can_rsvp && ev.my_status !== "organizer";
    const rsvp = canRsvp ? `<div class="tcal-sec">${h(t("yourRsvp"))}: ${stTag(ev.my_status || "needs-action")}</div>
      <div class="tcal-rsvpbar">
        ${[["accepted", "accept"], ["tentative", "maybe"], ["declined", "decline"]].map(([st, k]) => `<button class="btn ${ev.my_status === st ? "on" : ""}" data-rsvp="${st}">${h(t(k))}</button>`).join("")}
        <label class="muted" style="font-size:11.5px"><input type="checkbox" id="tpiRsvpReply" /> ${h(t("rsvpReply"))}</label>
      </div>` : "";
    const invites = (d.invites || []).map((i) => `<div class="tcal-li"><span>${h(i.method)}</span><span>${h(i.filename)}</span><span class="r">${h(i.created_at.slice(5, 16))}</span><a class="btn" href="${h(i.url)}" download="${h(i.filename)}">${h(t("download"))}</a></div>`).join("");
    paneEl().innerHTML = `<button class="btn ghost" data-a="back">${h(t("back"))}</button>
      <h2 class="mh" style="margin-top:8px">${h(ev.title)} ${stTag(ev.my_status)}</h2>
      <p class="muted" style="margin:0">${h(t("source")[ev.source] || ev.source)} · ${h(ev.calendar_name)}${ev.location ? " · " + h(ev.location) : ""}${ev.repeat ? " · " + h(t("repeat")[ev.repeat] || ev.repeat) : ""}</p>
      <div class="tcal-sec">${h(t("timesIn"))}</div>
      ${(d.times || []).map((x) => `<div class="tcal-li"><b>${h(x.city)}</b><span class="muted">${h(x.offset)}</span><span class="r" style="color:var(--ink);font-size:12px">${h(x.text)}</span></div>`).join("")}
      ${ev.organizer ? `<div class="tcal-sec">${h(t("organizer"))}</div><div class="tcal-li">${h(ev.organizer.name || ev.organizer.email)} <span class="muted">${h(ev.organizer.name ? ev.organizer.email : "")}</span></div>` : ""}
      ${people ? `<div class="tcal-sec">${h(t("attendees"))} · ✓${h(counts.accepted || 0)} ?${h(counts.tentative || 0)} ✕${h(counts.declined || 0)} …${h(counts["needs-action"] || 0)}</div>${people}` : ""}
      ${rsvp}
      ${ev.description ? `<div class="tcal-sec">${h(t("fDesc"))}</div><div style="white-space:pre-wrap;font-size:13px">${h(ev.description)}</div>` : ""}
      ${invites ? `<div class="tcal-sec">${h(t("invite"))}</div>${invites}<div class="tcal-note">${h(t("notSent"))}</div>` : ""}
      <div class="actionbar">
        ${ev.editable ? `<button class="btn primary" data-a="edit">${h(t("edit"))}</button><button class="btn ghost" data-a="del">${h(t("del"))}</button>` : `<span class="muted" style="font-size:12px">${h(t("readOnly"))}</span>`}
      </div>`;
    paneEl().onclick = async (e) => {
      const a = e.target.closest("[data-a]")?.dataset.a;
      const st = e.target.closest("[data-rsvp]")?.dataset.rsvp;
      if (a === "back") showPane("home");
      else if (a === "edit") openEditor(ev.id);
      else if (a === "del") {
        if (!confirm(t("confirmDel"))) return;
        try { const r = await postJSON("/api/cal/event/delete", { id: ev.id }); notify(r.note || t("deleted")); view.pane = "home"; load(); }
        catch (err) { notify(t("failed") + err.message, true); }
      } else if (st) {
        try {
          const r = await postJSON("/api/cal/rsvp", { id: ev.id, status: st, make_reply: !!el("tpiRsvpReply")?.checked });
          notify(r.note || t("rsvpSaved"));
          await load();
          openEvent(ev.id);
        } catch (err) { notify(t("failed") + err.message, true); }
      }
    };
  }

  async function openEditor(id, start, prefill) {
    let form;
    if (id) {
      const d = view.detail?.event?.id === id ? view.detail : await getJSON(`/api/cal/event/${encodeURIComponent(id)}?x=1`).catch(() => null);
      if (!d) return;
      form = { id, ...d.edit };
    } else {
      const s = start || defaultStart();
      form = { title: "", all_day: false, tz: view.settings?.tz || "", start: s, end: addMin(s, view.settings?.slot_minutes || 30), location: "", description: "", repeat: "", attendees: "", ...(prefill || {}) };
    }
    view.form = form;
    view.result = null;
    showPane("edit");
  }

  function tzOptions(sel) {
    const all = [...new Set([...(view.settings?.timezones || []), sel].filter(Boolean))];
    return all.map((z) => `<option value="${h(z)}" ${z === sel ? "selected" : ""}>${h(z)}</option>`).join("");
  }

  function renderEditor() {
    const f = view.form;
    const typ = f.all_day ? "date" : "datetime-local";
    const val = (v) => (f.all_day ? String(v || "").slice(0, 10) : String(v || "").slice(0, 16));
    const res = view.result;
    paneEl().innerHTML = `<button class="btn ghost" data-a="back">${h(t("back"))}</button>
      <h2 class="mh" style="margin-top:8px">${h(f.id ? t("editTitle") : t("newTitle"))}</h2>
      <div class="tcal-form" id="tpiForm">
        <label>${h(t("fTitle"))}<input name="title" value="${h(f.title)}" /></label>
        <label class="inline"><input type="checkbox" name="all_day" ${f.all_day ? "checked" : ""} /> ${h(t("fAllDay"))}</label>
        <div class="two"><label>${h(t("fStart"))}<input name="start" type="${typ}" value="${h(val(f.start))}" /></label>
          <label>${h(t("fEnd"))}<input name="end" type="${typ}" value="${h(val(f.end))}" /></label></div>
        <div class="two"><label>${h(t("fTz"))}<select name="tz">${tzOptions(f.tz)}</select></label>
          <label>${h(t("fRepeat"))}<select name="repeat">${Object.keys(t("repeat")).filter((k) => k !== "custom" || f.repeat === "custom").map((k) => `<option value="${h(k)}" ${k === (f.repeat || "") ? "selected" : ""}>${h(t("repeat")[k])}</option>`).join("")}</select></label></div>
        <label>${h(t("fLocation"))}<input name="location" value="${h(f.location)}" /></label>
        <label>${h(t("fAttendees"))}<input name="attendees" value="${h(f.attendees)}" placeholder="pat@example.com, lee@example.com" /></label>
        <label>${h(t("fDesc"))}<textarea name="description">${h(f.description)}</textarea></label>
        <label class="inline"><input type="checkbox" name="make_invite" ${f.make_invite === false ? "" : "checked"} /> ${h(t("fInvite"))}</label>
        <div class="acts"><button class="btn primary" data-a="save">${h(t("save"))}</button><button class="btn ghost" data-a="back">${h(t("cancel"))}</button></div>
      </div>
      ${res ? resultHtml(res) : ""}
      <div class="tcal-note">${h(t("notSent"))}</div>`;
    const formEl = el("tpiForm");
    formEl.querySelector("[name=all_day]").onchange = (e) => { view.form = { ...readForm(), all_day: e.target.checked }; renderEditor(); };
    paneEl().onclick = async (e) => {
      const a = e.target.closest("[data-a]")?.dataset.a;
      if (a === "back") { if (f.id) openEvent(f.id); else showPane("home"); }
      else if (a === "save") {
        const body = readForm();
        view.form = body;
        if (body.repeat === "custom") delete body.repeat;
        try {
          const r = await postJSON("/api/cal/event", body);
          notify(t("saved"));
          view.result = r;
          view.form = { ...body, id: r.event?.id || body.id };
          await load();
          view.pane = "edit";
          renderEditor();
        } catch (err) { notify(t("failed") + err.message, true); }
      }
    };
  }

  function readForm() {
    const q = (n) => el("tpiForm").querySelector(`[name=${n}]`);
    const allDay = q("all_day").checked;
    return { id: view.form.id, title: q("title").value.trim(), all_day: allDay, start: q("start").value, end: q("end").value || undefined,
      tz: q("tz").value, repeat: q("repeat").value, location: q("location").value, attendees: q("attendees").value,
      description: q("description").value, make_invite: q("make_invite").checked && !!q("attendees").value.trim() };
  }

  function resultHtml(r) {
    const inv = r.invite || r.reply;
    return `${r.note ? `<div class="tcal-note">${h(r.note)}</div>` : ""}
      ${(r.warnings || []).map((w) => `<div class="tcal-warn">⚠ ${h(w)}</div>`).join("")}
      ${(r.conflicts || []).length ? `<div class="tcal-sec">${h(t("conflicts"))}</div>${r.conflicts.map((c) => `<div class="tcal-warn">⚠ ${h(c.who)} · ${h(c.title || t("privateBusy"))} · ${h(c.start.replace("T", " ").slice(5))} – ${h(c.end.slice(11))}</div>`).join("")}` : ""}
      ${inv ? `<div class="tcal-sec">${h(t("invite"))} · ${h(inv.method)} · sent: false</div>
        <div class="tcal-li"><span>${h(inv.filename)}</span><span class="muted">${h((inv.recipients || []).join(", "))}</span><a class="btn" href="${h(inv.url)}" download="${h(inv.filename)}">${h(t("download"))}</a></div>
        <div class="tcal-pre">${h(inv.ics || "")}</div>` : ""}`;
  }

  function renderAi() {
    const pr = view.proposal;
    const p = pr?.proposal;
    paneEl().innerHTML = `<button class="btn ghost" data-a="back">${h(t("back"))}</button>
      <h2 class="mh" style="margin-top:8px">${h(t("aiTitle"))}</h2>
      <div class="tcal-form"><textarea id="tpiAsk" placeholder="${h(t("aiHint"))}">${h(view.ask || "")}</textarea>
        <div class="acts"><button class="btn" data-a="parse">${h(t("aiPreview"))}</button>
        <button class="btn primary" data-a="book">${h(t("aiBookNow"))}</button></div></div>
      ${pr ? `<div class="tcal-sec">${h(t("parsedBy"))}: ${h(pr.label)}</div>
        ${pr.error ? `<div class="tcal-warn">⚠ ${h(pr.error)}</div>` : ""}
        ${p.start ? `<div class="tcal-li"><b>${h(p.title)}</b><span class="r" style="color:var(--ink)">${h(p.start.replace("T", " "))} – ${h(p.end.slice(11))} · ${h(p.tz)}</span></div>
          ${p.attendees.length ? `<div class="tcal-li">${h(t("attendees"))}: ${h(p.attendees.join(", "))}</div>` : ""}
          ${p.location ? `<div class="tcal-li">${h(t("fLocation"))}: ${h(p.location)}</div>` : ""}
          ${pr.slot ? `<div class="tcal-li muted">${h(t("aiSlot"))}: ${h(pr.slot.reason)}</div>` : ""}
          ${(pr.conflicts || []).map((c) => `<div class="tcal-warn">⚠ ${h(c.who)} · ${h(c.title || t("privateBusy"))} · ${h(c.start.replace("T", " ").slice(5))}</div>`).join("")}
          <div class="acts" style="margin-top:6px"><button class="btn ghost" data-a="form">${h(t("aiOpenForm"))}</button></div>`
        : `<div class="tcal-warn">${h(t("aiNoStart"))}</div>`}` : ""}
      ${view.aiResult ? resultHtml(view.aiResult) : ""}
      <div class="tcal-note">${h(t("notSent"))}</div>`;
    paneEl().onclick = async (e) => {
      const a = e.target.closest("[data-a]")?.dataset.a;
      if (!a) return;
      if (a === "back") { view.proposal = null; view.aiResult = null; showPane("home"); return; }
      if (a === "form" && p) { openEditor(null, p.start, { ...p, attendees: p.attendees.join(", ") }); return; }
      view.ask = el("tpiAsk").value.trim();
      if (!view.ask) return;
      try {
        if (a === "parse") { view.proposal = await postJSON("/api/cal/agent/propose", { ask: view.ask }); view.aiResult = null; }
        else if (a === "book") {
          const args = p && p.start ? { ...p, ask: view.ask } : { ask: view.ask };
          view.aiResult = await postJSON("/api/cal/agent/create_event", args);
          notify(t("saved"));
          await load();
          view.pane = "ai";
        }
      } catch (err) { notify(t("failed") + err.message, true); }
      renderAi();
    };
  }

  async function renderZones() {
    const s = await ensureSettings();
    if (!view.tzs) view.tzs = await getJSON("/api/cal/timezones").catch(() => ({ all: [] }));
    const list = `<datalist id="tpiTzList">${[...new Set([...(s.timezones || []), ...(view.tzs.all || [])])].map((z) => `<option value="${h(z)}"></option>`).join("")}</datalist>`;
    paneEl().innerHTML = `<button class="btn ghost" data-a="back">${h(t("back"))}</button>
      <h2 class="mh" style="margin-top:8px">${h(t("zonesTitle"))}</h2>${list}
      <div class="tcal-form">
        <label>${h(t("primaryTz"))}<input id="tpiTz" list="tpiTzList" value="${h(s.tz)}" /></label>
        <label>${h(t("extraTz"))}</label>
        <div id="tpiZones">${s.extra_tzs.map((z) => zoneRow(z)).join("")}</div>
        <div class="acts"><button class="btn ghost" data-a="addzone">${h(t("addZone"))}</button></div>
        <label>${h(t("weekStart"))}<select id="tpiWs"><option value="1" ${s.week_start === 1 ? "selected" : ""}>${h(t("monday"))}</option><option value="0" ${s.week_start === 0 ? "selected" : ""}>${h(t("sunday"))}</option></select></label>
        <div class="acts"><button class="btn primary" data-a="save">${h(t("save"))}</button></div>
      </div>
      <div class="tcal-sec">${h(t("timesIn"))}</div>
      ${(s.tz_labels || []).map((z) => `<div class="tcal-li"><b>${h(z.city)}</b><span class="r">${h(z.tz)} · ${h(z.offset)}</span></div>`).join("")}`;
    paneEl().onclick = async (e) => {
      const a = e.target.closest("[data-a]")?.dataset.a;
      if (a === "back") showPane("home");
      else if (a === "addzone") { if (el("tpiZones").children.length < 3) el("tpiZones").insertAdjacentHTML("beforeend", zoneRow("")); }
      else if (a === "rmzone") e.target.closest(".tcal-zone").remove();
      else if (a === "save") {
        const extra = [...el("tpiZones").querySelectorAll("input")].map((i) => i.value.trim()).filter(Boolean);
        try {
          view.settings = await postJSON("/api/cal/settings", { tz: el("tpiTz").value.trim(), extra_tzs: extra, week_start: parseInt(el("tpiWs").value, 10) });
          notify(t("saved"));
          await load();
          showPane("zones");
        } catch (err) { notify(t("failed") + err.message, true); }
      }
    };
  }
  const zoneRow = (z) => `<div class="tcal-zone tcal-form" style="margin:0"><input list="tpiTzList" value="${h(z)}" style="flex:1" /><button class="btn ghost" data-a="rmzone">${h(t("remove"))}</button></div>`;

  async function renderInvites() {
    const d = await getJSON("/api/cal/invites").catch(() => ({ invites: [] }));
    paneEl().innerHTML = `<button class="btn ghost" data-a="back">${h(t("back"))}</button>
      <h2 class="mh" style="margin-top:8px">${h(t("invites"))}</h2>
      <div class="tcal-note">${h(t("notSent"))}</div>
      ${d.invites.map((i) => `<div class="tcal-li"><span class="tcal-rsvp">${h(i.method)}</span><b data-ev="${h(i.event_id)}" style="cursor:pointer">${h(i.summary)}</b>
        <span class="muted">${h(i.recipients.join(", "))}</span><span class="r">${h(i.created_at.slice(5, 16))}</span>
        <a class="btn" href="${h(i.url)}" download="${h(i.filename)}">${h(t("download"))}</a></div>`).join("") || `<p class="muted">${h(t("noInvites"))}</p>`}`;
    paneEl().onclick = (e) => {
      if (e.target.closest("[data-a=back]")) showPane("home");
      const r = e.target.closest("[data-ev]"); if (r) openEvent(r.dataset.ev);
    };
  }

  async function renderFreebusy() {
    const fbOpts = view.fbOpts || (view.fbOpts = { minutes: view.settings?.slot_minutes || 30, weekends: false, off: [] });
    const start = view.data?.days?.[0]?.date || view.anchor;
    const days = view.mode === "week" ? 7 : 14;
    let feeds = [], fb = null;
    try {
      feeds = (await getJSON("/api/cal/feeds")).feeds;
      const ids = feeds.filter((f) => !fbOpts.off.includes(f.id)).map((f) => f.id).join(",");
      fb = await getJSON(`/api/cal/freebusy?start=${start}&days=${days}&minutes=${fbOpts.minutes}&weekends=${fbOpts.weekends ? 1 : 0}&feeds=${ids || "0"}`);
    } catch (e) { paneEl().innerHTML = `<p class="muted">${h(t("failed") + e.message)}</p>`; return; }
    const ws = fb.work_start, we = fb.work_end, span = (we - ws) * 60;
    const pos = (a, b) => {
      const s = Math.max(a, ws * 60), e = Math.min(b, we * 60);
      return e <= s ? null : `left:${((s - ws * 60) / span) * 100}%;width:${((e - s) / span) * 100}%`;
    };
    const cols = `110px repeat(${fb.days.length}, minmax(26px, 1fr))`;
    const head = `<div></div>` + fb.days.map((d) => `<div class="dh">${h(d.weekday)}<br>${h(d.date.slice(5))}</div>`).join("");
    const rows = fb.people.map((p) => `<div class="nm" title="${h(p.email)}">${h(p.kind === "me" ? t("me") : p.name)}${p.error ? " ⚠" : ""}</div>` +
      p.days.map((segs, i) => `<div class="trk ${fb.days[i].weekend ? "weekend" : ""}">${segs.map((s) => { const st = pos(s.from_min, s.to_min); return st ? `<span class="b" style="${st}" title="${h(s.start.slice(11))}–${h(s.end.slice(11))} ${h(s.title || t("privateBusy"))}"></span>` : ""; }).join("")}</div>`).join("")).join("");
    const freeRow = `<div class="nm" style="color:var(--ok)">${h(t("freeSlots"))}</div>` + fb.days.map((d) => `<div class="trk">${fb.free_slots.filter((s) => s.date === d.date).map((s) => { const st = pos(s.from_min, s.to_min); return st ? `<span class="f" style="${st}"></span>` : ""; }).join("")}</div>`).join("");
    const emails = feeds.filter((f) => f.email && !fbOpts.off.includes(f.id)).map((f) => f.email);
    paneEl().innerHTML = `<button class="btn ghost" data-a="back">${h(t("back"))}</button>
      <h2 class="mh" style="margin-top:8px">${h(t("fbTitle"))}</h2>
      <p class="muted" style="margin:0;font-size:12px">${h(fb.tz)} · ${h(ws)}:00–${h(we)}:00 · ${h(t("fbHint"))}</p>
      <div class="tcal-form" style="flex-direction:row;align-items:end;gap:10px;flex-wrap:wrap">
        <label>${h(t("minutes"))}<select id="tpiFbMin">${[15, 30, 45, 60, 90, 120].map((m) => `<option ${m === fbOpts.minutes ? "selected" : ""}>${m}</option>`).join("")}</select></label>
        <label class="inline"><input type="checkbox" id="tpiFbWe" ${fbOpts.weekends ? "checked" : ""} /> ${h(t("weekends"))}</label>
      </div>
      <div class="tcal-fb" style="grid-template-columns:${cols}">${head}${rows}${freeRow}</div>
      <div class="tcal-sec">${h(t("freeSlots"))}</div>
      ${fb.free_slots.slice(0, 12).map((s, i) => `<div class="tcal-li"><span>${h(s.date.slice(5))} ${h(s.start.slice(11))}–${h(s.end.slice(11))}</span><span class="muted">${h(Math.round(s.minutes / 6) / 10)}${h(t("hours"))}</span><button class="btn r" style="margin-left:auto" data-slot="${i}">${h(t("useSlot"))}</button></div>`).join("") || `<p class="muted">${h(t("noSlots"))}</p>`}
      <div class="tcal-sec">${h(t("feeds"))}</div>
      ${feeds.map((f) => `<div class="tcal-li"><input type="checkbox" data-feed="${h(f.id)}" ${fbOpts.off.includes(f.id) ? "" : "checked"} />
        <b>${h(f.name)}</b><span class="muted">${h(f.email)}</span><span class="muted">${h(f.kind === "url" ? f.url : f.filename)}</span>
        <span class="r">${h(f.events)} ${h(t("events"))} · ${h(f.freebusy)} ${h(t("fbBlocks"))}</span>
        ${f.error ? `<span class="tcal-warn">⚠ ${h(f.error)}</span>` : ""}
        ${f.kind === "url" ? `<button class="btn" data-a="refresh" data-id="${h(f.id)}">${h(t("refresh"))}</button>` : ""}
        <button class="btn ghost" data-a="rmfeed" data-id="${h(f.id)}">${h(t("remove"))}</button></div>`).join("") || `<p class="muted">${h(t("noFeeds"))}</p>`}
      <div class="acts" style="margin:8px 0"><button class="btn" data-a="demo">${h(t("demoFeeds"))}</button></div>
      <div class="tcal-sec">${h(t("importUrl"))}</div>
      <div class="tcal-form" id="tpiFeedUrl">
        <input name="url" placeholder="https://calendar.example.com/pat.ics" />
        <div class="two"><input name="name" placeholder="${h(t("feedName"))}" /><input name="email" placeholder="${h(t("feedEmail"))}" /></div>
        <label class="inline"><input type="checkbox" name="allow_private" /> ${h(t("allowPrivate"))}</label>
        <div class="acts"><button class="btn primary" data-a="addurl">${h(t("add"))}</button></div>
      </div>
      <div class="tcal-sec">${h(t("importFile"))}</div>
      <div class="tcal-form" id="tpiFeedFile">
        <input name="file" type="file" accept=".ics,text/calendar" />
        <div class="two"><input name="name" placeholder="${h(t("feedName"))}" /><input name="email" placeholder="${h(t("feedEmail"))}" /></div>
        <div class="acts"><button class="btn primary" data-a="addfile">${h(t("add"))}</button></div>
      </div>
      <div class="tcal-sec">${h(t("importMine"))}</div>
      <div class="tcal-form" id="tpiMine"><input name="file" type="file" accept=".ics,text/calendar" />
        <div class="acts"><button class="btn" data-a="mine">${h(t("add"))}</button></div></div>`;
    el("tpiFbMin").onchange = (e) => { fbOpts.minutes = parseInt(e.target.value, 10); renderFreebusy(); };
    el("tpiFbWe").onchange = (e) => { fbOpts.weekends = e.target.checked; renderFreebusy(); };
    paneEl().querySelectorAll("[data-feed]").forEach((c) => {
      c.onchange = () => {
        const id = parseInt(c.dataset.feed, 10);
        fbOpts.off = c.checked ? fbOpts.off.filter((x) => x !== id) : [...fbOpts.off, id];
        renderFreebusy();
      };
    });
    const readFile = (input) => new Promise((ok, bad) => {
      const file = input.files?.[0];
      if (!file) return bad(new Error("no file"));
      const r = new FileReader();
      r.onload = () => ok({ text: String(r.result), name: file.name });
      r.onerror = () => bad(r.error);
      r.readAsText(file);
    });
    paneEl().onclick = async (e) => {
      const b = e.target.closest("[data-a],[data-slot]");
      if (!b) return;
      const a = b.dataset.a;
      try {
        if (b.dataset.slot !== undefined) {
          const s = fb.free_slots[parseInt(b.dataset.slot, 10)];
          openEditor(null, s.start, { end: addMin(s.start, fbOpts.minutes), tz: fb.tz, attendees: emails.join(", ") });
          return;
        }
        if (a === "back") { showPane("home"); return; }
        if (a === "demo") { await postJSON("/api/cal/feeds/demo", {}); notify(t("imported")); }
        else if (a === "refresh") { await postJSON("/api/cal/feed/refresh", { id: parseInt(b.dataset.id, 10) }); notify(t("imported")); }
        else if (a === "rmfeed") { await postJSON("/api/cal/feed/delete", { id: parseInt(b.dataset.id, 10) }); notify(t("deleted")); }
        else if (a === "addurl") {
          const f = el("tpiFeedUrl"), q = (n) => f.querySelector(`[name=${n}]`);
          const r = await postJSON("/api/cal/feeds", { url: q("url").value.trim(), name: q("name").value.trim(), email: q("email").value.trim(), allow_private: q("allow_private").checked });
          notify(r.note || t("imported"));
        } else if (a === "addfile") {
          const f = el("tpiFeedFile"), q = (n) => f.querySelector(`[name=${n}]`);
          const file = await readFile(q("file"));
          const r = await postJSON("/api/cal/feeds", { ics: file.text, filename: file.name, name: q("name").value.trim(), email: q("email").value.trim() });
          notify(r.note || t("imported"));
        } else if (a === "mine") {
          const file = await readFile(el("tpiMine").querySelector("[name=file]"));
          const r = await postJSON("/api/cal/import", { ics: file.text });
          notify(r.note || t("imported"));
          await load();
          view.pane = "fb";
        }
      } catch (err) { notify(t("failed") + err.message, true); }
      renderFreebusy();
    };
  }

  window.loadCal = load;
  const coreSetView = window.setView;
  if (typeof coreSetView === "function") {
    window.setView = (v, ...rest) => {
      if (v !== "calendar") document.getElementById("app")?.classList.remove("tcal-cal-wide");
      return coreSetView(v, ...rest);
    };
  }
  new MutationObserver(() => {
    if (state.view !== "calendar") return;
    view.settings = null;
    view.data = null;
    load();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });

  if (state.view === "calendar" || new URLSearchParams(location.hash.slice(1)).get("view") === "calendar") window.setView("calendar");
  else getJSON("/api/cal/view?view=week").then((d) => { const c = el("cnt-cal"); if (c) c.textContent = d.count || ""; }).catch(() => {});
})();
