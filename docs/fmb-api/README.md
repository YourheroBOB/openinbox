# Openinbox API 與介面參考

本文件彙整目前可由提供的 README、架構文件，以及 `server/features/agents.py`、`server/persona.py` 原始碼確認的介面。涵蓋 HTTP API、可直接呼叫的 Python 函式、MCP、CLI 與設定名稱。

> **範圍限制：**本次提供的原始碼內容不包含大多數功能模組的實作，也未包含 `server/app.py`、`server/agent_bridge.py`、`server/yhbmail.py`、`server/mcp_server.py` 等完整內容。因此，下列文件會標明哪些契約可由實作確認、哪些僅能確認路徑或功能名稱。未提供實作的參數、回應欄位、錯誤碼與 CLI 參數不推測；這些項目尚待對照完整原始碼補齊。

## 文件索引

- [HTTP API](http.md)：已知路徑、確認的參數與回應，以及尚待實作來源核對的端點。
- [Python API](python.md)：`agents.py` 與 `persona.py` 可見的公開函式。
- [MCP 介面](mcp.md)：stdio JSON-RPC 方法與已知工具名稱。
- [CLI 與設定](cli-settings.md)：可確認的命令、環境變數名稱與設定項名稱。

## 通用約定

- HTTP 服務供本機面板使用；有資料變更的外掛端點可能檢查請求來源。
- JSON API 的錯誤格式與 HTTP 狀態碼以各端點的實際實作為準；未提供實作的端點不在本文件臆測。
- 範例中的名稱與識別碼均為說明用佔位內容，不代表實際使用者或郵件資料。
- 設定參考只列名稱，不列設定值或憑證值。
- 產品目前以本機草稿、唯讀同步及明確人工確認為界；本參考不表示系統提供自動寄信能力。
