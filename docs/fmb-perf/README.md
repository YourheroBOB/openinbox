# Openinbox 效能與可靠性審查（docs/fmb-perf）

本目錄是一次「效能與可靠性審查」的產物，只新增 Markdown 文件，**不修改任何程式碼**。
目的：把 openinbox 這套單機、單行程、零 pip 的「信箱腦」在效能瓶頸、資源洩漏、
併發／競態、逾時與重試、錯誤恢復、日誌可觀測性六個面向的問題，整理成每項都可執行、
可驗證、有優先級的改善清單。

## 文件

| 檔案 | 內容 |
|---|---|
| `README.md` | 本檔：範圍、證據基礎、判讀方式、優先級定義、安全與測試規範 |
| `findings.md` | 全部待改善項，依六個面向分組；每項含位置、影響、建議修法、驗證方式、優先級、證據 |
| `action-plan.md` | 依優先級與依賴排序的行動計畫、里程碑退出條件、要補的回歸測試 |

## 範圍與證據基礎

本審查以「目前 repo 的內容」為準。審查時可讀到的檔案包括：
`docs/fmb/ARCHITECTURE.md`、`docs/fmb/ROADMAP.md`、兩份 `README`、`adapters/README*`、
`server/features/agents.py`、`ui/modules/agents.js`、`run.sh`、`install.sh`、
`accounts.example.json`、`agent.example.json`、`.gitignore`、`skills/*` 等。

限制（重要，請在實作前確認）：

- 對於**未提供原始碼**的模組（例如 `server/app.py`、`server/yhbmail.py`、
  `server/agent_bridge.py`、`server/features/imap.py`、`search.py`、`outbox.py`、
  `usage.py`、`cache.py`、`plugins.py`、`server/persona.py`、`server/second_brain.py`），
  findings 的位置以**模組／函式層級**描述，並在「證據」欄標註推論來源；
  這類項目會標上「需程式碼確認」，實作第一件事是先用測試重現，再修。
- 對於**可讀到原始碼**的模組（`server/features/agents.py`、`ui/modules/agents.js`），
  finding 直接引用其中的行為（例如 `list_deliverables` 每次全檔讀取、`save_deliverable`
  非原子寫入）。
- 本文件不宣稱已量測到實測數字；凡涉及效能的項，`驗證方式` 都給出可在
  `tmp_path`／暫存根目錄重跑的量測或斷言方法。

## 優先級定義

| 等級 | 意義 |
|---|---|
| P0 | 可能造成資料遺失、損毀、服務無法啟動或持續卡死；或高風險競態，需先確認再修 |
| P1 | 顯著影響可用性、可靠性或大型資料集效能；應排進下一個里程碑 |
| P2 | 影響效率、可觀測性、維運成本或恢復能力；排在其後 |
| P3 | 品質與長期維護性改善 |

## 判讀方式

- 每項都有穩定 ID（`PERF-*`、`LEAK-*`、`RACE-*`、`TIME-*`、`RECV-*`、`OBS-*`），
  可在 commit、issue、測試名稱中沿用。
- 「建議修法」是保守、可回退的最小改動，不引入 pip 依賴、不新增預設寄送路徑、
  不把外掛描述成沙箱。
- 修完一項，請把對應 `驗證方式` 落成 `tests/` 下的 unittest，再關閉該項。

## 安全與測試規範（所有項目共同遵守）

1. 測試一律用 `tempfile`／`tmp_path` 與虛構資料，不讀寫 repo 以外的路徑。
2. 測試需要憑證、金鑰、密碼、端點時，只用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串；
   不使用 `sk-`、`ghp_、`xox` 等任何真實格式前綴。
3. 測試不得連線到網路上的正式服務；外部相依（IMAP、Agent、CLI、ICS）一律以本地
   fake 取代。
4. 任何新日誌、錯誤回應、metrics 都**不得**包含：郵件內文、主旨、寄件人、案件或
   當事人資料、提示詞、模型回答、金鑰或環境變數值；只記錄事件類型、錯誤類別、
   HTTP 狀態、耗時與計數。
5. 不修改 `.github/workflows`、secrets／憑證設定、git remote；不做 git push／merge。

## 與路線圖的關係

本審查與 `docs/fmb/ROADMAP.md` 互補：ROADMAP 以「價值排序」盤點大型工作包
（備份、一致性、診斷、MCP、多 mailbox、規則、行事曆、批次、無障礙／效能、外掛治理）；
本目錄聚焦同一系統的**效能、可靠性與可觀觀測性**，並把 ROADMAP 中與
SQLite 競態、大型資料集、失敗診斷相關的条目拆成可逐項修掉的 finding。
`action-plan.md` 盡量對齊 ROADMAP 的里程碑精神（先正確性與安全，再規模化能力）。
