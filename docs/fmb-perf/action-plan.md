# 行動計畫（action-plan）

依「先確認再修、先正確性與安全、再規模化」排序。每個里程碑都可有獨立驗收，
不引入 pip 依賴、不新增預設寄送路徑、不把外掛描述成沙箱。所有新測試遵守
`README.md` 的安全與測試規範。

## 里程碑 0：可靠性地基（P0 確認 + 高頻 P1）

目標：先排除會卡死服務、洩漏資源或讓錯誤外洩的路徑，並建立可觀測性最小集。

| 順序 | 項目 | 動作要點 |
|---:|---|---|
| 1 | RACE-04、RACE-01 | 以暫存 DB 重現跨執行緒共用連線與 `database is locked`；確認後改執行緒本地連線／鎖 + WAL + `busy_timeout` |
| 2 | TIME-01、TIME-02 | 為 openai_compatible 補逾時；為 IMAP 補 socket 逾時；逾時一律 fallback 並標示 |
| 3 | LEAK-01、LEAK-02 | CLI 子程序 `kill()`+`wait()` 或 `subprocess.run(timeout=)`；HTTP 回應以 `with` 關閉 |
| 4 | LEAK-03 | IMAP `try/finally` 登出；單帳號失敗不影響他人 |
| 5 | RECV-01 | 逐帳號同步隔離與狀態記錄；UI 與 API 一致 |
| 6 | OBS-01、OBS-03 | 統一 logger（無 PII）；全站錯誤正規化（只回類別 + HTTP 狀態） |

退出條件：
- 併發寫入測試無 `locked`、無 race；重現案例可跑。
- 假 hang 端點、假不掉話 IMAP、假逾時 CLI 都能在時限內 fallback，無殘留程序／socket。
- 壞帳號不阻礙好帳號；上游回傳敏感字串時 API 不回傳。
- 新增日誌通過「無內文／無金鑰」掃描測試。

建議新增測試（`tests/`，暫存根目錄 + 假資料）：
- `test_fmb_perf_sqlite_concurrency.py`：多執行緒寫入、WAL、busy_timeout。
- `test_fmb_perf_agent_timeout.py`：hang 端點、逾時 CLI、HTTP worker 關閉。
- `test_fmb_perf_imap_timeout_logout.py`：假 IMAP 逾時與 finally 登出。
- `test_fmb_perf_error_label.py`：假上游含敏感字串，斷言不外洩。

## 里程碑 1：效能與可觀測性（其餘 P1 + 關鍵 P2）

目標：大型資料集下仍可用，且能量測。

| 順序 | 項目 | 動作要點 |
|---:|---|---|
| 1 | PERF-01 | 偵測 FTS5；降級時加上限與前綴；`/api/health` 暴露引擎種類 |
| 2 | PERF-04 | IMAP 增量 + 批次 FETCH + 節流；同步耗時入帳號狀態（不含主旨） |
| 3 | RACE-02 | 版本簽章驅動可重入衍生；single-flight 重建；壞卡隔離 |
| 4 | OBS-02 | 同步／Agent／搜尋耗時與計數；健康端點彙總（無 PII） |
| 5 | PERF-05 | `list_deliverables` 以 mtime 索引／快取；維持 limit |
| 6 | OBS-05 | `usage.jsonl` 行格式測試（只有計數與時間戳） |

退出條件：
- 合成 2 萬封信下搜尋 P95 在可接受上限；降級路徑仍正確。
- 併發「同步 + 重建」無重複卡、索引最終一致。
- 健康端點可觀到同步／搜尋耗時，且通過無 PII 掃描。

建議新增測試：
- `test_fmb_perf_search_scale.py`：2 萬封假信、有／無 FTS5。
- `test_fmb_perf_imap_incremental.py`：假 IMAP 斷言唯讀命令與批次。
- `test_fmb_perf_derived_reentrant.py`：併發重建無重複。
- `test_fmb_perf_deliverables_index.py`：大量卡片下列表耗時與正確性。

## 里程碑 2：規模化 UX 與恢復能力（其餘 P2）

目標：大收件匣好用、產物可控、可安全升級與重啟。

| 順序 | 項目 | 動作要點 |
|---:|---|---|
| 1 | PERF-02 | `/api/inbox` 分頁／cursor；前端虛擬列表；保留深連結與鍵盤 |
| 2 | PERF-03 | Agent 來源／包片段短 TTL 快取；明確上限；附階段耗時 |
| 3 | RACE-03 | 清除快取加鎖；請求端對暫時空結果重試一次 |
| 4 | TIME-03 | 冪等唯讀操作有界重試（退避 + 抖動）；與逾時共存 |
| 5 | TIME-04 | outbox tick 輕量化；重活交背景；記 tick 耗時 |
| 6 | RECV-02 | 成果卡原子寫入；讀取容忍缺檔 |
| 7 | RECV-03、RECV-04 | 可回復遷移 + 版本檢查；重啟後排程／undo 續存 |
| 8 | LEAK-04 | 用量檔輪轉；產物保留期；不誤刪受保留資料 |

退出條件：
- 大型收件匣 time-to-interactive 與 DOM 節點數受控；深連結／鍵盤不回歸。
- 同一對象重複 Agent 請求第二次更快且結果一致。
- 併發 clear 無未處理例外；升級／重啟路徑資料保留。

建議新增測試：
- `test_fmb_perf_inbox_pagination.py`：分頁正確、深連結保留。
- `test_fmb_perf_pack_cache.py`：二次請求更快且一致。
- `test_fmb_perf_cache_clear_race.py`：併發 clear + 讀取。
- `test_fmb_perf_retry_backoff.py`：重試次數、退避、有界停止。
- `test_fmb_perf_outbox_restart.py`：重啟後排程與 undo。
- `test_fmb_perf_usage_rotation.py`：輪轉後檔數／大小受控。

## 里程碑 3：打磨（P3）

| 項目 | 動作要點 |
|---|---|
| LEAK-05 | `agents.js` 渲染髒檢查／rAF 合併；觀察器去重 |
| OBS-04 | `/api/features` 健康訊息去內部路徑；保留非沙箱警告 |

退出條件：UI 語法檢查通過（無 Node 則跳過）；壞外掛可診斷且不洩路徑。

## 與 ROADMAP 的對齊

- 里程碑 0／1 支撐 ROADMAP 項目 2（一致性）、3（診斷）與 9（大型資料集效能）的前置條件。
- RECV-03 與 ROADMAP 項目 1（備份／還原）互相依賴：沒有可驗證遷移就很難安全還原。
- PERF-04 與 ROADMAP 項目 5（多 mailbox）共享假 IMAP 測試資產，建議一起擴充
  `tests/_tpi_imap_fake.py`。
- 本計畫不自行擴大範圍到寄送、遙測或沙箱宣稱；那些維持 ROADMAP 的決策閘門。

## 追蹤建議

- 每項對應一个 issue，標題用 `[PERF-01]` 等 ID，便於在 commit 與測試名中追溯。
- 合併前確認：新增測試皆在暫存根目錄運行、未連正式服務、未出現真實格式憑證、
  日誌與錯誤回應通過無 PII 掃描。
