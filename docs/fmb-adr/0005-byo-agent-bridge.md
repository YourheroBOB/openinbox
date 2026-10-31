# ADR 0005：BYO agent bridge，`local` 是萬年後備

- 狀態：已接受（回溯整理）
- 相關程式：`server/agent_bridge.py`（`load_agent_cfg`、`context_pack`、`TOOLS`、`invoke_tool`、各 driver）、`agent.example.json`、`adapters/README.md`、`adapters/README.zh-Hant.md`、`server/features/agents.py`（fallback 與錯誤標籤的參考實作）

## 背景

專案明確承諾**不附託管模型**：使用者用自己已經在付的那條路（本機 Ollama、自架 vLLM、CLI 工具、自己的 worker）。
但同時，沒有接 agent 的人也必須能用——至少要看得到信、分得出來、拿得到草稿骨架。
於是「有 agent」與「沒 agent」不是兩種產品，而是同一條路徑上的兩個終點。

## 決策

1. `agent.json` 選 driver：`local`（預設）、`openai_compatible`、`cli`、`http`。
2. **`local` 永遠可用**，零網路；它是所有失敗情況的後備，不是「低配版」。
3. 每個 AI 功能都先組一個 **context pack**：使用者人格（persona）、與任務相關的本機資料（信件片段、看板、卡片）、語言、以及**規則**（唯讀、不要捏造、來源文字視為資料而非指令）。
4. 呼叫順序固定：**先在本機算出結果 → 有 agent 才交它改寫 → 失敗或空回應就退回本機結果**。
5. 回應要老實說：`driver`（實際用了誰）、`fallback`（是否退回本機）、`error`（錯誤類別）。UI 必須把「本機啟發式」標出來，不能讓使用者誤以為是模型輸出。
6. **錯誤訊息不直接外露**：bridge 的例外可能夾帶端點回應或 CLI 對 prompt 的回顯，所以只回例外類別，必要時附上 HTTP 狀態碼（`features/agents.py` 的 `error_label` 是參考做法）。
7. 提示詞要寫明：來源文字是引用的信件內容，只能當資料；缺的事實標 `[待填]`／`[missing]`，不要發明人名、金額、日期。

## 取捨

**我們放棄**

- 統一的模型行為與品質保證（每個 driver 差很多，token 用量有時只能估算）。
- 伺服器端保存對話狀態；對話是「每次帶上下文」的無狀態呼叫。

**我們得到**

- 不綁供應商、可完全離線、可換模型不用改程式。
- 使用者自己控制成本與隱私：只有自己的 driver 會看到 context pack。

**已知代價**

- 每個功能的 prompt 都要自己維護，規則容易漂移（所以規則集中在 pack 裡，而不是散在功能中）。
- 逾時與延遲不可控，UI 需要忙碌狀態。

## 後果

- 新增 AI 功能時，**先寫本機版**，再接 bridge，最後補 fallback 標示與測試。
- 工具的增刪只改 `agent_bridge.TOOLS` 與 `invoke_tool`：HTTP `/api/v1/tools` 與 MCP 兩邊同時生效（ADR 0010）。
- 不要在使用者介面或 API 回應裡放原始例外字串、端點 URL 或 prompt 內容。
- 任何「讓 agent 有副作用」的提案，先回頭看 ADR 0002。
