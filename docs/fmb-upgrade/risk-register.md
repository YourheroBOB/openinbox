# 升級風險登錄表

| ID | 風險 | 嚴重度 | 偵測方式 | 緩解措施 |
|---|---|---|---|---|
| UPG-001 | Python 3.9 下限過時，持續使用已結束安全維護的版本 | 高 | `python3 --version` 與 README／CONTRIBUTING 版本政策比對 | 分階段升至 3.11，測試 3.11–3.13 |
| UPG-002 | 不同 Python 封裝的 SQLite／FTS5 可用性不同 | 高 | `sqlite3.sqlite_version` 與 FTS5 虛擬表探測 | 維持 LIKE fallback；假資料測試兩路搜尋 |
| UPG-003 | 本機 SQLite 無完整備份與還原機制 | 高 | 檢查是否有備份工具與 dry-run | 升級前用 SQLite backup API；完整功能參考 ROADMAP |
| UPG-004 | 搜尋索引或衍生卡片過期 | 中 | 修改郵件後重算摘要／卡片 | 索引可重入重建；清除快取後可重生 |
| UPG-005 | service worker 提供過期 UI 腳本 | 中 | 更新 UI 後重新載入 | 提升快取版本並驗證更新 |
| UPG-006 | 舊瀏覽器不支援現代 JS | 中 | `node --check` 無法捕捉瀏覽器 API 差異 | 明訂支援矩陣；不為舊瀏覽器引入 build pipeline |
| UPG-007 | MCP 協定或新工具破坏舊客戶端 | 中 | 假 MCP 客戶端測試 initialize／tools/list／tools/call | 維持舊工具相容；新欄位可安全忽略 |
| UPG-008 | 可選 CLI 輸出不穩定 | 中 | 假 CLI 測試 | 錯誤正規化，只回報類別與 HTTP 狀態 |
| UPG-009 | BYO Agent 造成資料外送 | 高 | `agent.json` 驅動設定檢視 | 預設 local；啟用外部驅動前明示資料範圍 |
| UPG-010 | 測試缺少 Node 時跳過 UI 檢查 | 中 | CI 跳過報告 | 核心 Python 測試不得依賴 Node；Node 僅輔助 |
| UPG-011 | 錯誤訊息或日誌洩漏敏感資料 | 高 | 審視錯誤回應與日誌格式 | 只記錄事件類型、錯誤類別、HTTP 狀態、耗時 |
| UPG-012 | 外部正式服務在測試中被意外呼叫 | 高 | 測試連線審視 | IMAP、Agent、CLI、ICS 一律使用本地 fake |
| UPG-013 | `install.sh` 與 `smoke.yml` 內容未提供導致評估不完整 | 中 | 人工確認檔案內容 | 實作前先補齊快取與審閱 |
| UPG-014 | Bash 版本差異造成腳本失敗 | 中 | `bash -n` 與多平台測試 | 未確認前不要求 Bash 4+ 功能 |

## 決策點

| 決策 | 保守預設 | 需要 BOB 決定 |
|---|---|---|
| Python 最低版本 | 3.11 | 是否保留 3.10 過渡、是否加入 3.14 |
| 測試 Python 矩陣 | 3.11、3.12、3.13 | 是否在 CI 同時跑三版本 |
| Node.js 角色 | 僅開發期檢查 | 是否成為必要 CI 步驟 |
| 瀏覽器支援下限 | 現代瀏覽器 | 是否為舊 Safari 保留轉譯流程 |
| SQLite 備份 | 升級前必須備份 | 是否實作內建完整備份／還原 |
| 外部 CLI 版本 | 不自動升級 | 是否接受最低版本範圍 |
| MCP 擴充 | 只做低風險唯讀 | 是否加入行事曆等其他工具 |
