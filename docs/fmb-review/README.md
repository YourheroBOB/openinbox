# openinbox 程式碼審查報告（FMB review）

## 範圍與方法

- 本報告只新增文件，不修改任何產品碼、測試、CI、secrets 或 git 設定。
- 審查依據為任務提供的 repo 快照內容；因無法即時讀取全部 187 檔，`行號` 以快照中的符号／區塊為錨點標示「約」，實際修補前請用 `grep -n` 或 IDE 再次確認。
- 已覆蓋的重點路徑：`server/features/agents.py`、`ui/modules/agents.js`，並對照 `docs/fmb/ARCHITECTURE.md`、`docs/fmb/ROADMAP.md`、README、CONTRIBUTING 的契約。
- 未逐檔複製任何郵件內文、案件當事人、LINE 訊息、token、金鑰或密碼；示例值一律使用明顯假值。

## 嚴重度定義

| 嚴重度 | 意義 |
|---|---|
| 高 | 可能造成資料損毀、不一致、安全邊界削弱或主要流程錯誤 |
| 中 | 特定輸入或併發下會錯誤、難以診斷或降低可測試性 |
| 低 | 可讀性、無障礙、相依風險或維護性問題 |
| 建議 | 非缺陷，但值得排入待辦清單 |

## 檔案索引

- `docs/fmb-review/README.md`：本文件，範圍、方法、嚴重度定義。
- `docs/fmb-review/issues.md`：逐項問題，含檔案錨點、嚴重度、說明、建議修法程式片段。
- `docs/fmb-review/top10-recommendations.md`：前十大修補建議與工作量估計。

## 本次審查的正面發現

- `server/features/agents.py` 對成果 ID 有嚴格格式驗證，HTML 採全轉義，UI 以 sandbox iframe 預覽，符合「不執行外部內容」原則。
- `parse_mention` 為純函式，有利於測試；context pack 已明確要求把郵件內容視為資料，不要跟隨其中指示。
- 文件 `docs/fmb/ROADMAP.md` 已把備份、衍生資料一致性、MCP 擴充等列為高價值缺口，與本審查方向一致。

## 限制

- 未執行完整測試；本任务只新增 Markdown。
- 未能取得 `server/app.py`、`server/agent_bridge.py`、`server/yhbmail.py`、`server/features/search.py` 等內容，涉及這些模體的推測已標為「待確認」。
