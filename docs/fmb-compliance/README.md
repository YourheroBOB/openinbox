# 授權與資料合規盤點（openinbox）

本目錄是 openinbox／TooPowerInbox 的**工程面合規盤點**，涵蓋四塊：

1. 相依套件的授權相容性。
2. 程式處理的個人資料類別與流向。
3. 保存與刪除機制。
4. 記錄檔可能外洩的欄位。

並以台灣《個人資料保護法》（以下稱個資法）的一般要求做缺口對照與建議。

> **重要聲明**
> - 本目錄是工程盤點與待辦清單，**不是法律意見**。對外提供服務、商業使用或涉及第三人個資時，應由法務或外部顧問复核。
> - 條號以現行公布條文為準；若主管機關修法或發布新函釋，請以官方公告為準並更新本目錄。
> - 本目錄**不含任何真實個資、憑證、金鑰、LINE 訊息內文或案件當事人資料**。所有示例一律使用倉庫既有的虛構資料（`*@example.com`、`fixtures/`）或明顯假值（如 `FAKE_VALUE_FOR_TEST`）。

## 1. 文件索引

| 文件 | 內容 |
|---|---|
| [DEPENDENCIES.md](DEPENDENCIES.md) | 相依套件與授權矩陣、散布義務、授權 allowlist 建議、SBOM 缺口 |
| [DATA-INVENTORY.md](DATA-INVENTORY.md) | 資料主體、個資類別、資料集清單（RoPA-lite）、資料流與外送點、存取面 |
| [RETENTION-DELETION.md](RETENTION-DELETION.md) | 現有保存與刪除機制、刪除完整性缺口、建議保留期、當事人權利處理程序 |
| [LOGGING-REVIEW.md](LOGGING-REVIEW.md) | 記錄點盤點、可能外洩欄位、遮罩建議、驗收測試做法 |
| [PDPL-GAP-ANALYSIS.md](PDPL-GAP-ANALYSIS.md) | 個資法條文對照、缺口 G1–G16、風險等級與優先級 |
| [ACTION-PLAN.md](ACTION-PLAN.md) | P0／P1／P2 待辦、驗收條件、禁制事項、BOB 決策清單 |
| [PRIVACY-NOTICE-DRAFT.md](PRIVACY-NOTICE-DRAFT.md) | 告知事項草案（繁中／英文），供第 8 條與第 9 條落地參考 |

## 2. 盤點範圍與依據

### 2.1 依據的檔案（本輪可讀取的證據）

- 文件類：`README.md`、`README.zh-Hant.md`、`CONTRIBUTING.md`、`CONTRIBUTING.zh-Hant.md`、`STATE.md`、`docs/fmb/ARCHITECTURE.md`、`docs/fmb/ROADMAP.md`、`adapters/README*.md`、`state/*.md`。
- 程式類：`server/features/agents.py`（完整）、`ui/modules/agents.js`（完整）。
- 設定與腳本：`accounts.example.json`、`agent.example.json`、`install.sh`、`run.sh`、`.gitignore`、`LICENSE`。
- 資料：`fixtures/*.json`、`fixtures/ics/*.ics`、`skills/*.md`、`vault/cards/.gitkeep`。

### 2.2 本次**未能**直接讀取、需人工复核的檔案

`server/app.py`、`server/yhbmail.py`、`server/agent_bridge.py`、`server/persona.py`、`server/second_brain.py`、`server/mcp_server.py`、`server/features/*.py`（除 `agents.py` 外）、`scripts/smoke.sh`、`scripts/overnight.py`、`.github/workflows/smoke.yml`、`ui/index.html` 與其餘 `ui/modules/*.js`、`tests/*`。

因此本目錄對這些區域的描述均標成推論或待確認，並在 `ACTION-PLAN.md` 列為「需以程式碼確認」項目。

### 2.3 證據等級標記

本目錄統一使用下列標記，避免把推論當成事實：

| 標記 | 意義 |
|---|---|
| `[A]` | 已由本輪讀到的檔案內容直接確認（例如 `agents.py` 的錯誤遮罩、`LICENSE` 的 MIT 條文） |
| `[B]` | 由 README／ARCHITECTURE／ROADMAP 等文件推得，尚未逐行核對程式 |
| `[C]` | 未能確認，必須人工或後續工作確認 |

## 3. 適用前提（影響整體結論）

個資法第 51 條規定，自然人為單純個人或家庭活動而蒐集、處理或利用個人資料者，不適用該法。openinbox 的設計定位是**單機、單使用者、本機優先**，若僅由本人於個人生活中使用，實務上可能落在該條的豁免範圍。

但下列情況會使豁免**不再可靠**，必須改以非公務機關的一般義務（第 8、9、19、20、27 條等）檢視：

- 把工具提供給同事、客戶、家人以外的人使用，或部署成多人可連的服務。
- 用於營業、接案、客戶關係管理（`data/contacts.json` 的 CRM 用途即屬之）。
- 把信件內容外送到 BYO agent 或 MCP 客戶端背後的雲端模型。
- 由公司名義維運，或處理員工、客戶的資料。

> **保守預設**：不論目前是否落在第 51 條豁免，本目錄一律以「未來可能需要對外提供或商業使用」的前提列缺口， Priority 排序則允許把部分項目降級。

## 4. 與其他文件的關係

- `docs/fmb/ARCHITECTURE.md`：系統架構、資料表用途、安全邊界。本目錄不重複其內容，只從合規角度補「個資類別、保留期、刪除、告知」。
- `docs/fmb/ROADMAP.md`：其中第 1 項（備份還原）、第 2 項（衍生資料一致性）、第 3 項（同步診斷）與合規的資料正確性、可回復性直接相關，本目錄的建議會標註對應路線圖項目，避免重工。
- `docs/fmb-security/`（`AUDIT.md`、`CHECKLIST.md`）：技術安全面；本目錄聚焦個資法對應的技術與組織措施。

## 5. 維護方式

- 每次新增會處理個資的功能（新的 connector、新的 Agent 外送路徑、新的匯出格式），都應同步更新 `DATA-INVENTORY.md` 與 `LOGGING-REVIEW.md`。
- 每次調整保留期或刪除語意，都應更新 `RETENTION-DELETION.md`，並在 `ACTION-PLAN.md` 記錄驗收狀態。
- 文件本身不得貼入真實郵件、真實帳號或憑證；示例一律使用 `example.com` 或 `FAKE_VALUE_FOR_TEST`。
