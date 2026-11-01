# ADR-0013：示範模式為預設，live 模式是選配

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`accounts.json`、`fixtures/`、`install.sh`、`cache.py`、所有 UI
- 相關：ADR-0004、ADR-0006、ADR-0008

## 背景

產品承諾是「`./install.sh && ./run.sh` 就能看到東西」。若預設需要填帳號、設密碼、裝 CLI，
第一次體驗就會卡住，也沒有安全的地方練習操作。同時 repo 裡不能出現任何真實信箱資料。

## 決策

1. `accounts.json` 預設 `mode: "demo"`；`accounts.example.json` 即為此設定。
2. 第一次開機由 yhbmail 載入 `fixtures/` 的**虛構**示範信件、行事曆與規則。
3. 要接真信箱必須明確改成 `mode: "live"` 並設定 driver、帳號與環境變數（ADR-0006）。
4. `install.sh` 只在缺少時複製範例設定，**不覆蓋**既有檔。
5. 示範資料一律虛構：repo 內禁止真實信箱、真實郵件內容（CONTRIBUTING 明文）。
6. `POST /api/cache/clear` 可用 `{"reseed": true}` 重建示範資料，便於測試與重現。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| 預設 live 模式 | 新手第一步就卡在帳號與密碼 |
| 首次執行精靈 | 需要表單、驗證與狀態管理，與「小」的定位衝突 |
| 不放示範資料 | 無法開箱展示，也難以撰寫可重現測試 |

## 後果

**正面**

- 零設定可跑；UI、技能、Agent 協作都能立刻試。
- 測試可用同一批 fixtures，行為可重現、無外部相依。

**負面／代價**

- 使用者可能誤以為已連接真信箱；UI 需把帳號與同步狀態講清楚（ROADMAP 第 3 項）。
- fixtures 需持續維護，且必須保持虛構。

## 證據

- `accounts.example.json`：`"mode": "demo"`。
- `README.md`：「Demo mode is the default.」與「Demo mail loads on the first boot.」
- `CONTRIBUTING.md`：「Keep demo fixtures fictional. No real inboxes in the repo.」
- `fixtures/` 目錄內容（`demo_inbox.json`、`demo_sent.json`、`ics/*.ics`、`rules_demo.json`）。
