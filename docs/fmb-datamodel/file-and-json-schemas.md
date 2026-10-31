# 檔案格式與 JSON Schema

## 1. 通用格式規則

| 格式 | 編碼 | 規則 |
|---|---|---|
| JSON | UTF-8 | 檔案根為 object 或 schema 明確允許的型別；輸出採兩空格縮排時不影響解析 |
| JSON Lines | UTF-8 | 每行一個完整 JSON object；不得使用多行物件或陣列 |
| Markdown | UTF-8 | 衍生投影優先由主 JSON 重建；手寫內容不得被重建程序覆寫 |
| HTML | UTF-8 | 動態內容一律轉義；不允許 script、外部資源或 inline event handler |
| ICS | UTF-8 | CRLF 相容；以 `BEGIN:`／`END:` 配對 |
| EML | UTF-8 | 標準 MIME；附件以 MIME part 表示 |

### JSON 共通約定

- 未知欄位應被忽略或保留，不得讓整份設定失效。
- `null` 與缺少欄位需依各 schema 定義處理。
- 日期時間採 ISO 8601；跨時區資料另外保留 offset 或 IANA timezone。
- 陣列順序通常不具業務意義；搜尋結果等依文件另有排序規則。
- 布林值只使用 JSON boolean，不使用字串 `"true"`／`"false"`。

## 2. `accounts.json`

### 2.1 欄位

| 欄位 | 型別 | 必要 | 說明 |
|---|---|---|---|
| `mode` | string | 是 | `demo` 或 `live` |
| `accounts` | array | 是 | 帳號集合 |
| `calendars` | array | 否 | 保留的行事曆帳號／來源集合；其細部格式由 calendar 設定契約定義 |

### 2.2 Account 欄位

| 欄位 | 型別 | 必要 | 說明 |
|---|---|---|---|
| `email` | string | 是 | 帳號識別；不得在文件中抄錄實值 |
| `driver` | enum | 是 | `demo`、`gog`、`gsk`、`imap` |
| `platform` | string | 否 | 顯示或相容性用途，例如郵件平台類型 |
| `label` | string | 否 | 使用者顯示名稱 |
| `provider` | enum | 否 | `icloud`、`fastmail`、`yahoo`、`zoho`；其他供應商以 `host` 描述 |
| `host` | string | 否 | 自訂 IMAP 主機 |
| `port` | integer | 否 | IMAP port；預設由 driver 決定 |
| `security` | enum | 否 | `ssl`、`starttls`、`none`；`none` 僅允許 loopback |
| `username` | string | 否 | IMAP 登入帳號 |
| `mailbox` | string | 否 | 預設信箱資料夾 |
| `password_env` | string | 否 | 密碼所在環境變數名稱；不得填秘密值 |
| `signature` | string／object | 否 | 帳號簽名；mailops 功能延伸 |
| `primary` | boolean | 否 | 主帳號排序延伸 |

### 2.3 JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "AccountSet",
  "type": "object",
  "required": ["mode", "accounts"],
  "properties": {
    "mode": {"type": "string", "enum": ["demo", "live"]},
    "accounts": {
      "type": "array",
      "items": {"$ref": "#/$defs/account"}
    },
    "calendars": {"type": "array", "items": {"type": "object"}}
  },
  "additionalProperties": true,
  "$defs": {
    "account": {
      "type": "object",
      "required": ["email", "driver"],
      "properties": {
        "email": {"type": "string", "minLength": 1},
        "driver": {"type": "string", "enum": ["demo", "gog", "gsk", "imap"]},
        "platform": {"type": "string"},
        "label": {"type": "string"},
        "provider": {"type": "string", "enum": ["icloud", "fastmail", "yahoo", "zoho"]},
        "host": {"type": "string"},
        "port": {"type": "integer", "minimum": 1, "maximum": 65535},
        "security": {"type": "string", "enum": ["ssl", "starttls", "none"]},
        "username": {"type": "string"},
        "mailbox": {"type": "string"},
        "password_env": {"type": "string", "minLength": 1},
        "signature": {},
        "primary": {"type": "boolean"}
      },
      "additionalProperties": true
    }
  }
}
```

若 provider 設定含明文秘密欄位，載入器必須拒絕該設定，而不是忽略後繼續。

## 3. `agent.json`

### 3.1 欄位

| 欄位 | 型別 | 說明 |
|---|---|---|
| `driver` | enum | `local`、`openai_compatible`、`cli`、`http` |
| `comment` | string | 選填說明 |
| `openai_compatible` | object | 相容端點設定 |
| `openai_compatible.base_url` | string | 端點基底 URL |
| `openai_compatible.model` | string | 模型名稱 |
| `openai_compatible.api_key_env` | string | API key 所在環境變數名稱 |
| `cli` | object | CLI driver 設定 |
| `cli.command` | string array | argv；不得以 shell 字串拼接 |
| `cli.timeout_sec` | integer | timeout 秒數 |
| `http` | object | HTTP worker 設定 |
| `http.url` | string | worker URL |
| `http.timeout_sec` | integer | timeout 秒數 |

### 3.2 JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "AgentProfile",
  "type": "object",
  "required": ["driver"],
  "properties": {
    "driver": {"type": "string", "enum": ["local", "openai_compatible", "cli", "http"]},
    "comment": {"type": "string"},
    "openai_compatible": {
      "type": "object",
      "properties": {
        "base_url": {"type": "string"},
        "model": {"type": "string"},
        "api_key_env": {"type": "string"}
      },
      "additionalProperties": true
    },
    "cli": {
      "type": "object",
      "properties": {
        "command": {"type": "array", "items": {"type": "string"}},
        "timeout_sec": {"type": "integer", "minimum": 1}
      },
      "additionalProperties": true
    },
    "http": {
      "type": "object",
      "properties": {
        "url": {"type": "string"},
        "timeout_sec": {"type": "integer", "minimum": 1}
      },
      "additionalProperties": true
    }
  },
  "additionalProperties": true
}
```

`local` driver 必須零網路；外部 driver 失敗時可退回 local。

## 4. `rules.json`

### 4.1 RuleSet

| 欄位 | 型別 | 說明 |
|---|---|---|
| `version` | integer | 規則格式版本 |
| `comment` | string | 選填說明 |
| `rules` | array | 規則集合 |

### 4.2 Rule

| 欄位 | 型別 | 必要 | 說明 |
|---|---|---|---|
| `id` | string | 是 | 規則穩定 ID |
| `name` | string | 是 | 顯示名稱 |
| `description` | string | 否 | 說明 |
| `enabled` | boolean | 是 | 是否啟用 |
| `match` | enum | 是 | `any` 或 `all` |
| `conditions` | array | 是 | 條件集合 |
| `actions` | array | 是 | 動作集合 |
| `stop` | boolean | 否 | 命中後是否停止後續規則 |

### 4.3 Condition

| 欄位 | 型別 | 說明 |
|---|---|---|
| `field` | enum | `subject`、`text`、`from`、`label`、`category`、`lane`、`replied` 等 |
| `op` | enum | `contains`、`not_contains`、`equals`、`regex`、`is` |
| `value` | string／boolean | 比較值；regex 必須安全編譯並限制資源 |

### 4.4 Action

| `type` | 額外欄位 | 說明 |
|---|---|---|
| `label` | `label` | 新增本機標籤 |
| `mark_read` | 無 | 設為已讀 |
| `archive` | 無 | 移至封存 |
| `task` | `action`、`note` | 建立分流任務 |
| `draft_reply` | `template`、`template_zh` | 建立本機草稿 |

### 4.5 JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "RuleSet",
  "type": "object",
  "required": ["rules"],
  "properties": {
    "version": {"type": "integer", "minimum": 1},
    "comment": {"type": "string"},
    "rules": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "name", "enabled", "match", "conditions", "actions"],
        "properties": {
          "id": {"type": "string", "minLength": 1},
          "name": {"type": "string"},
          "description": {"type": "string"},
          "enabled": {"type": "boolean"},
          "match": {"type": "string", "enum": ["any", "all"]},
          "conditions": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["field", "op", "value"],
              "properties": {
                "field": {"type": "string"},
                "op": {"type": "string"},
                "value": {}
              },
              "additionalProperties": true
            }
          },
          "actions": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["type"],
              "properties": {"type": {"type": "string"}},
              "additionalProperties": true
            }
          },
          "stop": {"type": "boolean"}
        },
        "additionalProperties": true
      }
    }
  },
  "additionalProperties": true
}
```

規則只可改本機狀態或建立本機草稿，不得自動對外寄送。

## 5. `vault/persona.json`

### 5.1 欄位

| 欄位 | 型別 | 說明 |
|---|---|---|
| `updated_at` | datetime string | 建構時間 |
| `mode` | string | 建立時的帳號模式 |
| `identity` | object | 身分摘要 |
| `identity.name` | string | 顯示名稱 |
| `identity.role` | string | 角色 |
| `identity.timezone` | string | 時區 |
| `identity.accounts` | string array | 帳號集合；屬敏感本機資料 |
| `how_you_write` | string array | 文風觀察 |
| `how_you_run_inbox` | string array | 收信習慣 |
| `attention_now` | string array | 當下注意事項 |
| `inbox_priorities` | object array | 類別統計；每項含 `category`、`count` |
| `top_senders` | object array | 寄件人統計；每項含 `email`、`count` |
| `facts_learned` | integer | 推論來源數量 |
| `source` | string | 建構來源類別 |

### 5.2 JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Persona",
  "type": "object",
  "required": ["updated_at", "mode", "identity", "inbox_priorities", "top_senders"],
  "properties": {
    "updated_at": {"type": "string"},
    "mode": {"type": "string"},
    "identity": {
      "type": "object",
      "required": ["name", "role", "timezone", "accounts"],
      "properties": {
        "name": {"type": "string"},
        "role": {"type": "string"},
        "timezone": {"type": "string"},
        "accounts": {"type": "array", "items": {"type": "string"}}
      },
      "additionalProperties": true
    },
    "how_you_write": {"type": "array", "items": {"type": "string"}},
    "how_you_run_inbox": {"type": "array", "items": {"type": "string"}},
    "attention_now": {"type": "array", "items": {"type": "string"}},
    "inbox_priorities": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["category", "count"],
        "properties": {
          "category": {"type": "string"},
          "count": {"type": "integer", "minimum": 0}
        },
        "additionalProperties": true
      }
    },
    "top_senders": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["email", "count"],
        "properties": {
          "email": {"type": "string"},
          "count": {"type": "integer", "minimum": 0}
        },
        "additionalProperties": true
      }
    },
    "facts_learned": {"type": "integer", "minimum": 0},
    "source": {"type": "string"}
  },
  "additionalProperties": true
}
```

`persona.md` 是此 JSON 的閱讀投影，不應反向當作唯一主來源。

## 6. `data/contacts.json`

聯絡人 CRM 為使用者所有，應採 canonical envelope：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ContactBook",
  "type": "object",
  "required": ["version", "contacts"],
  "properties": {
    "version": {"type": "integer", "minimum": 1},
    "updated_at": {"type": "string"},
    "contacts": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["email", "name", "domain", "email_count", "last_topic", "stage", "tags", "notes"],
        "properties": {
          "email": {"type": "string", "minLength": 1},
          "name": {"type": "string"},
          "domain": {"type": "string"},
          "email_count": {"type": "integer", "minimum": 0},
          "last_topic": {"type": "string"},
          "stage": {"type": "string"},
          "tags": {"type": "array", "items": {"type": "string"}},
          "notes": {"type": "string"}
        },
        "additionalProperties": true
      }
    }
  },
  "additionalProperties": true
}
```

實作若仍需讀取舊版 envelope，應在 loader 邊界正規化，不能讓兩種格式同時被寫回。

## 7. `data/skills.json`

技能 ID 以 `skills/` 檔名去掉 `.md` 為準。Canonical 結構：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SkillSettings",
  "type": "object",
  "required": ["version", "skills"],
  "properties": {
    "version": {"type": "integer", "minimum": 1},
    "skills": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "enabled": {"type": "boolean"},
          "updated_at": {"type": "string"}
        },
        "additionalProperties": true
      }
    }
  },
  "additionalProperties": true
}
```

未列出的技能採系統預設值。關閉的技能必須拒絕執行，且不能只在 UI 隱藏。

## 8. `data/usage.jsonl`

每行代表一次模型呼叫；不記提示詞、回答、郵件內容或秘密。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `timestamp` | datetime string | 呼叫時間 |
| `driver` | enum | 實際 driver |
| `model` | string | 可選模型名稱 |
| `source` | string | 功能或呼叫來源 |
| `input_tokens` | integer | 輸入 token 數 |
| `output_tokens` | integer | 輸出 token 數 |
| `total_tokens` | integer | 總 token 數 |
| `estimated` | boolean | 是否為估算值 |

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "UsageEvent",
  "type": "object",
  "required": ["timestamp", "driver", "total_tokens", "estimated"],
  "properties": {
    "timestamp": {"type": "string"},
    "driver": {"type": "string"},
    "model": {"type": "string"},
    "source": {"type": "string"},
    "input_tokens": {"type": "integer", "minimum": 0},
    "output_tokens": {"type": "integer", "minimum": 0},
    "total_tokens": {"type": "integer", "minimum": 0},
    "estimated": {"type": "boolean"}
  },
  "additionalProperties": true
}
```

## 9. `data/deliverables/<id>.json`

### 9.1 Deliverable

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | string | 安全且唯一的成果 ID |
| `title` | string | 顯示標題 |
| `kind` | enum | `research_person`、`research_company`、`meeting_prep` |
| `target` | string | 使用者輸入的研究對象或任務目標 |
| `lang` | enum | `zh` 或 `en` |
| `created` | datetime string | 建立時間 |
| `driver` | enum | 實際使用的 driver |
| `fallback` | boolean | 是否退回本機 |
| `text` | string | Markdown 成果正文 |
| `sources` | object array | 本機來源摘要 |

### 9.2 Source

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | string | 郵件 ID |
| `subject` | string | 主旨 |
| `from` | string | 寄件人 |
| `date` | string | 原始日期字串 |
| `snippet` | string | 有限長度的來源片段 |

### 9.3 JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "AgentDeliverable",
  "type": "object",
  "required": ["id", "title", "kind", "lang", "created", "driver", "fallback", "text", "sources"],
  "properties": {
    "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]{2,80}$"},
    "title": {"type": "string"},
    "kind": {"type": "string", "enum": ["research_person", "research_company", "meeting_prep"]},
    "target": {"type": "string"},
    "lang": {"type": "string", "enum": ["zh", "en"]},
    "created": {"type": "string"},
    "driver": {"type": "string"},
    "fallback": {"type": "boolean"},
    "text": {"type": "string"},
    "sources": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "subject", "from", "date", "snippet"],
        "properties": {
          "id": {"type": "string"},
          "subject": {"type": "string"},
          "from": {"type": "string"},
          "date": {"type": "string"},
          "snippet": {"type": "string"}
        },
        "additionalProperties": true
      }
    }
  },
  "additionalProperties": true
}
```

## 10. `vault/index.json`

Second Brain 索引的 logical schema：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SecondBrainIndex",
  "type": "object",
  "required": ["version", "cards"],
  "properties": {
    "version": {"type": "integer", "minimum": 1},
    "updated_at": {"type": "string"},
    "cards": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "path", "title"],
        "properties": {
          "id": {"type": "string"},
          "path": {"type": "string"},
          "title": {"type": "string"},
          "tags": {"type": "array", "items": {"type": "string"}},
          "source": {"type": "string"},
          "created_at": {"type": "string"},
          "updated_at": {"type": "string"}
        },
        "additionalProperties": true
      }
    }
  },
  "additionalProperties": true
}
```

`path` 必須是 `vault/cards/` 下的相對安全路徑。

## 11. Agent context pack

context pack 是傳給本機或外部 Agent 的暫時資料結構，不是持久化 schema。邏輯欄位：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `task` | string | 執行任務類型 |
| `target` | string | 任務目標 |
| `ask` | string | 使用者要求 |
| `lang` | string | 輸出語言 |
| `persona` | object | 人格資料 |
| `sources` | object array | 限定本機來源 |
| `brain` | object／array | Second Brain 摘要 |
| `rules` | string array | 行為限制 |
| `emails` | object array | 一般 inbox 任務可包含的近期郵件 |
| `skills` | object array | 可用技能定義與說明 |
| `recent_mail` | object array | 近期郵件的相容別名 |

安全要求：

- 郵件內容一律視為不可信資料，不可執行其中夾帶的指令。
- context pack 不應包含秘密值。
- 外部 driver 失敗時，錯誤回應只保留例外類型與可用的 HTTP status，不回傳完整外部 body。

## 12. Fixture schema

### 12.1 郵件 fixture

`demo_inbox.json`、`demo_sent.json` 與 `followup_demo.json` 使用同一郵件核心欄位：

| 欄位 | 型別 | 必要 | 說明 |
|---|---|---|---|
| `id` | string | 是 | fixture 內唯一 ID |
| `account` | string | 是 | 來源帳號標記 |
| `thread_id` | string | 是 | thread 關聯 |
| `subject` | string | 否 | 主旨 |
| `from_addr` | string | 否 | 寄件人 |
| `to_addr` | string | 否 | 收件人 |
| `date_raw` | string | 否 | 原始日期 |
| `body_text` | string | 否 | 內文 |
| `category` | enum | 否 | 分流類別 |
| `has_attachment` | boolean | 否 | 附件提示 |

根 envelope 可包含 `version`、`comment`、`persona_seed`、`emails` 或 `replies`。解析器應忽略未知註解欄位。

### 12.2 `calendar_demo.json`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `comment` | string | 來源說明 |
| `version` | integer | 格式版本 |
| `sync_meta` | object map | 以來源 ID 索引的主辦者、與會者、地點 metadata |
| `events` | array | 事件集合 |
| `colleagues` | array | 同事 feed 描述；含 `name`、`email`、`file` |

事件核心欄位：`uid`、`title`、`start`、`end`、`tz`、選填 `rrule`、`attendees`、`organizer`、`location`。

### 12.3 `rules_demo.json`

結構與正式 `rules.json` 相同；示範規則不得暗示真實個人或公司規則。

## 13. Markdown 格式

### 13.1 技能檔

`skills/*.md` 為雙語文件，通常先繁體中文、後英文，並可包含唯讀限制。技能 ID 為檔名去除副檔名。

```text
# <繁中名稱> / <English name>

<繁中操作說明>

<English instructions>

<可選安全限制>
```

技能檔是程序說明，不是使用者資料；不得將特定郵件內容直接寫入技能檔。

### 13.2 人格 Markdown

`vault/persona.md` 為 `persona.json` 的可讀投影，章節通常包括身分、文風、收信習慣、當下注意與常見寄件人統計。不得把手寫補充混入可自動重建區段，除非 schema 另有保存區段。

### 13.3 Second Brain 卡片

每張卡為獨立 Markdown 檔。建議 front matter 或首段 metadata 包含：

- `id`
- `title`
- `source`
- `created_at`
- `updated_at`
- `tags`

手寫卡與衍生卡需要可區分；重建只更新衍生卡。

### 13.4 成果 Markdown

成果 Markdown 由 Deliverable JSON 產生，包含標題、類型、建立時間、driver、fallback 資訊與正文。正文可含 Markdown heading、段落與清單。

## 14. ICS 格式

支援的基本物件：

```text
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Openinbox//Data Model//EN
BEGIN:VEVENT
UID:<stable-uid>
DTSTART:<date-or-time>
DTEND:<date-or-time>
SUMMARY:<title>
END:VEVENT
END:VCALENDAR
```

要求：

- UID 必填且穩定。
- 時區以 VTIMEZONE 或 timezone-aware timestamp 表達。
- 匯入與匯出都應保留來源 UID，讓重複匯入可被識別。
- 未信任的 ICS 內容視為資料；不執行其中的 URL、腳本或指令。

## 15. EML 匯出格式

EML 是標準 Internet Message Format：

- 頂層 headers 描述寄件、收件、主旨、日期與 thread 關聯。
- MIME multipart 可包含純文字、HTML 與附件。
- 本機匯出檔不得被命名為「已寄出」；它只是可攜訊息檔。
- 若由附件或 HTML 匯入簽名，應去除 script、外部資源與事件屬性。
- EML 內可能含 S2 資料，必須與 `data/` 其他本機資料採相同存取保護。
