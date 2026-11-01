# ADR-0008：單一 SQLite ＋ 本機檔案；FTS5 優先、LIKE 後備；快取清除語意

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`server/yhbmail.py`、`search.py`、`cache.py`、`vault/`、`data/`
- 相關：ADR-0001、ADR-0013；ROADMAP 第 1、2、9 項

## 背景

零 pip 前提（ADR-0001）下需要可靠的儲存與搜尋。個人等級資料量不需要資料庫伺服器，
但需要交易、索引與關聯查詢。同時衍生資料（人格、卡片、索引、用量）生命週期不同於原始
郵件，清除語意必須明確，否則使用者會失去親手寫的卡片。

## 決策

1. **一個 SQLite 檔** `data/openinbox.db` 承載主要表格：`emails`、`drafts`、`mail_state`、
   `search_docs`／`search_fts`、行事曆與 feed、`brain_fixes`、compose 設定與聲音樣本、
   triage 任務與歷史、outbox 相關表、`agent_turns`。
2. 衍生與設定放**本機檔案**：`vault/persona.*`、`vault/index.json`、`vault/cards/*.md`、
   `data/usage.jsonl`、`data/contacts.json`、`data/skills.json`、`data/slides/`、`data/deliverables/`。
3. 搜尋兩層策略：優先用 **FTS5**（英文 `unicode61`、中文重疊 bigram）；SQLite 沒有 FTS5
   時整體退回 `LIKE`——結果正確但大型資料集較慢。
4. **快取清除語意**（`POST /api/cache/clear`）：移除郵件快取、示範／快取行事曆、Agent 回合、
   衍生卡片與衍生人格索引；**保留**草稿、使用者手寫卡片、本機建立或匯入的行事曆
   （含 `cal_feeds`）與邀請草稿；`{"reseed": true}` 重建示範資料。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| 每個功能一個 DB／JSON 檔 | 交易、關聯與備份面變複雜 |
| 純檔案資料庫（無 SQLite） | 查詢、索引、交易都要自己造 |
| 引進 ORM／ migration 工具 | 違反零 pip |
| 清快取＝全部刪掉 | 會摧毀使用者資產（草稿、手寫卡、行事曆） |

## 後果

**正面**

- 搬遷＝打包 `data/`＋`vault/`；測試可用暫存根目錄完整重建。
- 搜尋能力自動降級，不會因為環境沒有 FTS5 而不可用。

**負面／代價**

- 使用中直接複製 SQLite 可能不一致，內建備份是已知缺口（ROADMAP 第 1 項）。
- 大型資料集的寫入鎖與列表效能需要批次與虛擬列表等工程手段（ROADMAP 第 8、9 項）。
- 衍生資料的失效需要來源簽章策略，否則舊摘要會被當現況（ROADMAP 第 2 項）。

## 證據

- `docs/fmb/ARCHITECTURE.md` 第 4 節（資料表與檔案表）、第 5.4、5.9 節。
- `README.md`「清除本機快取」段（保留草稿、手寫卡、行事曆 feed）。
- `.gitignore`：`data/`、`vault/persona.*`、`vault/index.json`、`vault/cards/*.md` 等排除規則。
