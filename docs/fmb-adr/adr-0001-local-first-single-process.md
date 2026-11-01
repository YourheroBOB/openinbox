# ADR-0001：本機優先——單行程、標準庫、零 pip、無託管模型

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`server/` 全部、`run.sh`、`install.sh`、所有功能外掛
- 相關：ADR-0002、ADR-0008、ADR-0012；ROADMAP 第 1、10 項

## 背景

openinbox 的定位是「真正屬於你的本機信箱腦」。郵件是高度敏感的個人資料，而當時市面上的
選項多半把資料與模型放在別人的伺服器上。團隊規模小、沒有維運團隊，同時希望系統：

- 開箱即可用，離線也能用；
- 任何人類都能讀完並審查核心程式碼；
- 不引入套件管理地獄（版本衝突、供應鏈風險、安裝失敗）。

## 決策

1. **一個 Python 3.9+ 單行程**跑 HTTP 服務、背景工作（outbox 到期檢查）與資料庫存取。
2. `server/` **只用標準函式庫**（`imaplib`、`sqlite3`、`http.server` 等），零 pip 依賴。
3. 資料落在本機：`data/openinbox.db`（SQLite）＋ `vault/` ＋ `data/` 檔案。
4. **不內建託管模型**，不設點數計量；模型由使用者自帶（BYO，見 ADR-0005）。
5. 無遙測、無廣告、無第三方分析。
6. 安裝只做最小的事：檢查 Python、建立目錄、缺少時複製範例設定（`install.sh` 不覆蓋既有檔）。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| 微服務／多程序分工 | 單機工具不需要，維運與除錯成本遠高於收益 |
| 引進 pip 依賴（框架、ORM） | 「零安裝」是產品承諾；相依衝突會破壞可攜性 |
| 純前端＋託管後端 | 違反本機優先；資料主權是核心賣點 |
| 內建推理模型 | 違反「不託管模型」；改為 BYO agent |

## 後果

**正面**

- 安裝路徑極短：`./install.sh && ./run.sh`，沒有環境地獄。
- 程式可完整審查；行為可預期；離線可用。
- 單一行程讓 MCP stdio 服務與 HTTP 面板可共享同一份本機資料與程式庫。

**負面／代價**

- 單行程＝單一故障域與資源上限；高併發寫入不是設計目標。
- SQLite 寫入鎖在大型資料集下會成為瓶頸（ROADMAP 第 8、9 項）。
- 外掛都在同行程載入，信任邊界必須靠文件與慣法維繫（ADR-0012）。
- 沒有內建備份／還原，直接複製使用中的 SQLite 可能不一致（ROADMAP 第 1 項）。
- 搜尋能力取決於 Python 的 SQLite 是否編進 FTS5（ADR-0008）。

## 證據

- `README.md`／`README.zh-Hant.md`：「One process, no hosted model, no credit meter」「Python 3.9+, zero pip packages」。
- `docs/fmb/ARCHITECTURE.md` 核心原則第 1、2 條與「明確不包含」。
- `CONTRIBUTING.md`：「Python 3.9 stdlib only in `server/`」。
- `run.sh`：單一 `exec python3 server/app.py`。
