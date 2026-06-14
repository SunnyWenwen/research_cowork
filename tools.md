# Cowork 工具系統

來源：即時內省（觀察自身工具清單與 schema），2026-06-12，引擎版本 2.1.170

## 工具分類總覽

與 Claude Code 相同採 **pre-loaded / deferred** 兩層 + ToolSearch 載入機制，但工具組合差異很大。

### Pre-loaded（session 開始即有完整 schema）

| 工具 | 說明 |
|---|---|
| `Read` / `Write` / `Edit` | 同 Claude Code，但**只能存取已連接資料夾 + memory 目錄**（Windows 路徑） |
| `Glob` / `Grep` | 同 Claude Code，同樣受資料夾限制 |
| `Agent` | subagent。subagent_type：claude / claude-code-guide / Explore / general-purpose / Plan / statusline-setup；支援 `isolation: worktree`、model 覆寫（含 fable）；description 強調「不要主動 spawn」 |
| `AskUserQuestion` | 多選一/多選題 UI（Cowork 大量使用，system prompt 要求開工前先問） |
| `Skill` | 同 Claude Code 的 skill 觸發機制 |
| `ToolSearch` | 載入 deferred 工具（`select:` 精確 / 關鍵字 / `+詞` 必含） |
| `mcp__workspace__bash` | **取代 Claude Code 的 Bash**：在 sandbox VM 內執行，每次呼叫獨立（見 sandbox.md），timeout 上限 45 秒 |
| `mcp__workspace__web_fetch` | 抓網頁（有網域限制機制） |
| `mcp__cowork__present_files` | 以檔案卡片呈現給使用者；`.skill` 檔會顯示安裝按鈕 |
| `mcp__visualize__read_me` / `show_widget` | 行內視覺化 widget（SVG/HTML），有 `sendPrompt()` 回傳機制 |

注意：**沒有** Claude Code 的 `Bash`、`NotebookEdit`、`TodoWrite`（Cowork 用 TaskCreate/TaskUpdate 系列取代 todo）。

> ⚠️ **`mcp__cowork__send_user_message` 為條件性工具，非通用 pre-loaded**（修正先前記錄，2026-06-13）。證據：(a) 字串在引擎 binary `2.1.170`/`2.1.177` 計數**皆 0** → 非引擎構件，是 App 層 `cowork` MCP server 工具；(b) 比對 cache 內 **12 個 session 的 `local_*.json`**，`send_user_message` **只出現在 Fable 5 的 `spVariantPrompts['marigold']`**，base（Sonnet 4.6）systemPrompt **無一例外皆無**（`base_sup=False`）；(c) 本（非 Fable 5）session 的工具清單亦無此工具。→ 它隨 marigold（Fable 5）prompt 變體才被掛上，詳見 [prompt-schema.md](prompt-schema.md) marigold diff。<br>備註：先前推測「base prompt 已更新、Sonnet 4.6 也有」**未獲 cache 證據支持**；若曾在某 Sonnet session 觀察到，該 session 不在這份 6/12 複製的 cache 內，需取得其 `local_*.json` 才能定論。

### Deferred（需 ToolSearch 載入）

session 開始時以 `<system-reminder>` 列名稱（無 schema），對應 JSONL 中 `attachment` 記錄的 `deferred_tools_delta`。本 session 觀察到的清單分類：

- **任務清單**：`TaskCreate` / `TaskGet` / `TaskList` / `TaskStop` / `TaskUpdate`（取代 Claude Code 的 TodoWrite，UI 渲染成 widget）
- **搜尋**：`WebSearch`
- **MCP connectors（使用者連接的服務）**：如 Gmail（`mcp__{uuid}__search_threads` 等 18 個）— **server 名稱是 uuid**，非語意名稱
- **Claude in Chrome**：`mcp__Claude_in_Chrome__*`（navigate、get_page_text、computer 等 ~20 個）
- **computer-use**：`mcp__computer-use__*`（screenshot、click、type、request_access 等 ~30 個；有 read/click/full 三層 app tier 權限）
- **Cowork 平台功能**：`mcp__cowork__create_artifact` / `update_artifact` / `list_artifacts` / `request_cowork_directory` / `allow_cowork_file_delete` / `read_widget_context`
- **MCP registry**：`mcp__mcp-registry__search_mcp_registry` / `suggest_connectors` / `list_connectors`（動態建議使用者安裝 connector）
- **plugins / skills 管理**：`mcp__plugins__*`、`mcp__skills__list_skills` / `suggest_skills`
- **排程**：`mcp__scheduled-tasks__create/update/list_scheduled_task(s)`
- **session 觀察**：`mcp__session_info__list_sessions` / `read_transcript`（見 session.md）

### ToolSearch 行為（實測）

- 載入前直接呼叫 deferred 工具會 `InputValidationError`
- `select:A,B,C` 一次載入多個；回傳格式為 `<functions>` 區塊內的 JSONSchema（與 system prompt 開頭工具清單同編碼）
- MCP server 指示（如 computer-use 的使用說明）隨 system prompt 提供，建議「整組載入」（關鍵字匹配 server 名稱子字串）

## Skill 系統

- 機制同 Claude Code（SKILL.md、Skill 工具觸發），但 skill 檔案掛載為**唯讀快取**：session 內不可建立/修改 skill，需到 Settings > Capabilities
- 路徑：Windows `AppData\Roaming\Claude\local-agent-mode-sessions\skills-plugin\...`；VM 內 `/sessions/{name}/mnt/.claude/skills/`（ro）
- 內建 skill：docx / pdf / pptx / xlsx / schedule / setup-cowork / skill-creator / session 相關 + plugin 提供的 skill（`cowork-plugin-management:*`）
- system prompt 強制規範「先研究、後讀 output-format skill」的順序（防止先被文件格式 anchoring）

## MCP 架構觀察

- Cowork 把平台功能本身也做成 MCP server：`cowork`、`workspace`、`visualize`、`session_info`、`scheduled-tasks`、`mcp-registry`、`plugins`、`skills`、`computer-use` 等，與外部 connector（Gmail 等）同一機制
- 外部 connector 的 server 名稱用 uuid（如 `mcp__5f1729b4-...__search_threads`），平台內建 server 用語意名稱 — 可作為區分特徵
- system prompt 指示 agent 主動查 registry 並建議 connector（`search_mcp_registry` → `suggest_connectors`），這是 Claude Code 沒有的「工具自我擴充」流程

## ★ 權威清單（binary 層，audit.jsonl 的 system/init）

來源：`audit.jsonl` 每輪重發的 `system/init` record，2026-06-12。這是引擎啟動時的完整宣告。

**12 個 MCP server**（全 connected）：`5f1729b4-...`（Gmail，uuid 命名）、`Claude in Chrome`、`computer-use`、`cowork`、`cowork-onboarding`、`mcp-registry`、`plugins`、`scheduled-tasks`、`session_info`、`skills`、`visualize`、`workspace`。
→ 比第一輪內省多抓到 **`cowork-onboarding`**（含 `show_onboarding_role_picker`）。

**6 種 agent**：claude、claude-code-guide、Explore、general-purpose、Plan、statusline-setup。

**slash_commands（24 個，含 UI 未明列的隱藏指令）**：`clear`、`compact`、`context`、`heapdump`、`init`、`reload-skills`、`review`、`security-review`、`usage`、`insights`、`goal`、`team-onboarding`，加上 plugin/skill 提供的（`anthropic-skills:*`、`cowork-plugin-management:*`）。
→ `heapdump`、`insights`、`goal`、`team-onboarding`、`usage`、`context` 等為內省未見的內建指令。

其他 init 欄位：`model: claude-fable-5`、`apiKeySource: none`、`output_style: default`、`memory_paths.auto`、`plugins[]`（附 inline 路徑）、`fast_mode_state: off`。

## 與 Claude Code 工具系統差異總表

| 面向 | Claude Code | Cowork |
|---|---|---|
| Shell | 本機 Bash，session 延續 | VM 內 bash，每次獨立，45s 上限 |
| 檔案存取 | 專案目錄 | 僅已連接資料夾（其他路徑被拒） |
| Todo | TodoWrite | TaskCreate/TaskUpdate（widget 渲染） |
| 瀏覽器 | 無內建 | Claude in Chrome MCP |
| 桌面控制 | 無 | computer-use MCP（tier 權限） |
| 工具擴充 | 手動設定 MCP | registry 搜尋 + 主動建議 |
| 視覺輸出 | 無 | visualize widget、Artifacts |
| UI 互動 | 無 | AskUserQuestion 強制前置、present_files |

## ★ MCP 協議層（directMcpHost.js，2026-06-13）

來源：`asar_extracted/.vite/build/mcp-runtime/directMcpHost.js`（571KB）；App 版本 1.11847.5.0。

Cowork 的 MCP client 實作位於獨立的 `directMcpHost.js` bundle，與主 `index.js` 分開打包。

**協議版本**：

```javascript
LATEST_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05", "2024-10-07"]
```

向後相容 5 個版本（最舊支援 `2024-10-07`）。

**傳輸層**：`StreamableHTTPClientTransport`（相對於傳統 stdio 或 SSE）——支援流式 HTTP 回應，是 MCP 2025-11-25 的新傳輸機制。

**進階功能（client-side capabilities）**：

| 功能 | 說明 |
|---|---|
| **Sampling** | MCP server 可向 LLM 請求補全（`sampling.createMessage`）—— server-initiated LLM call |
| **Elicitation** | MCP server 可向使用者請求輸入（`elicitation.create`）—— server-initiated user prompt |
| **OAuth** | 完整 OAuth 2.0 保護資源流程（`OAuthProtectedResourceMetadataSchema`）；需使用者開啟 URL 時拋出 `UrlElicitationRequired`（錯誤碼 `-32042`） |

**關鍵推論**：Cowork connector MCP server（如 Gmail）理論上可利用 sampling 直接觸發 LLM 補全，或用 elicitation 要求使用者輸入，無需 agent 主動呼叫——這是 MCP 2025-11-25 協議的新能力。

**與 Claude Code 的關係**：引擎層（2.1.170 ELF）也含有 MCP 相關字串，但 `directMcpHost.js` 是 App 層的 MCP client（負責連接外部 connector server）；引擎的 MCP 機制處理 sub-agent 工具呼叫路由。兩層各有 MCP 實作。

## 待研究

- Hooks 是否存在於 Cowork（Claude Code 有 21 種事件）
- 權限系統：permission_request IPC 是否同 Claude Code；computer-use 的 tier 強制機制
- `web_fetch` 與 `WebSearch` 的網域限制實作
- Artifacts 的 `window.cowork.*` API（callMcpTool / askClaude / runScheduledTask）細節 → features.md
- MCP sampling/elicitation 在實際 connector 使用中的觀察記錄
