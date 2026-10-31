# Openinbox 常見問題與疑難排解（FAQ）

本目錄整理 `YourheroBOB/openinbox`（TooPowerInbox）的使用者與開發者常見問題。內容依 repo 內可見的程式、測試與文件整理：`README.md`／`README.zh-Hant.md`、`CONTRIBUTING*.md`、`adapters/README*.md`、`docs/fmb/ARCHITECTURE.md`、`docs/fmb/ROADMAP.md`、`server/features/*.py`、`ui/modules/*.js`、`state/*.md`。

## 使用說明

- 本目錄只新增文件，未修改任何既有檔案。
- 文件不含 token、金鑰、密碼、客戶個資、LINE 訊息內文或案件當事人資料。示例一律用 `example.com`／`.example` 虛構網域與 `FAKE_VALUE_FOR_TEST` 這類明顯假值。
- 若實際行為與最新程式不同，以程式碼為準，並回頭更新本目錄。
- 每一題固定四欄：**問題**、**原因**、**解法**、**相關檔案**。

## 文件索引

| 檔案 | 對象 | 內容 | 題號 |
|---|---|---|---|
| [USER-FAQ.md](USER-FAQ.md) | 使用者 | 安裝啟動、示範模式、語系、接真信箱、IMAP 密碼、Copilot 降級、草稿與 outbox、清除快取、備份、PWA、雲端主機 | U1–U12 |
| [DEVELOPER-FAQ.md](DEVELOPER-FAQ.md) | 開發者 | 新增功能外掛與 UI 模組、Origin 檢查、測試規範、搜尋索引、Agent bridge、成果卡片、對外 API 契約 | D1–D9 |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 兩者 | 症狀 → 原因 → 解法 → 相關檔案（埠佔用、模組沒載入、缺密碼、TLS、Agent fallback、`@agent` 沒觸發、搜尋落後、PWA、MCP 等） | T1–T13 |

## 三句話版本

1. 預設是**示範模式**，不用登入任何信箱；`./install.sh && ./run.sh` 後開 `http://127.0.0.1:8770/`。
2. **不預設寄信**：草稿、排程、outbox 都只留在本機，`save_draft` 只寫本機 SQLite。
3. IMAP 是**唯讀**（`EXAMINE` + `BODY.PEEK`），密碼只從環境變數讀，`accounts.json` 寫明文 `password` 會被拒絕。
