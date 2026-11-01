# 技能參考

技能是 `skills/*.md` 的雙語 markdown（正體中文在前、英文在後）。結果先在本機算出，有接 BYO agent 時再交給它改寫。每個技能都有開關，關閉的技能拒絕執行。

## 1. 內建技能

| 技能 | 檔名 | 用途 |
|---|---|---|
| 晨間簡報 | `morning-brief` | 把上一工作日之後的邮件分桶；「需要你」寫到不用開原信就能決定；唯讀 |
| 快速補課 | `catch-me-up` | 依寄件人與主題歸堆近期活動；先講還要回的 |
| 整理收件匣 | `categorize-inbox` | 分成需要你／即將到來／值得一看／僅供參考／可清理；點出最吵來源 |
| 幫我找 | `find-it-for-me` | 在本機資料中找東西（細節見技能檔） |
| 會前準備 | `meeting-prep` | 一頁會議準備：時間、與會者、相關邮件、未決問題、期限、附件；唯讀，不 RSVP |
| 這個人是誰 | `brief-this-person` | 針對單一寄件人的簡報（細節見技能檔） |
| 更了解你 | `know-you-better` | 讀人格檔說明寫作習慣與注意焦點；不捏造 |
| 本週安排 | `plan-my-week` | 合併行事曆與收件匣：期限→會議→未回覆 |
| 轉成投影片 | `turn-into-a-slide` | 產生本機 HTML 投影片於 `data/slides/`；不上傳 |
| 加入聯絡人 CRM | `crm-this-contact` | 寄件人存入 `data/contacts.json`：姓名、網域、往來次數、最近主題、階段、標籤、筆記 |

> 技能總表以 `skills/` 目錄實際檔案為準；上表依快照中的 `skills/*.md` 整理。

## 2. 技能 API

| 端點 | 說明 |
|---|---|
| `GET /api/skills` | 技能列表（含開關） |
| `POST /api/skills/run` | 執行技能；關閉中的技能拒絕執行；body 至少帶技能名，選用帶目標與 `lang`（確切欄位待確認） |
| `POST /api/skills/settings` | 開關與設定，存 `data/skills.json`（確切 body 待確認） |

也可以透過 `POST /api/v1/agent/run` 搭配 `skill` 使用；context pack 會帶上技能本文。

## 3. CRM API（`data/contacts.json`）

| 端點 | 說明 |
|---|---|
| `GET /api/crm/contacts` | 聯絡人列表 |
| `POST /api/crm/contacts/update` | 新增／更新聯絡人 |
| `POST /api/crm/contacts/delete` | 刪除聯絡人 |

資料只留本機。

## 4. 用量 API

`GET /api/usage`：回傳 BYOK token 用量（`data/usage.jsonl`）。端點有回 `usage` 記實數，否則估算；不記提示詞、回答或金鑰。
