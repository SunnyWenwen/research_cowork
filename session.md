# Cowork Session 機制

來源：即時內省（讀取本 session JSONL + session_info 工具實測），2026-06-12，引擎版本 2.1.170

## 底層即 Claude Code Session 引擎

本 session 的 user record 含 `"version": "2.1.170"`、`"entrypoint": "local-agent"`、`"promptSource": "sdk"`，且 JSONL 格式與 Claude Code 相同 → **Cowork 是以 `local-agent` 為進入點的 Claude Code/Agent SDK 引擎**，session 機制大量共用（可對照 `reseach_claude_code/session.md`）。

## 儲存位置與目錄結構（binary 層證實，2026-06-12）

來源：使用者複製 RoamingClaude 資料進專案，bash 分析。**修正第一輪的推測**。

```
AppData\Roaming\Claude\local-agent-mode-sessions\
└─ {ownerAccountId}\            # bc71ab19-... = 帳號 id（config 證實，非「裝置」）
   └─ {org-id}\                 # 9de92944-... = organizationId（組織；dxt blocklist URL 證實，2026-06-14 修正，原標「環境/裝置層」）
      ├─ local_{session-uuid}\          # ★ 每個 session 一個目錄
      │  ├─ outputs\                    # agent 暫存輸出（= cwd）
      │  ├─ uploads\                    # 上傳檔案
      │  ├─ audit.jsonl                 # ★★ HMAC 簽章稽核日誌（完整記錄，見下）
      │  ├─ .audit-key                  # HMAC 金鑰（binary，機敏）
      │  └─ .claude\
      │     ├─ projects\{encoded-cwd}\{cliSessionId}.jsonl  # 引擎層 JSONL（快照）
      │     ├─ sessions\  tasks\  backups\  policy-limits.json
      ├─ local_{session-uuid}.json      # ★★ App 層 session 狀態（同層 sibling 檔，見下）
      └─ spaces\{spaceId}\memory\       # Memory（219d9c7e-..., 依 space）
```

### 三份記錄，不是一份（解答「是否只是部分 log」）

每個 session 同時存在三種記錄，分屬不同層：

| 檔案 | 層 | 內容 | 我（VM agent）能否看到 |
|---|---|---|---|
| `.claude/projects/*.jsonl` | 引擎 | Claude Code 格式 transcript，**延遲快照**（實測停在 62 行） | ✅ 唯讀掛載 |
| `audit.jsonl` | App | **HMAC 簽章的完整稽核日誌**（實測 612 行 vs 引擎 62 行） | ❌ 在 session 目錄、未掛載 |
| `local_{uuid}.json` | App | session 狀態（systemPrompt、egress、folders…） | ❌ 未掛載 |

→ 之前我從 VM 看到的 62 行只是**引擎層延遲快照**，真正完整的記錄是 App 層 `audit.jsonl`（612 行）。這正是 `request_cowork_directory` 拒絕訊息所說「transcripts、session state 刻意不可存取」保護的東西。

- 兩層 session id：`local_{uuid}`（Cowork/App 層）vs `cliSessionId`（引擎 SDK 層，JSONL 檔名），**不同**。`audit.jsonl` 內 user record 用 App id、system/init 用引擎 id，**audit 合併了兩層**。**一對多**：一個 `local_{uuid}` 每被 resume/重啟一次就新增一條 `cliSessionId` jsonl（同 cwd 目錄），詳見下方「resume vs compaction」段

### audit.jsonl 記錄類型（跨 session 比對，2026-06-13）

來源：bash 分析 RoamingClaude_cache 內 12 個 session 的 audit.jsonl，覆蓋不同模型與任務類型。

`{type, ..., _audit_timestamp, _audit_hmac}` 每筆都有 HMAC 簽章（防竄改，對應官方文章的 OTLP/稽核機制；`_audit_hmac` 僅存在於 App 層 app.asar，見 [binary.md](binary.md)）。

#### cache 內全部 12 個 session 清單（2026-06-13 補齊）

來源：bash 解析 `local_*.json` + 各 `audit.jsonl`（時間為 UTC、取 `_audit_timestamp` 起訖）。`srv` = system/init 宣告的 connected MCP server 數。

| session | model | srv | audit 行數 | 時間（UTC） | 標題 |
|---|---|---|---|---|---|
| e5075532 | sonnet-4-6 | 11 | 36 | 6/12 12:53–12:54 | Today's attention |
| 3ee25aa7 | sonnet-4-6 | 12 | 25 | 6/12 13:11 | Today's mail |
| 6a96f78a | sonnet-4-6 | 12 | 67 | 6/12 13:12–13:13 | Daily status page |
| 2d19e05b | sonnet-4-6 | 12 | 103 | 6/12 13:13–13:16 | What needs my attention |
| c821ac90 | sonnet-4-6 | 12 | 192 | 6/12 13:14–13:23 | New live artifact |
| 55e1f97c | sonnet-4-6 | 12 | 178 | 6/12 13:25–13:38 | Testing |
| 430237c8 | **fable-5** | 12 | 612 | 6/12 14:58–16:24 | Cowork research planning（本研究）|
| 65a86e22 | sonnet-4-6 | 10 | 50 | 6/10 14:57–15:00 | Connectors overview |
| d84bc41d | sonnet-4-6 | 10 | 7 | 6/10 15:17 | 1+1 |
| 724f6a0b | sonnet-4-6 | 10 | 95 | 6/10 15:18–15:51 | New file |
| db72646d | sonnet-4-6 | 10 | 13 | 6/10 15:52 | New txt file |
| a2b9c1fc | sonnet-4-6 | 10 | 110 | 6/10 15:53–16:03 | New txt file |

觀察：(1) **12 個中僅 430237c8 為 Fable 5**，其餘全 Sonnet 4.6；(2) MCP server 數 6/10 為 **10**、6/12 起增為 **11→12**（Gmail/computer-use 陸續連接），與「6/12 升級期間連接更多 connector」一致；(3) 無任一 session 使用 `Agent`（subagent）工具，只見 `TaskCreate`/`TaskUpdate`（見下方 subagent 段）。

#### 各 session 的 record 分布（4 個樣本）

| session | 模型 | 行數 | user | assistant | system | rate_limit | result |
|---|---|---|---|---|---|---|---|
| d84bc41d（「1+1」） | Sonnet 4.6 | 7 | 2 | 1 | 2 | 1 | 1 |
| 65a86e22（早期） | Sonnet 4.6 | 50 | 10 | 6 | 24 | 5 | 5 |
| c821ac90（工具密集） | Sonnet 4.6 | 192 | 28 | 35 | 120 | 5 | 4 |
| 430237c8（研究） | Fable 5 | 612 | 114 | 168 | 296 | 17 | 17 |

**規律**：`system/init` 數 = `result` 數 = `rate_limit_event` 數（每輪一組）。

#### system subtype 詳解（必然出現 vs 條件出現）

| subtype | 出現條件 | 說明 |
|---|---|---|
| `system/init` | **必然，每輪一次** | 重發完整 session 設定（工具清單、mcp_servers、model、slash_commands…） |
| `system/status` | **必然**，每次 API call 一次 | `status` 值**固定為 `"requesting"`**（跨全部 12 session、171 筆 `subtype:status` 逐一核對，無其他值，2026-06-13）；工具呼叫多的輪次出現多次（每次向 API 發請求都記錄一筆） |
| `system/thinking_tokens` | **條件**：僅 Fable 5 / 有 extended thinking 時 | `{estimated_tokens, estimated_tokens_delta}`，streaming 過程多次累計 |
| `system/permission_request` | **條件**：需使用者互動時 | 對象包括 **AskUserQuestion**（使用者需回答）和危險操作（`allow_cowork_file_delete`）——不只是 computer-use |
| `system/permission_response` | 同上（permission_request 後） | 使用者回應結果 |
| `system/model_refusal_fallback` | **條件**：Fable 5 安全機制觸發時 | ★ **自動降級機制**，見下 |
| `system/api_retry` | **條件**：API 呼叫失敗重試時 | 研究 session 出現 1 次 |

> 註（2026-06-13）：勿把 `system/status` 的固定值 `"requesting"` 與 audit 中**其他記錄**的同名 `status` 欄位混淆。後者出現在不同 context、值不同：`"connected"`（mcp_server 連接狀態，最多，579 筆）、`"allowed"`（permission 結果，51 筆）、`"completed"`/`"in_progress"`（task/結果狀態，13/14 筆）。即「`status` 這個 key 值域很廣，但 `subtype:status` 的 system record 永遠是 requesting」。

#### ★ system/model_refusal_fallback（新發現，2026-06-13）

Fable 5 有雙用途安全措施，觸發後自動降級到 Opus 4.8 重試：

```json
{
  "type": "system",
  "subtype": "model_refusal_fallback",
  "trigger": "refusal",
  "direction": "retry",
  "original_model": "claude-fable-5",
  "fallback_model": "claude-opus-4-8",
  "api_refusal_category": null,
  "api_refusal_explanation": null,
  "retracted_message_uuids": ["518d899d-..."],
  "content": "Fable 5's safety measures flagged this message for cybersecurity or biology topics...",
  "request_id": "req_011Cbydq..."
}
```

- `retracted_message_uuids`：原 Fable 5 回應被撤銷（從對話記錄移除）
- 使用者看到的是 `content` 欄位的解釋文字（說明已切換到 Opus）
- 研究 session 在分析 binary（grep 安全相關字串）時觸發 3 次（15:54、16:01、16:05）
- `api_refusal_category`/`api_refusal_explanation` 在我們的樣本中均為 null（API 未提供詳情）

#### result record 欄位（完整，來自「1+1」session）

`result` 是每輪結束的完整摘要，含計費與效能資訊：

```json
{
  "type": "result", "subtype": "success",
  "duration_ms": 8171, "duration_api_ms": 8134,
  "ttft_ms": 8083,           // Time To First Token
  "ttft_stream_ms": 8082,
  "time_to_request_ms": 36,
  "num_turns": 1,
  "result": "2",             // 最終輸出文字
  "stop_reason": "end_turn",
  "total_cost_usd": 0.0484,
  "usage": {
    "input_tokens": 3,
    "cache_creation_input_tokens": 11013,
    "cache_read_input_tokens": 23352,
    "output_tokens": 5,
    "iterations": [...],     // 本輪 API call 陣列
    "service_tier": "standard",
    "inference_geo": "not_available"
  },
  "modelUsage": {
    "claude-sonnet-4-6[1m]": { "inputTokens":3, "costUSD":0.0484, ... }
  },
  "terminal_reason": "completed",
  "fast_mode_state": "off",
  "permission_denials": []
}
```

- `num_turns`：一個 result 可涵蓋多個使用者訊息輪次（用戶快速連發時）
- `modelUsage` 按模型拆分計費；降級後會有兩個 model key
- `inference_geo: "not_available"` 暗示路由資訊有意隱藏

#### 最小 turn 的完整 7 行流程（「1+1」）

```
user          ← 使用者訊息接收（client_platform: desktop_app）
system/init   ← 本輪 session 設定重播
system/status ← API call 開始（status: "requesting"）
user(isReplay:true) ← 引擎重播使用者訊息給自己
assistant     ← 模型回應
rate_limit_event ← 速率限制檢查
result        ← 本輪完整摘要
```

`user` record 出現兩次：第一次是 App 層接收（含 `client_platform`），第二次是引擎重播（`isReplay:true`）。

重要：`system/thinking_tokens` 在 Sonnet 4.6 的「1+1」session **完全不出現**——Sonnet 4.6 不使用 extended thinking；Fable 5 session 因 `<auto_thinking>` 機制幾乎每輪都有。

### 為何 agent 看得到自己的 log（推斷）

來源：即時內省 + request_cowork_directory 拒絕訊息，2026-06-12

- 拒絕訊息明示「tool-result 檔案已可透過現有規則讀取」→ 掛載 `.claude/projects/` 的**主要目的推測是大型工具結果外部儲存的讀回通道**（同 Claude Code 機制），transcript 只是同目錄順帶可見
- 安全帳對齊：本 session 的 log 內容本就全在 agent 的 context 內，**零新資訊**；真正邊界是其他 session 的記錄（有實際資訊洩漏風險），故掛載精確切在本 session 目錄
- 唯讀＝防竄改歷史（保審計完整性）；延遲快照＝非為即時自省設計，是引擎 flush 節奏的副產品
- 結論：「自我觀察」研究法是搭 tool-results 基礎設施的便車，非刻意授予的能力

## JSONL 記錄類型（實測本 session，62 行樣本）

| type | 說明 | Claude Code 文件是否已記錄 |
|---|---|---|
| `user` | 同 Claude Code，多了 `promptId`、`promptSource`、`permissionMode`、`entrypoint` 等欄位 | 已記錄（欄位有差異） |
| `assistant` | 同 Claude Code | 已記錄 |
| `queue-operation` | 訊息佇列操作，實測 `enqueue`/`dequeue`。**binary 證實字串在引擎 binary（非 App 層）→ 是 Claude Code 引擎機制** | 未記錄 |
| `last-prompt` | 最後 prompt 摘要 `{lastPrompt, leafUuid, sessionId}`。**字串在引擎 binary** | 未記錄 |
| `attachment` | 系統附加資訊，三種子類型：`deferred_tools_delta`/`mcp_instructions_delta`/`skill_listing`。`deferred_tools_delta` 字串在引擎 binary | 未記錄 |
| `mode` | **（新發現 2026-06-13）** 記錄 session 當前模式，結構 `{type, mode, sessionId}`，實測 `mode:"normal"`（本 session 出現 23 次，疑似每輪/模式變更時寫一筆）。推測其他值含 plan 等 | 未記錄 |

註：上述三類字串均出現在**引擎 binary**（`claude-code-vm/2.1.170/claude`），代表它們是 Claude Code 引擎本身的記錄類型。**已部分驗證（2026-06-13）**：2.1.170→2.1.177 forward diff 顯示 `queue-operation`(4)/`last-prompt`(10)/`deferred_tools_delta`(11) 計數跨版本完全不變 → 確為穩定的引擎核心機制；惟「是否為 2.1.170 新增」需更舊版本（2.1.70/2.1.72）做 backward diff，仍未解（見 [binary.md](binary.md)「版本 forward diff」章節）。

### 掛載的 JSONL 非即時同步

實測（2026-06-12）：對話進行約 40 分鐘後，`.claude/projects/` 掛載中的 JSONL 仍停在第一輪期間的狀態（62 行、mtime 未變）。**掛載提供的是延遲快照，非即時串流**——機制未定（引擎緩衝 vs 同步時點），分析時注意內容可能落後目前對話。同 session 內 `toolUseResult` 實測有 dict / list / str 三種型別（Claude Code 文件僅記 dict 與 str）。

注意：`progress`、`system`、`file-history-snapshot`、`compact_boundary` 等 Claude Code 已知類型本樣本未出現（樣本太短），不代表 Cowork 沒有。`queue-operation`/`last-prompt`/`attachment` 在 2.1.177 仍存在且計數不變（forward diff 已證，見 [binary.md](binary.md)）；backward 驗證（是否 2.1.170 新增）需 2.1.70/2.1.72。

### user record 欄位（Cowork 特徵值）

```
entrypoint: "local-agent"     # Claude Code 為 "cli" 等
promptSource: "sdk"
userType: "external"
permissionMode: "default"
cwd: {session outputs 目錄的 Windows 路徑}
gitBranch: "HEAD"
version: "2.1.170"
```

### 使用者訊息的附加內容

UI 會在使用者訊息後附加系統產生的 hint，直接進入 content，例如指向視窗時的 `<cu_window_hints>`（computer-use 視窗提示）。

## session_info MCP 工具（Cowork 內建）

Cowork 提供 agent 跨 session 觀察能力（Claude Code 無對應內建工具）：

- `list_sessions`：列出本機所有 Cowork session（含標題、idle/running 狀態、cwd、`is_child` 是否為本 session 派生），預設 20 筆、最近優先
- `read_transcript`：讀取指定 session 的 transcript（**非原始 JSONL**，是整理過的 `[user]`/`[assistant]` 文字格式）；session 執行中會 block 等待（`max_wait_seconds`），`format: auto/full`

## 模型版本演進（6/12 當日升級）

來源：bash 分析多個 session 的 system/init，2026-06-13。

時間取自各 session `audit.jsonl` 的 `_audit_timestamp`（**UTC**），已逐筆核對：

| session 起訖（UTC） | model（system/init） | connected MCP servers |
|---|---|---|
| 65a86e22 6/10 14:57、d84bc41d 6/10 15:17 | `claude-sonnet-4-6[1m]` | 10（無 Gmail、無 computer-use） |
| c821ac90 6/12 13:14–13:23 | `claude-sonnet-4-6[1m]` | 12（Gmail + computer-use 已連接） |
| 430237c8 6/12 14:58–16:24（本研究） | `claude-fable-5` | 12 |

- `[1m]` 後綴推測為「100 萬 context window」變體標記
- **Fable 5 切換點收斂至 6/12 13:23–14:58 UTC 之間**（c821ac90 最後一筆 Sonnet 為 13:23、430237c8 第一筆 Fable 5 為 14:58；研究 session 從一開始即 Fable 5，故先前以「16:24」標示為該 session 末筆時間，非切換點）
- MCP server 連接狀態在 session 間可變（按使用者當時的連接配置）

## subagent / 引擎 JSONL 落點（2026-06-13 查證）

來源：bash 解析 cache 12 session + 本（live）session 掛載的 `.claude/projects`。

- **cache 內 12 個 session 無一使用 `Agent`（subagent）工具**（audit 內 tool_use 僅見 `TaskCreate`×16、`TaskUpdate`×27，無 `Agent`；亦無任何 `isSidechain:true` 記錄）→ 故「subagent 是否寫獨立 JSONL」**目前無資料可判**，需一個實際 spawn subagent 的 session 才能驗證。
- **cache 內各 session 的 `.claude/projects/` 目錄存在但為空**（0 個 jsonl）；引擎層 transcript 在這份複製中未被保留（同層另有 `.claude/sessions`、`tasks`、`backups/`、`policy-limits.json`）。→ 印證 session.md 先前所述「引擎 JSONL 是延遲快照」——複製當下尚未 flush 或已被清。
- **本 live session**：`.claude/projects/{encoded-cwd}/` 下**恰 1 個 jsonl**（即引擎每 session 寫一份 transcript），record 型別含 `user`/`assistant`/`queue-operation`/`last-prompt`/`attachment`/**`mode`**，無 `isSidechain` → 未 spawn subagent 時就是單檔、無 sidechain。
- **掛載範圍**：live `.claude` 僅 bind-mount `projects` + `skills`（ro）；**`tasks`、`sessions`、`backups` 未掛載**，VM 內看不到，需經使用者複製 cache 才能分析。

### `.claude/tasks/` = 任務清單(Progress 面板)的持久化(2026-06-14)

來源：cache 副本分析。結構 `.claude/tasks/{cliSessionId}/{taskId}.json` + `.lock`。
- 每個 task 一個 `{id}.json`，欄位 = `id/subject/description/activeForm/status/blocks/blockedBy` —— 即 `TaskCreate`/`TaskUpdate` 工具所設者。UI 右側 **Progress 面板 ↔ 這些檔**。
- **按 engine session 分**：`local_430237c8/.claude/tasks/` 下有兩個 cliSessionId 子夾(`0e8c3535`+`f98841bb`)→ 對應它 resume 過的兩個引擎 session（呼應「一對多」）。
- Windows 8.3 短檔名（如 `0E4B04~1`）= cliSessionId(`0e4b04f2...`)子夾的縮寫。

## resume vs compaction：jsonl 檔產生規則（2026-06-14 實證）

來源：使用者手動複製 `local_430237c8` 的 `.claude/projects/` 進專案後 bash 分析。該 Cowork session 的 projects 目錄下有**兩個 jsonl（同一個 cwd 目錄）**，逐一拆解得：

| jsonl（= engine sessionId） | 行數 | 時間（UTC） | 起頭 |
|---|---|---|---|
| `f98841bb...`（原始） | 506 | 6/12 14:58 → 6/13 03:25 | queue-operation |
| `0e8c3535...`（接續） | 970 | 6/13 03:29 → 6/13 13:28 | mode → 全新真實 user prompt |

**結論一：一個 Cowork session（`local_{uuid}`）可含「多條」engine sessionId jsonl —— 由 resume/重啟產生，非 compaction。**
- 兩檔同 cwd、皆 `isSidechain:0`（非 sidechain）、時間前後相接（間隔 4 分鐘）。
- 第二檔開頭是**全新真實 user 訊息**（非「continued from previous」摘要）→ 引擎被重新啟動、開新 sessionId，落同一 `projects/{cwd}` 目錄。
- 故 `local_{uuid}` ↔ `cliSessionId` 是**一對多**；jsonl 檔數 = 該 task 內引擎(重)啟動次數。**無法從 JSONL 區分「手動重開 App」與「閒置/跨日自動重啟」**（痕跡相同）。

**結論二：compaction 不產生新 jsonl，只在「同一檔內」插入 `compact_boundary`。**
- `compact_boundary` 在 f98841bb 出現 **31 次**、0e8c3535 **47 次**（散布全檔），0e8c3535 另有 `isCompactSummary`/`compactMetadata`/"This session is being continued" 續接摘要 —— **全部在檔案內部**，自始至終沒有因壓縮而分檔。
- → 回答「長 session 是否出現 compact_boundary」：**會，且大量**（這是個跨日、自動壓縮數十次的超長 session）。

**附帶修正**：先前以 audit.jsonl（612 行、停 6/12 16:24）為據，低估了此 session 長度；實際引擎 transcript 一路到 6/13 13:28，合計近 1500 行 —— audit 複製檔僅早期快照。

## 待研究

- subagent 獨立 JSONL / `isSidechain` / `is_child`：需一個**實際使用 Agent 工具**的 session 才能驗證（現有樣本皆無；已確認 430237c8 的兩檔**非** sidechain，是 resume）
- `mode` record 的其他值（plan 等）與寫入時機
- 大型 tool result 的外部儲存（tool-results/）機制是否同 Claude Code
- `queue-operation` 是否有 enqueue 以外的 operation（如 dequeue/cancel）
- `system/status` 的其他 status 值（目前只見過 `"requesting"`）
- `modelUsage` 在降級輪次的雙 key 結構（Fable 5 + Opus 4.8 拆帳）
- 大型 tool result 的外部儲存（tool-results/）機制是否同 Claude Code
- `queue-operation` 是否有 enqueue 以外的 operation（如 dequeue/cancel）
- `system/status` 的其他 status 值（目前只見過 `"requesting"`）
- `modelUsage` 在降級輪次的雙 key 結構（Fable 5 + Opus 4.8 拆帳）
