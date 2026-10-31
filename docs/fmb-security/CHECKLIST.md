# openinbox 資安與可靠性稽核清單（CHECKLIST）

搭配 [AUDIT.md](AUDIT.md) 使用。狀態說明：
- ✅ 通過：現有實作已妥善處理（有測試或明確程式碼佐證）
- ⚠️ 部分：有防護但有殘餘風險（見 AUDIT 對應編號）
- ❓ 待確認：本輪未取得該檔內容，需後續覆核
- ❌ 不通過：需修補

## 1. 輸入驗證

| 項目 | 狀態 | 備註 |
|---|---|---|
| 所有 POST body 欄位有型別轉換與長度上限 | ✅ | agents.py：target 120／ask 1000／text 4000 |
| 列舉型欄位白名單（kind、fmt、action 等） | ✅ | `TASK_KINDS`、`fmt in ("md","html","json")` |
| 數字參數夾界（limit 等） | ✅ | `max(1, min(int(...), 200))`，ValueError 有處理 |
| 查詢參數進 SQL 前參數化 | ❓ | A-07：yhbmail.py 待逐行確認 |
| email_id／id 類輸入進入資料層前驗證 | ⚠️ | deliverable ID 有 `ID_RE`；`email_id` 直接交 `yhbmail.get_email`，待確認 A-07 |

## 2. 命令注入

| 項目 | 狀態 | 備註 |
|---|---|---|
| subprocess 一律 argv list、`shell=False` | ❓ | A-06：設計正確（agent.json 為 argv 清單），agent_bridge 實作待確認＋補測試 |
| 使用者／信件內容不進入 argv（只走 stdin） | ❓ | A-06 |
| CLI／HTTP 錯誤不回顯 prompt／stderr 給客戶端 | ✅ | `error_label()` 只回類型＋HTTP 碼 |

## 3. 路徑穿越

| 項目 | 狀態 | 備註 |
|---|---|---|
| deliverable ID 白名單 regex 後才組路徑 | ✅ | `ID_RE`，`..`／`/` 無法通過 |
| vault 卡片 slug 過濾路徑字元 | ✅ | `_slug` 將非英數壓成 `-` |
| `/ui/modules/*`、靜態檔路由防穿越 | ✅ | foundation 驗收測試 404 |
| fmt 副檔名白名單（`partition(".")` 後仍驗證） | ✅ | `json.md` 之類會被拒 |

## 4. 機密外洩

| 項目 | 狀態 | 備註 |
|---|---|---|
| 密碼／token 不落檔（accounts.json 拒明文 password） | ✅ | providers／mailops 均有驗證 |
| API 回應不含憑證值（只回環境變數名） | ✅ | `/api/providers` |
| .gitignore 涵蓋 accounts.json／agent.json／data／.env／vault 個人檔 | ✅ | |
| 錯誤回應不含 stack trace／endpoint body | ⚠️ | agents.py 已做好；全域 handler 待確認（A-04） |
| BYO agent URL 明文外傳有警示 | ❌ | A-05：建議加 `_url_warning` |
| 信件內容進 LLM pack 有不可信邊界標記 | ⚠️ | A-02：建議加 fence＋規則 |
| repo 內無真實信箱／個資（fixtures 全虛構） | ✅ | 僅 example.com／.example 網域 |

## 5. 相依套件

| 項目 | 狀態 | 備註 |
|---|---|---|
| 零第三方 pip 相依（供應鏈風險最小化） | ✅ | stdlib only，CONTRIBUTING 有規範 |
| 無 telemetry／hosted model 呼叫 | ✅ | local driver 零網路 |

## 6. 錯誤處理

| 項目 | 狀態 | 備註 |
|---|---|---|
| agent 失敗退回本機啟發式並標示 fallback | ✅ | 可靠性 fail-open、透明 |
| JSON／OSError 解析失敗不炸整個端點 | ⚠️ | `list_deliverables` 有處理；`read_deliverable` 缺（A-04）；`second_brain.load` 缺（A-03） |
| 未捕捉例外回 500 時不洩漏 traceback 給客戶端 | ❓ | app.py 待確認 |

## 7. 併發

| 項目 | 狀態 | 備註 |
|---|---|---|
| SQLite 併發寫入策略（WAL／busy_timeout／重試） | ❓ | A-11 |
| 多檔寫入（deliverable md+html+json）一致性 | ⚠️ | A-03：建議 atomic write |
| index／persona 單寫入者或互斥 | ⚠️ | A-03 |
| ID 生成避免碰撞 | ✅ | `_stamp()` 含微秒 |

## 8. Fail-open / Fail-closed

| 項目 | 狀態 | 備註 |
|---|---|---|
| 安全檢查失敗一律拒絕（Origin 403、關閉的技能拒跑、明文密碼拒收） | ✅ | |
| 可靠性降級（agent→local）明確標示 | ✅ | |
| 未確認的 outbox 草稿不得寄出 | ✅ | tpi-outbox 測試 |

## 9. Web / 瀏覽器面

| 項目 | 狀態 | 備註 |
|---|---|---|
| CSRF：寫入端點檢查本機 Origin | ⚠️ | 已有，但 Host 未驗證（A-01 DNS rebinding） |
| XSS：deliverable HTML 全 escape、iframe sandbox、UI `h()` | ✅ | |
| SW 只快取靜態檔、不碰 /api/* | ✅ | mobile 驗收測試 |
| ICS 匯入 SSRF 防護（私有位址、redirect、大小上限） | ✅ | calendar 驗收測試 |
| 列印頁／PWA 圖示無外部資源 | ✅ | |

## 10. 其他

| 項目 | 狀態 | 備註 |
|---|---|---|
| HTTP 無認證（loopback 設計假設）文件化 | ⚠️ | A-09：可選 `OPENINBOX_TOKEN` |
| data／vault 目錄權限 700 | ❌ | A-10：install.sh 建議 chmod |
| MCP stdio：解析錯誤回 -32700／-32600 等標準碼 | ✅ | tpi-mcp 測試 |
| 測試不觸網、不讀寫 repo 外路徑 | ✅ | 拋棄式資料夾＋假 IMAP 伺服器 |

## 建議修補優先序

1. **A-01**（Host 驗證）— 小改動、擋掉整類 rebinding 風險
2. **A-02**（pack 不可信邊界）— 中改動、降低提示注入
3. **A-03／A-04**（原子寫入＋OSError）— 可靠性
4. **A-06／A-07／A-11**（待確認項逐檔覆核並補測試）
5. **A-05／A-08／A-09／A-10**（防呆與文件化）
