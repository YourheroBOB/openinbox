# ADR-0003：不預設寄信——人工確認的本機 outbox

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`server/features/outbox.py`、`_outbox_transport.py`、`compose.py`、`agent_bridge`
- 相關：ADR-0005、ADR-0008；ROADMAP 第 6、8 項與決策閘門

## 背景

自動寄信是不可逆操作：誤觸、被提示注入誘發、或 Agent 誤讀情境，都可能把私人內容寄給
錯誤的對象。產品定位是「信箱腦」而不是「寄信機器」；作者明確不希望系統代替人做出承诺。

## 決策

1. **沒有啟用中的預設對外寄送路徑**：`send is off`，草稿不會離開機器，除非使用者自己接出去。
2. 草稿只進 SQLite `drafts` 表；outbox 進入可寄出狀態**必須**有使用者明確確認
   （確認 token ＋ `ack`）。
3. 排程到期只把項目移入**本機** outbox，不觸發任何外部傳送。
4. 倒數時間內可取消；取消不刪除原始草稿。
5. 提供本機 EML 匯出作為「把東西帶出去」的人工出口。
6. 不存在能繞過確認的 Agent 工具；`adapters/README` 明言 "Send is not exposed"。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| 內建 SMTP 直接寄信 | 不可逆風險與產品定位衝突 |
| Agent 一鍵寄出 | 等於把承諾權交給模型，違反人工確認原則 |
| 完全不提供 outbox | 排程、確認、撤銷、匯出是有價值的本機編排能力 |

## 後果

**正面**

- 誤寄風險接近零；安全敘事誠實且可對外說明。
- `_outbox_transport.py` 成為唯一保留的傳輸／匯出邊界，未來若啟用寄送可獨立審查。

**負面／代價**

- 產品不是完整寄信客戶端；使用者要自己接最後一哩。
- outbox 語意（確認、撤銷、排程）需要文件與測試持續維護（ROADMAP 第 6、8 項）。

## 證據

- `README.md`：「Send is off. Drafts never leave the machine unless you wire that yourself.」
- `docs/fmb/ARCHITECTURE.md` 第 5.5、8.4 節。
- `adapters/README.md`：「Send is not exposed. Drafts stay in the local SQLite file.」
- `docs/fmb/ROADMAP.md` 決策閘門：「未來寄信能力——維持排除」。
