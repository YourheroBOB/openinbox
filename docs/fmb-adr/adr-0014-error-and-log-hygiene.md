# ADR-0014：錯誤與日誌淨化——只回事件類別，不回內容

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：所有 API、`agent_bridge`、`usage.py`、`plugins.py`、`providers.py`
- 相關：ADR-0005、ADR-0006、ADR-0011；ROADMAP 第 3 項與完成定義第 9 條

## 背景

外部 Agent 的錯誤訊息很「髒」：CLI stderr 可能回映整個提示詞，HTTP 錯誤可能夾帶端點回應
內文；郵件主旨、寄件人、案件資訊更不該出現在錯誤裡。同時 BYOK 用量記錄若要可分享、可除錯，
就只能是數字，不能是內容。

## 決策

1. **對外錯誤只保留類別與狀態碼**：例外類型名稱，加上可解析出的 HTTP 狀態碼；
   **不回訊息本文**（`features/agents.py` 的 `error_label` 即此模式，並在 docstring 說明理由）。
2. **用量只記 token 數**：端點有回 `usage` 記實數，否則估算；不記提示詞、模型回答或金鑰。
3. **log 與診斷不含內容**：只記錄事件類型、錯誤類別、HTTP 狀態、耗時與計數；
   不含郵件主旨、寄件人、內文、案件或當事人資料、憑證、外部端點原始回應。
4. **供應商診斷先正規化**：CLI 錯誤文字可能不穩定或含敏感內容，先分類成
   「缺少環境變數／CLI 不存在／認證失敗／網路或 TLS 失敗／帳號拒絕」再顯示；
   缺密碼只顯示環境變數名稱（ADR-0006）。
5. `/api/features` 的匯入錯誤不洩漏完整內部路徑或郵件內容。
6. 上游 CLI 行為差異靠本機整合測試與明確版本假設維護，不靠把錯誤原文丟給使用者。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| 回傳完整錯誤訊息 | 方便但會洩漏提示詞、端點回應與郵件內容 |
| 日誌記內容以便事後分析 | 不可逆隱貌風險；本機優先產品不該累積內容 |
| 引進第三方 log／APM | 違反零 pip 與無遙測原則 |

## 後果

**正面**

- 截屏、issue 回報、log 分享都不會外流敏感內容。
- 錯誤格式統一，測試可斷言「只有類別與狀態碼」。

**負面／代價**

- 除錯難度提高：需要在本地以暫存根目錄與假資料重現（`tmp_path`＋fake IMAP／CLI）。
- 分類映射要隨上游調整維護。

## 證據

- `server/features/agents.py`：`error_label` docstring「Never the message itself: agent_bridge
  errors can include the endpoint body or a CLI stderr echo of the prompt.」與 `_HTTP_STATUS_RE`。
- `README.md`「BYOK usage」段：「No prompts, answers or keys are logged.」
- `docs/fmb/ROADMAP.md` 完成定義第 9 條、第 3 項建議範圍。
- `docs/fmb-perf/README.md` 安全與測試規範第 4 條。
