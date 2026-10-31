# 保存與刪除機制盤點

本文件說明 openinbox 目前的資料保存行為、可用的刪除操作、刪除完整性缺口，並提出建議保留期與當事人權利請求的處理程序。

## 1. 現況總結

| 問題 | 現況 | 證據 |
|---|---|---|
| 是否有自動保留期（TTL） | **沒有**。程式未見任何定期清除或到期刪除機制 | `[B]`／`[C]` 需以程式碼確認 |
| 是否有單一「全部刪除」入口 | 有，`POST /api/cache/clear`（側欄「清除本機快取」） | `[A]` README |
| 該入口是否刪除全部資料 | **沒有**。草稿、使用者筆記卡、本機／匯入行事曆、邀請草稿會保留 | `[A]` README、`[B]` ARCHITECTURE 5.9 |
| 是否能只刪某位資料主體的資料 | **沒有**。只能整批清除或使用者手動操作個別郵件／聯絡人 | `[A]`／`[C]` |
| 是否有備份／還原 | 沒有內建流程 | `[A]` ROADMAP 第 1 項 |
| 是否有刪除稽核紀錄 | 未見 | `[C]` |
| 是否安全抹除（覆寫／VACUUM） | 未見 | `[C]` |

## 2. 可用刪除操作一覽

| 操作 | 範圍 | 保留什麼 | 證據 |
|---|---|---|---|
| `POST /api/cache/clear`（可帶 `{"reseed": true}`） | 郵件快取、示範／快取行事曆、`agent_turns`、衍生卡片、衍生人格與索引 | 草稿、使用者自寫卡片、本機建立或匯入的行事曆、`cal_feeds`、邀請草稿 | `[A]` README、`[B]` ARCHITECTURE 5.9 |
| 個別郵件「刪除／封存／移動」 | 本機狀態（資料夾、已讀、星號） | 遠端信箱完全不變（IMAP 使用 `EXAMINE`＋`BODY.PEEK`） | `[A]` README、`[B]` mailops |
| `POST /api/cal/feed/delete`（`{"id": N}`） | 單一同事 ICS feed | 其他 feed 與本機事件 | `[A]` README |
| `POST /api/crm/contacts/delete` | 單一 CRM 聯絡人 | 其他聯絡人 | `[A]` README |
| 草稿刪除 | 單一草稿 | 其他草稿 | `[B]` |
| 成果卡片刪除 | **未見 API** | — | `[C]` `agents.py` 只有列出與讀取 |
| `data/slides/`、`data/usage.jsonl` 刪除 | **未見 API** | — | `[C]` |
| 解除安裝 | 需使用者自行刪除 `data/`、`vault/`、`accounts.json`、`agent.json`、`rules.json` | 無自動清理 | `[A]` `install.sh`／`.gitignore` |

## 3. 刪除完整性缺口

即使使用者按下「清除本機快取」，下列位置仍可能保留資料：

| # | 位置 | 為什麼會殘留 | 建議 |
|---|---|---|---|
| D1 | SQLite WAL／SHM（`*.db-wal`、`*.db-shm`） | 交易日誌可能仍含已刪資料，直到 checkpoint | 清除後執行 `PRAGMA wal_checkpoint(TRUNCATE)` |
| D2 | SQLite 未使用的頁面 | 刪除只是標記，資料仍在檔案中 | 提供可選 `VACUUM`，或設定 `PRAGMA secure_delete` |
| D3 | FTS5 索引與 shadow table | 需確認刪信時 trigger 覆蓋所有刪除路徑 | 加測試：刪信後搜尋不到，且 `search_docs` 無殘留 |
| D4 | `data/deliverables/` | 未列入清除清單 `[C]` | 納入清除或提供刪除 API |
| D5 | `data/slides/` | 未列入清除清單 `[C]` | 納入清除或提供刪除 API |
| D6 | `data/contacts.json` | 需逐一刪除 | 提供「全部清除」選項 |
| D7 | `data/usage.jsonl` | 未列入清除清單 | 提供保留期與清除選項 |
| D8 | `compose_voice_samples`、`brain_fixes`、`triage_history`、`outbox_log` | 未列入清除清單 `[C]` | 明確列出每個資料集的清除語意 |
| D9 | `vault/persona.md`／`persona.json` | 清除快取會移除衍生人格，但若使用者手動編輯則可能保留 | 文件說明 |
| D10 | 備份副本 | 若使用者自行備份，刪除本機資料不會影響備份 | 文件明示「刪除不含你自行建立的備份」 |
| D11 | 瀏覽器列印／另存 PDF、EML 匯出 | 落在使用者下載目錄 | 文件明示為使用者責任 |
| D12 | 作業系統快取、暫存檔、shell history | 例如 CLI 驅動把 context pack 寫到暫存檔 | 檢查 CLI 驅動實作 `[C]` |
| D13 | 日誌檔 | 見 `LOGGING-REVIEW.md` | 搭配遮罩與保留期 |

> **建議在文件中明示**：「清除本機快取」是**本機快取隔離**操作，不是個資法第 11 條意義下的完整刪除，也不處理備份與使用者自行匯出的檔案。

## 4. 建議保留期（預設值供 BOB 決策）

目前沒有任何自動刪除，好處是不會誤刪，壞處是資料無限累積。建議採「**預設不自動刪除郵件快取，但對衍生資料設保留期**」的保守組合：

| 資料集 | 建議保留期 | 理由 | 是否自動刪除 |
|---|---|---|---|
| 郵件快取 `emails`（含 `search_docs`） | 跟隨來源；可設定上限（例如 180／365 天） | 使用者期待「本機信箱」長期可用，自動刪除風險高 | 不自動，提供設定與提醒 |
| `agent_turns`（摘要／Agent 結果快取） | 30 天 | 純衍生、可重算 | 是 |
| `triage_history` | 90 天 | 操作歷史，追溯用途有限 | 是（可設定） |
| `triage_tasks` | 完成後 90 天 | 任務追蹤 | 是 |
| `outbox_log` | 12 個月 | 需保留可追溯性 | 是 |
| `data/deliverables/` | 90 天 | 研究卡片多為一次性 | 是（可設定） |
| `data/slides/` | 30 天 | 一次性輸出 | 是 |
| `data/usage.jsonl` | 12 個月 | 用量統計 | 是 |
| `compose_voice_samples` | 使用中保留，可停用學習 | 屬側寫資料，需可關閉與清除 | 不自動，提供「關閉學習」 |
| `vault/persona.*` | 衍生，可重建 | 若使用者手動編輯則保留 | 不自動 |
| `brain_fixes` | 保留 | 使用者主動修正，刪除會讓推論退回錯誤 | 不自動 |
| `drafts` | 使用者控制 | 未寄出的內容屬使用者資產 | 不自動 |
| `cal_feeds`／本機事件 | 使用者控制 | 行事曆是主要功能資料 | 不自動 |
| 日誌（若新增） | 30 天 | 排錯與事故調查 | 是 |

> 保留期數值是**產品決策**，列在 `ACTION-PLAN.md` 的 BOB 決策清單（D4）。

## 5. 當事人權利請求處理程序（草案）

個資法第 3 條賦予當事人查詢閱覽、製給複本、補充更正、停止蒐集處理利用、刪除等權利；第 10 條要求在 15 日內答覆。openinbox 目前沒有對應功能，因此先以人工程序補位：

### 5.1 受理

1. 以書面或 Email 受理，記錄請求人類別、請求類型、識別方式。
2. 確認請求人與資料主體的關聯（避免洩漏他人資料）。

### 5.2 查詢與閱覽（第 3 條第 1 款、第 10 條）

1. 以 Email 位址在 `data/openinbox.db` 的 `emails`（`from_addr`、`to_addr`）與 `data/contacts.json` 檢索。
2. 以 `vault/persona.*`、`vault/cards/`、`data/deliverables/` 檢索是否含該對象。
3. 匯出結果時**只給與請求人相關的內容**，不得夾帶第三人資料（同一封信的其他人即為第三人）。

### 5.3 製給複本

以 Markdown 或 JSON 匯出，內容僅限該資料主體的資料；交付方式避免使用未加密的公開連結。

### 5.4 更正與補充（第 3 條第 2 款、第 11 條）

1. 郵件原文不應被修改（避免破壞證據性）；改以「標註更正」或由使用者於來源端更正。
2. 人格與推論類資料（`vault/persona.*`、`brain_fixes`）可依請求更正。

### 5.5 停止蒐集處理利用（第 3 條第 4 款）

1. 將該對象加入排除清單（目前無此機制，見 `ACTION-PLAN.md` P1-3）。
2. 暫時做法：使用者自行刪除相關郵件與 CRM 記錄，並避免再用 BYO agent 處理該對象。

### 5.6 刪除（第 3 條第 5 款、第 11 條）

依 `3. 刪除完整性缺口` 逐項處理，並在完成後留下**不含內容**的稽核紀錄（時間、請求編號、處理的資料集、筆數）。

### 5.7 答覆範本要素

- 受理編號與日期。
- 處理結果（提供／更正／停止／刪除）。
- 未處理的部分與原因（例如資料位於使用者自行備份中、或屬第 11 條但書「執行職務或業務所必須」）。
- 後續聯絡窗口。

## 6. 建議的工程實作（與 ACTION-PLAN 對應）

| 項目 | 內容 | 優先級 |
|---|---|---|
| R1 | `/api/cache/clear` 增加 `include` 參數，明確列出要清的資料集（預設維持現行行為） | P1 |
| R2 | 新增 `POST /api/privacy/erase`：以 Email 位址或 thread id 為範圍刪除，含 FTS、WAL checkpoint、稽核紀錄 | P1 |
| R3 | 新增 `GET /api/privacy/export`：以 Email 位址匯出該對象資料（Markdown／JSON） | P1 |
| R4 | `/api/cache` 顯示每個資料集的筆數與最舊／最新時間，讓使用者知道累積了什麼 | P1 |
| R5 | 保留期設定與到期清理（見第 4 節），預設只對衍生資料生效 | P2 |
| R6 | 可選 `VACUUM`／`secure_delete` 與 WAL checkpoint | P2 |
| R7 | 移除／停用「從草稿學習語氣」（`compose_voice_samples`）的開關與清除 | P1 |
| R8 | 文件明示「清除 ≠ 完整刪除」，並列出保留清單 | P0（文件） |

**測試要求**（不得連網、不得讀寫 repo 外路徑）：

- 一律使用 `tempfile`／`tmp_path` 建立拋棄式資料目錄。
- 假資料使用 `user@example.com`、`someone@example.test`、`FAKE_VALUE_FOR_TEST`。
- 斷言：刪除後 `emails`、`search_docs`、`search_fts` 均查不到；`data/deliverables/` 不含該 id；WAL 檔在 checkpoint 後不含舊資料字串。
- 斷言：稽核紀錄不含主旨、內文、寄件人全名。
