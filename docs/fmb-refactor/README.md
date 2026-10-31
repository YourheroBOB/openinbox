# Openinbox 重構計畫（fmb-refactor）

本目錄只放「重構計畫」文件，不含程式變更。實際程式修改會依本計畫分成獨立批次，每批一個可獨立驗證的小改動。

## 文件索引

| 檔案 | 內容 |
|---|---|
| `README.md` | 範圍、原則、批次索引、如何使用本計畫 |
| `FINDINGS.md` | 重複程式、過長函式、耦合過緊、命名不一致的調查結果（含證據與信心等級） |
| `PLAN.md` | 目標結構、分批總表、每批步驟與驗收條件 |
| `BEFORE_AFTER.md` | 關鍵片段的重構前後對照 |
| `TESTS_RISKS.md` | 每批需先補的測試、風險、回滾與決策點 |

## 範圍

**涵蓋**

- `server/features/agents.py` 與 `ui/modules/agents.js`：本輪唯一完整閱讀過的實作，作為第一波重構對象。
- 跨功能重複出現的模式：Agent 驅動派送與 fallback、語言代碼轉換、雙語文案、UI 小工具函式、雙語文件成對維護。
- 命名與目錄結構的不一致。

**明確不涵蓋**

- 任何功能新增、行為變更、API 破壞性變更。
- `.github/workflows`、secrets／憑證設定、git remote、分支策略。
- 寄信能力、遠端郵件寫入（IMAP STORE／EXPUNGE）、託管模型、pip 相依。
- 資料庫 schema 變更（本計畫不涉及 migration）。
- 未在 `docs/fmb/ARCHITECTURE.md` 與 repo 檔案清單中確認的模組，一律先標「待確認」，不憑猜測改動。

## 原則

1. **行為凍結**：每一批的公開行為（HTTP 回應鍵集合、狀態碼、檔案格式、UI 可見文字）必須不變；若必須變，先寫契約測試並在該批說明差異。
2. **先補測試再動刀**：每一批都先補 characterization 測試（描述現況，不描述理想），確認改動前後一致。
3. **每批可獨立合併**：批次之間不共用同一個 commit；任一批回滾都不應要求其他批一起回滾。
4. **不動安全邊界**：維持「不預設寄信」、唯讀 IMAP、local origin 檢查、成果 HTML 全轉義與 sandbox 預覽。
5. **不引入新相依**：只使用 Python 標準函式庫；Node 只用於 `node --check` 語法檢查，缺席時跳過。
6. **測試資料一律虛構**：只用 `fixtures/` 既有虛構資料與 `tempfile`／`tmp_path`；需要假憑證時使用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串，不使用任何真實格式前綴。
7. **不讀寫 repo 外路徑**：測試與工具只操作 repo 內與暫存目錄。

## 如何進行

1. 先跑基線：`python3 -m unittest discover -s tests` 與 `scripts/smoke.sh`，把結果記在該批 PR 描述。
2. 依 `PLAN.md` 的批次順序做；B0（守門測試）必須先完成。
3. 每批結束都重跑基線指令，並在 PR 描述貼上「改前／改後」的函式長度統計（見 `PLAN.md` 的量測指令）。
4. 需要 BOB 決策的項目集中在 `TESTS_RISKS.md` 最後一節；未決前採該節列出的保守預設。

## 已知限制

- 本計畫只完整閱讀 `server/features/agents.py` 與 `ui/modules/agents.js`。其他模組的「疑似重複」是依 `docs/fmb/ARCHITECTURE.md` 與 repo 佈局推得，標為「待確認」，必須在 B0 以清點結果校正後才進入實作。
- 未執行任何程式，因此所有「行數」為估計值；B0 會用 AST 統計取得實際數字並回填。
