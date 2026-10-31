# 合規待辦與決策清單

本文件把 `PDPL-GAP-ANALYSIS.md` 的缺口轉成可執行項目。**本輪只新增文件，未修改任何程式或既有檔案**；下列工程項目需另開工作分支執行。

## 1. 執行原則

1. 任何改動都不得新增預設寄信路徑、不得新增遙測、不得新增必要 pip 套件。
2. 測試一律使用 `tempfile`／`tmp_path` 與虛構資料；假憑證只用 `FAKE_VALUE_FOR_TEST` 這類明顯假字串。
3. 測試不得連線到正式服務，不得讀寫 repo 以外的路徑。
4. 不得修改 `.github/workflows`、secrets／憑證設定、git remote。
5. 文件與程式不一致時，以程式實際行為為準並修正文件。

## 2. P0：文件與最低限度治理（不需改程式）

| # | 項目 | 產出 | 驗收條件 | 對應缺口 |
|---|---|---|---|---|
| P0-1 | 採用告知草案 | 由 BOB 審閱 `PRIVACY-NOTICE-DRAFT.md`，決定放置位置（README、首次啟動頁、或兩者） | 使用者能在不讀原始碼的情況下知道蒐集目的、資料類別、外送風險、權利行使方式 | G1 |
| P0-2 | 明示第 51 條適用前提 | 告知文件寫明「僅限自然人為個人或家庭活動使用；對外提供或商業使用不適用」 | 文字存在且與 BYO agent 章節互相連結 | G1 |
| P0-3 | 明示「清除 ≠ 完整刪除」 | 在 README 的清除說明與本目錄 `RETENTION-DELETION.md` 對齊 | 使用者能知道草稿、行事曆、deliverables、備份不會被清 | G4 |
| P0-4 | 角色定義 | 文件寫明使用者＝蒐集者、BYO agent／MCP 客戶端＝受託處理者或獨立蒐集者 | 有明確段落與決策紀錄 | G1、G7 |
| P0-5 | 安全維護計畫草案 | 可放 `docs/fmb-compliance/SECURITY-PROGRAM.md`（下一輪新增） | 含權限、日誌、備份、事故、訓練五節 | G6 |

> P0 全部是文字工作，但 P0-1 與 P0-3 需要 BOB 決定是否修改既有 README；本輪依規則不修改既有檔案。

## 3. P1：程式與機制（需另開分支）

| # | 項目 | 建議實作 | 驗收條件 | 對應缺口 |
|---|---|---|---|---|
| P1-1 | 日誌遮罩與請求記錄 | 覆寫 `log_message`；新增 `server/logsafe.py`；`error_label()` 模式推廣 | stderr 不含 `FAKE_SUBJECT_FOR_TEST`、`alice@example.test`；錯誤只含類型與狀態碼 | G9 |
| P1-2 | 刪除語意明確化 | `/api/cache/clear` 加 `include` 參數；回應列出每個資料集刪除筆數 | 回應不含內容；測試覆蓋每個資料集 | G4 |
| P1-3 | 依資料主體刪除與匯出 | `POST /api/privacy/erase`、`GET /api/privacy/export`（以 Email 或 thread id 為範圍） | 刪除後 `emails`、`search_docs`、`search_fts`、`deliverables` 均查不到；匯出只含該主體資料 | G2、G4 |
| P1-4 | 外送可見性與同意 | `agent.json` 非 loopback 需 `allow_remote: true`；首次外送顯示告知；記錄外送事件（host、大小、時間） | 未設定時拒絕外送並回明確訊息；事件日誌不含內容 | G5 |
| P1-5 | 敏感內容提示 | 對特種個資與高風險識別碼做提示（不自動刪除） | UI 顯示提示；不建立任何分析欄位 | G8 |
| P1-6 | 停止處理清單 | 以 Email 建立排除清單，摘要／研究／CRM 明確跳過 | 測試：列入清單者不出現在 context pack | G2 |
| P1-7 | 關閉與清除側寫 | 提供 `compose_voice_samples` 與 `vault/persona.*` 的停用與清除 | 停用後不再寫入；清除後檔案不存在 | G3、G10 |
| P1-8 | 事故應變文件化 | `docs/fmb-compliance/INCIDENT-RUNBOOK.md`（下一輪） | 含發現、隔離、評估、通知、改善五步與通知範本 | G13 |
| P1-9 | 檔案權限 | `install.sh` 加 `umask 077`；執行期檢查 `data/`、`vault/` 權限並警告 | 測試以 `tmp_path` 驗證建立後權限 | G6 |
| P1-10 | 明文金鑰拒絕 | `agent.json` 若含明文 `api_key` 直接拒絕（比照 `accounts.json` 的 `password`） | 測試：明文時回錯誤且不載入 | G5、G6 |
| P1-11 | 刪除完整性 | WAL checkpoint、可選 `VACUUM`、FTS 覆蓋所有刪除路徑 | 測試：刪除後以字串搜尋 WAL 與 DB 找不到 | G4 |

## 4. P2：治理與品質

| # | 項目 | 內容 | 對應缺口 |
|---|---|---|---|
| P2-1 | SBOM 與授權檢查 | 產生最小 SBOM；CI 檢查 allowlist（MIT／BSD／ISC／PSF／Public Domain／Apache-2.0） | L1、L2 |
| P2-2 | 第三方聲明檔 | `THIRD-PARTY-NOTICES` 草案，現階段聲明「未內含第三方程式碼」 | L1 |
| P2-3 | 保留期自動清理 | 僅對衍生資料（agent_turns、triage_history、deliverables、slides、usage） | G3 |
| P2-4 | 備份與還原 | 對應 `docs/fmb/ROADMAP.md` 第 1 項；備份 manifest 不含內容明文 | G6 |
| P2-5 | 加密選項 | DB 或備份層加密（決策見 D5） | G6 |
| P2-6 | 貢獻者合規教育 | `CONTRIBUTING` 增列「不得貼入真實郵件／帳號／憑證」與「新增外送路徑需更新本目錄」 | G15 |
| P2-7 | 商標與名稱一致性 | 統一主名稱並保留與廠商無關的免責 | L4、G16 |
| P2-8 | DCO／CLA | 決定是否採用 | L6 |
| P2-9 | 瀏覽器端儲存稽核 | 確認 UI 未把郵件寫入 `localStorage`／`IndexedDB` 並加測試 | G6 |

## 5. 禁止事項（本專案合規紅線）

1. 不新增未經人工確認的寄信路徑；Agent 不得代替使用者發言。
2. 不新增遙測、廣告 SDK、第三方分析。
3. 不把真實郵件、真實帳號、案件資料寫進 repo、測試、fixtures 或 `state/*.md`。
4. 不在日誌、錯誤訊息、API 回應中輸出完整 Email、姓名、主旨、內文、附件檔名、憑證。
5. 不以「自動刪除」處理特種個資或使用者可能需要的證據；改以提示與使用者決定。
6. 不把 Python 外掛描述成沙箱；它與主程序同權限。
7. 不把 `0.0.0.0` 或反向代理部署視為支援情境。

## 6. BOB 決策清單

| # | 決策 | 保守預設（若 BOB 未回覆） | 影響 |
|---|---|---|---|
| D1 | 使用定位：純自用（第 51 條）／對外提供／商業使用 | 以「純自用」撰寫告知，但保留對外使用的章節骨架 | 決定哪些義務必須履行 |
| D2 | 是否建立正式隱私告知並在 UI 顯示 | 先提供文件草案，不強制 UI | G1 |
| D3 | BYO agent 外送是否需每次同意或一次性同意 | 一次性同意 + 可在設定中撤回 + 非 loopback 需 `allow_remote` | G5 |
| D4 | 保留期數值（見 `RETENTION-DELETION.md` 第 4 節） | 採用建議值，且只對衍生資料自動清理 | G3 |
| D5 | 是否加密 DB／備份 | 先要求檔案權限與磁碟加密，不引入應用層加密 | G6 |
| D6 | 是否提供 per-subject 刪除／匯出 API | 提供，且限本機呼叫 | G2、G4 |
| D7 | 是否接受 GPL／AGPL 相依 | 不接受 | 授權 |
| D8 | `gog`／`gsk` 是否列為正式支援組合 | 列為「使用者自備、未經授權確認」 | L3、G11 |
| D9 | 是否採用 DCO／CLA | 先在 `CONTRIBUTING` 加一行聲明 | L6 |
| D10 | 專案主名稱 | 沿用 TooPowerInbox（README 主名） | L4 |

## 7. 未完成事項（本輪）

- 未能讀取 `server/app.py`、`server/yhbmail.py`、`server/agent_bridge.py` 等核心檔案，因此資料表欄位、日誌行為、清除語意有 `[C]` 項需以程式碼核對。
- 未驗證 `.github/workflows/smoke.yml` 內容（本輪禁止修改，亦未取得內容）。
- 未確認 UI 瀏覽器端儲存行為。
- 未確認 `gog`、`gsk`、模型授權條款。
- 未建立 SBOM、第三方聲明檔、安全維護計畫、事故應變手冊（列為後續）。
- 未執行任何測試或程式改動（本輪僅新增文件）。
