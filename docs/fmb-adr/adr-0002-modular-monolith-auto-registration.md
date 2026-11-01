# ADR-0002：模組化單體——外掛自動註冊與 UI 模組動態載入

- 狀態：已接受（現況仍有效）
- 日期：事後補建（原始決策日未記錄）
- 影響範圍：`server/features/`、`ui/modules/`、`server/app.py`、`ui/index.html`
- 相關：ADR-0001、ADR-0012；ROADMAP 第 10 項

## 背景

功能面已累積大量能力（`STATE.md` 自述 38 項 GenMail 對齊功能已完成），且仍持續新增
技能、面板與整合。如果每次加功能都要改 `server/app.py` 的路由表或 `ui/index.html` 的
載入清單，會造成：核心檔衝突不斷、 reviewers 要在巨型 diff 裡找焦點、壞功能無法單獨隔離。

## 決策

1. **後端外掛**：`server/features/*.py` 在啟動時被匯入，模組用 `features` 提供的
   `@get`／`@post` 裝飾器自我註冊路由；`server/app.py` 不需要為新功能修改。
2. **前端外掛**：`ui/modules/*.js` 由 `ui/index.html` 依 `GET /api/ui-modules` 回傳的
   清單載入；每個模組自帶雙語字典與樣式。
3. **可觀測性**：`GET /api/features` 列出已載入功能、路由與匯入錯誤——壞外掛被看見，
   但不拖垮全域。
4. **請求契約**：`req.query`、`req.body`、`req.lang_zh()`；非 JSON 回應用 `Raw`；
   雙語由各模組自行負責（ADR-0009）。
5. 慣例優於設定：放對檔案位置就生效，不維護手動 manifest。

## 取捨

| 考慮過的做法 | 為什麼沒有選 |
|---|---|
| 手動路由／模組登錄檔 | 每加功能要改兩處核心，衝突與遺漏成本高 |
| 插件子程序沙箱 | 單機工具不需要，且與「受信任程式碼」定位衝突（ADR-0012） |
| 單體大 switch／巨型模組 | 已走到外掛化，回頭會讓檔案難以 review |

## 後果

**正面**

- 加功能＝丟檔案；核心 `app.py`／`index.html` 穩定，diff 集中在功能本身。
- 壞外掛的錯誤在 `/api/features` 可見，影響面局限。
- 測試可針對單一外掛檔撰寫（如 `tests/test_fmb_contract_feature_imap_mailbox.py`）。

**負面／代價**

- 啟動時 import 有副作用：語法錯誤、缺少模組會在啟動期爆發（靠 `/api/features` 診斷）。
- 路由衝突、命名空間污染、版本相容性目前靠慣法，沒有治理機制（ROADMAP 第 10 項）。
- 模組間共享全域狀態（SQLite 連線、`yhbmail.TZ`）需開發者自律。

## 證據

- `README.md`「Add a feature」段與 `from features import get, post` 範例。
- `docs/fmb/ARCHITECTURE.md` 第 3.2、6.2 節（外掛契約）。
- `server/features/agents.py` 以 `from features import Raw, get, post` 註冊六個路由。
