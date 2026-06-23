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

**參數（pre-loaded schema，即時內省 2026-06-15）**——只有兩個：

- `query`（必填 string）。三種寫法：
  - `select:Read,Edit,Grep` — 用**確切工具名**直接抓（逗號分隔多個），最精準
  - `notebook jupyter` — **關鍵字**搜尋，回最相符前 N 個
  - `+slack send` — `+詞` 表示**名稱必含** "slack"，其餘詞排序
- `max_results`（選填 number，預設 5）— 最多回幾個工具的 schema

**回傳**：`<functions>` 區塊內的 JSONSchema（與 system prompt 開頭工具清單同編碼）；schema 一出現在結果裡該工具即可呼叫。

**可一次載一大批（實測確認）**：`select:` 可帶長串名稱；或關鍵字配大的 `max_results`（如 `query:"computer-use", max_results:30`，因關鍵字比對工具名/server 名子字串，一發即整組 ~27 個 schema 全入）。system prompt 明確建議 computer-use / Claude in Chrome 這類「整組載入，別逐個 select」。**取捨**：每個 schema 進來都佔 context token，會抵消 deferred 省 token 的初衷；確定要用的整組一次載 OK，不確定的別預先全灌。

### ★ deferred 工具的「名稱」與「schema」走不同通道（2026-06-15 實測，本 session JSONL）

問題起點：使用者問「schema 是用 tool result 放進 context，還是其他方式？」→ 查本 session JSONL `attachment` 記錄定論：

| 內容 | 傳遞通道 | 證據 |
|---|---|---|
| 工具**名稱** | `attachment` 記錄的 `deferred_tools_delta`（`addedNames`/`addedLines`，本 session 89 筆，**只有名字無 schema**）→ 渲染成開場的 `<system-reminder>` deferred 清單 | JSONL attachment record |
| 工具**完整 schema** | **ToolSearch 的 tool result**（`<functions>` 區塊），以 tool_result 形式留在對話 context | 本 session 載 `select:TaskCreate,TaskUpdate` 收到 |

- 同一批 `attachment` 還用 delta 灌入：`agent_listing_delta`（6 種 agent）、`mcp_instructions_delta`（computer-use 使用說明 4863 字元）、`skill_listing`（53 個 skill 描述 25451 字元）。→ Cowork **開場大量「清單/說明」都靠 attachment delta 注入 context**，非寫死在 system prompt。
- **關鍵分辨**：context 裡有沒有 schema，只影響「**模型**能否正確帶參數」，不影響「引擎**能否執行**」——真正的工具註冊與參數驗證在引擎/MCP host 端（握有所有已連接工具真實 schema）。故無參數的 deferred 工具，不載 schema 也能直接呼叫成功（見上方 deferred≠不可呼叫的更正）。
- 一句話：**名稱走 attachment delta（system-reminder），schema 走 ToolSearch tool result**；兩者都只是「給模型看的副本」，執行端權威 schema 一直在引擎那邊。

#### ★ 底層是 Anthropic API 原生 beta「tool-search-tool」（2026-06-15 binary 驗證，升級先前推論）

問題起點：使用者問「打 Claude API 時 payload 到底怎麼帶 tools？session log 有嗎？」

**先確認 session log 無法驗證**：引擎 JSONL **不記 API request payload**——全檔搜 `"tools"`/`"tool_choice"`/`"input_schema"`/`"system"`/`"max_tokens"` **零命中**；只記回應側（assistant message、`usage`、`requestId`）。`usage.cache_creation_input_tokens`(~33k) 間接證明有被快取的 prompt 前綴（工具定義在內），但看不到內容。live 請求亦攔不到（MITM proxy 只放行本 VM token）。

**改用引擎 binary（2.1.170 字串）驗證，得到權威協議**：ToolSearch **是 Anthropic API 原生 beta，不是 harness 模擬**。

| 證據字串 | 意義 |
|---|---|
| `tool-search-tool-2025-10-19`（與 `advanced-tool-use-2025-11-20` 相鄰） | **anthropic-beta header 名**；請求帶此 beta 才啟用 |
| `tool_reference`（content block type） | **deferred 工具以「輕量參照」帶進請求**，非把完整 schema inline 進 `tools` |
| `tool_search_tool_result`（與 `mcp_tool_result`/`bash_code_execution_tool_result` 同類） | 模型呼叫 tool-search 後，API **回一個夾帶完整 schema 的 result content block** |
| `total_deferred_tools`、`getAutoToolSearchCharThreshold`、`ENABLE_TOOL_SEARCH=auto:N`（`gIq` 解析 `auto:` 前綴取字元閾值） | deferred 數計量 + 自動啟用門檻（工具定義字元數超過 N 才開） |
| `[ToolSearch:optimistic] disabled: ANTHROPIC_BASE_URL ... not a first-party Anthropic host` / `Vertex AI does not accept the tool-search beta header` | **限第一方 host**；非第一方或 Vertex 即停用 → 證明是真 API 端 beta |

**修正先前推論**：本檔上方「機制（推論，非實測）：harness 把 schema 加進 API `tools` 參數」**不夠準確**。真實機制是 API 層協議——deferred 工具以 `tool_reference` 攜帶、schema 經 tool-search round-trip 以 `tool_search_tool_result` 回傳，由 `tool-search-tool-2025-10-19` beta 啟用。先前「無參數 deferred 工具不載也能呼叫」的觀察仍相容：引擎/API 端握有所有 `tool_reference` 對應的真實 schema，呼叫只要參數合法即可路由。

**對照 OpenAI `tools=`**：OpenAI 把所有 schema inline 進 `tools`，是唯一來源；Claude tool-search beta 則可大量註冊工具但多數以 `tool_reference`（名稱/指標）帶入，模型按需拉 schema（回 `tool_search_tool_result`）——把「schema 隨選載入」做進 API 協議，省 token。

##### `tools` vs `tool_reference`：不同層、並存（2026-06-15 binary 驗證）

問題起點：使用者問「`tool_reference` 跟 `tools` 不一樣？Claude 兩個都存在？」→ 是，不同東西、同一請求並存。

| | `tools`（請求頂層參數） | `tool_reference`（content block） |
|---|---|---|
| 位置 | request 頂層 `tools` 陣列 | **訊息 content 內的區塊** |
| 結構 | 完整定義：name + description + `input_schema` | `{ type:"tool_reference", tool_name:K }`（**只有工具名**） |
| 角色 | 放「目前已啟用」工具的完整 schema | 指向「存在但 schema 未載入」的 deferred 工具 |

binary 證據：`isToolReferenceBlock`、`H.type==="tool_reference"`、構造式 `H.matches.map(K=>({type:"tool_reference",tool_name:K}))`；模型限定字串 `model does not support tool_reference blocks. This feature is only available on Claude Sonnet 4+, Opus 4+, and newer models.`；`Filtering out tool_reference for unavailable tool`；compaction 註解（`tool_reference`-carrying messages 被摘要後另存 deferred 名以維持 schema filter）。

運作：pre-loaded → 完整 schema 在 `tools`；deferred → 先以 `tool_reference` 區塊（僅名字）存在，經 ToolSearch 搜到後 schema 由 `tool_search_tool_result` 回傳、引擎 schema filter 才把完整定義納進後續 `tools`。故 `tool_reference` 不取代 `tools`，是 tool-search beta 額外的「輕量目錄層」，兩者並存（呼應「名字走一條通道、schema 走另一條」）。模型需 Sonnet 4+/Opus 4+ 才支援。

##### 校準：tool-search 是「server 認得的協議 + client 大量編排」的混合，非純 server tool（2026-06-15）

問題起點：使用者問「tool search 其實是 server side 的工具？」→ 部分對，但**先前把它等同 web_search/code_execution「伺服器託管工具」是過度宣稱**，校準如下。

- **server 端確實參與（已驗證）**：beta header 須 server 認得、專屬 `tool_search_tool_result` block、**限第一方 host**（Vertex 不收此 beta header、非第一方 proxy 需轉發 `tool_reference` blocks）→ 請求要送到 Anthropic server 且由其處理。
- **但非純 server-side 執行（校準）**：binary 有大量 **client/引擎側邏輯**——`getDeferredToolsDelta`、`clearToolSearchDescriptionCache`、`formatDeferredToolLine`、`findDeferredToolMarkerInTranscript`、`matches.map` 建 `tool_reference`、compaction 後重建 deferred 名單的 schema filter。與 `web_search`/`code_execution`（全程 server 跑、client 不執行）不同。`tool_search_tool_result` 雖與 `mcp_tool_result`(client 執行)/`bash_code_execution_tool_result`(server 執行) 並列，但該群本身混合，無法據此斷定純 server。
- **無法從字串斷定（標為未解）**：實際「query→比對出哪些工具」計算跑在 server 或 client。有 client matching 跡象，server 亦參與；硬下定論即推論。
- **結論**：tool-search ≈ **API 協議層 beta（server 認得）+ 引擎端編排** 的混合工具，不宜簡化為「純 server tool」。先前在本檔/對話把它與 web_search 並列為「server/managed tool」**據此更正**。

##### ★★ 官方文件校正（2026-06-15，來源：platform.claude.com `tool-search-tool`，權威）

使用者提供官方文件 URL → 讀後**更正上方兩處 binary 推論**，並補齊機制。

**更正 A：deferred 工具的完整 schema 一直在 `tools` 參數裡（推翻上方 `tools` vs `tool_reference` 表的「tools 只放已啟用」說法）**
- 官方機制：**所有**工具（含 deferred）都放在 request 的 `tools` 參數，deferred 者加旗標 **`defer_loading: true`**（這才是「標記為 deferred」的真正 API 手段）。
- 被藏起來的是 **system-prompt prefix**（模型實際 attend 的那份），**不是 `tools` 參數**。原文：「Deferred tools are not included in the system-prompt prefix. When the model discovers a deferred tool through tool search, the API appends a `tool_reference` block inline in the conversation, then expands it into the full tool definition... The prefix is untouched, so prompt caching is preserved.」
- 故完整 schema 始終在 `tools`（API 要用它自動展開 `tool_reference`、strict-mode grammar 也由完整 toolset 建）。**原本「搜到才把 schema 納入 tools」的描述錯誤——應為「搜到才放進模型可見的 prefix；tools 參數自始即全有」。**
- 至少要有一個工具**非** deferred（否則 400 `All tools have defer_loading set`）；建議把最常用 3–5 個設非 deferred；tool-search 工具本身**絕不可** `defer_loading`。

**更正 B：built-in tool search 確實是 server-side 工具（推翻上方「非純 server / 混合」的過度校準）**
- 原文：「Although this is provided as a **server-side tool**, you can also implement your own **client-side tool search** functionality.」→ built-in 本體 = server-side。
- 兩個 server 變體：**regex** `tool_search_tool_regex_20251119`（Claude 寫 Python `re.search` 패턴，≤200 字）、**BM25** `tool_search_tool_bm25_20251119`（自然語言）。
- **client-side 自訂版**也支援：自寫搜尋工具、回標準 `tool_result` 夾 `tool_reference` blocks（每個 referenced 工具須在 `tools` 有對應 `defer_loading:true` 定義）。
- 這解釋了 binary 同時有 server 路徑（beta header、host gating、`tool_search_tool_result`）與 client 路徑（`matches.map(K=>({type:"tool_reference",tool_name:K}))`）＋`[ToolSearch:optimistic]`：**第一方 host 走 server-side，否則 fallback client-side**。故「混合」指「引擎兩條路徑都備」，但 built-in 搜尋本體是 server-side——更正先前「不宜稱純 server」的措辭。

**回應格式（官方）**：`server_tool_use`（Claude 呼叫搜尋工具）→ `tool_search_tool_result`（內含 `tool_search_tool_search_result.tool_references[]`，每個 `{type:"tool_reference",tool_name}`）→ API 自動展開為完整定義 → `tool_use` 呼叫該工具。用量記 `server_tool_use.tool_search_requests`。

**版本/模型差（binary vs 官方）**：本專案 grep 的引擎 2.1.170 用**較舊** `tool-search-tool-2025-10-19`（單一 beta）；現行官方已是 `*_20251119` 且分 regex/BM25 兩變體。模型支援官方列 **Fable 5、Mythos 5、Mythos Preview、Sonnet 4.0+、Opus 4.0+、Haiku 4.5+**（binary 字串僅見 Sonnet4+/Opus4+）。catalog 上限 1 萬、每搜回 3–5、ZDR 適用。

### 「目前已載入哪些 schema」沒有可查詢的登記處（2026-06-15 實測）

問題起點：使用者問「你怎麼知道當前已載入哪些 tool 的 schema？有額外的地方紀錄嗎？」

- **模型側：無登記處、無計數器、無 `list_loaded_tools`**。模型判斷「已載入哪些 schema」唯一依據是**掃自己的 context**：(a) prompt 最上方 pre-loaded 函式區塊 + (b) 本對話內每次 ToolSearch 回傳且仍在 context 的 `<functions>` 區塊。若某 ToolSearch 結果因 compaction 被擠出 context，模型即「失憶」，須重新 ToolSearch。
- **引擎側：有紀錄，但記的是「可搜尋的 deferred 名單」，非「已載入 schema」**。本 session JSONL 僅開場 1 筆 `deferred_tools_delta`（added 89 / removed 0），欄位 `addedNames / addedLines / removedNames / readdedNames / pendingMcpServers`——**無任何「已載入 schema 計數/清單」欄位**。`removedNames`/`readdedNames` 的存在證明此名單是**會變動的執行期狀態**（如對話中途 plugin 的 `authenticate` 工具，係 MCP server 陸續連上後才新增進名單）。
- **結論**：「已載入 schema」狀態**只存在於模型 context**（暫時、以 tool_result 文字存在），無權威外部帳本；引擎 JSONL 記的是 deferred **名單**增減，不是 schema 載入狀態。實務：不確定某 schema 在不在，**直接再 ToolSearch 一次最保險**（冪等，重新回 schema）。

## Skill 系統

- 機制同 Claude Code（SKILL.md、Skill 工具觸發），但 skill 檔案掛載為**唯讀快取**：session 內不可建立/修改 skill，需到 Settings > Capabilities
- 路徑：Windows `AppData\Roaming\Claude\local-agent-mode-sessions\skills-plugin\...`；VM 內 `/sessions/{name}/mnt/.claude/skills/`（ro）
- 內建 skill：docx / pdf / pptx / xlsx / schedule / setup-cowork / skill-creator / session 相關 + plugin 提供的 skill（`cowork-plugin-management:*`）
- system prompt 強制規範「先研究、後讀 output-format skill」的順序（防止先被文件格式 anchoring）
- **Skill 來源僅「全域/帳號層」三種，無資料夾 local（2026-06-14 實測）**：(1) 內建快取、(2) 安裝的 plugin、(3) Settings > Capabilities 的 user skill。實測把 `SKILL.md` 丟進連接資料夾 `research_cowork/.claude/skills/` 與引擎 cwd `outputs/.claude/skills/`，`/reload-skills` 後**皆不出現** → **Claude Code 的「專案 `cwd/.claude/skills/` = project-local skill」機制，Cowork 未開放**。
  - **安全理由**：連接資料夾/scratch 可能含不受信任的使用者檔；若自動載入其中的 SKILL.md，等於任何資料夾都能注入「會自動觸發的能力」（prompt-injection / 自我提權破口）。故 Cowork 只認經核准/安裝的來源——與「agent 不能自我裝 plugin/connector/skill」同一道防線。
- **skill global/local 對照**：Cowork = 全部 global（帳號層，跨所有 Project/session）；Claude Code = 另有 project-local（`cwd/.claude/skills`）與 personal（`~/.claude/skills`）。

## MCP 架構觀察

- Cowork 把平台功能本身也做成 MCP server：`cowork`、`workspace`、`visualize`、`session_info`、`scheduled-tasks`、`mcp-registry`、`plugins`、`skills`、`computer-use` 等，與外部 connector（Gmail 等）同一機制
- system prompt 指示 agent 主動查 registry 並建議 connector（`search_mcp_registry` → `suggest_connectors`），這是 Claude Code 沒有的「工具自我擴充」流程

### MCP server 三種來源 / 命名慣例（2026-06-15 補：新增第三種）

| 來源 | server 名稱範例 | tool 名稱前綴 | 觀察 |
|---|---|---|---|
| **平台內建** | `cowork`、`workspace`、`visualize`、`session_info`、`scheduled-tasks`、`mcp-registry`、`plugins`、`skills`、`computer-use`、`cowork-onboarding`、`Claude in Chrome` | `mcp__cowork__*` 等語意名 | Cowork 平台功能本身，每個 session 必有 |
| **使用者連接的 connector** | uuid，如 `a8d37d66-a993-4cd6-badf-76497f1ae1c3`（Notion）、`5f1729b4-...`（Gmail，6/12 session） | `mcp__{uuid}__*` | 使用者在 Settings 連接的外部服務，server 名是 uuid（非語意名）；**每個 session 視帳號連了什麼而不同** |
| **plugin 內建（NEW）** | `plugin:engineering:slack`、`plugin:engineering:github`、`plugin:finance:bigquery` … | `mcp__plugin_engineering_slack__*`（`:` → `_`） | 安裝的 **plugin 隨附**的 MCP server；命名帶 `plugin:{plugin}:{server}` 前綴 |

→ 三種可由名稱一眼區分：**語意名 = 平台**、**純 uuid = 使用者 connector**、**`plugin:` 前綴 = plugin 隨附**。

#### ★ 使用者自己的 MCP server 一律 deferred，永不 pre-loaded（2026-06-23 即時內省，Opus 4.8）

問題起點：使用者問「自己的 MCP server 載入 Cowork 時會是 deferred 嗎？」

**結論：會，必定 deferred。** 使用者 connector（uuid 命名）與 plugin-bundled（`plugin:` 前綴）的工具**都只走 deferred 通道，從不進 pre-loaded**。pre-loaded 名額僅留給平台高頻內建工具（引擎原生 + `workspace__bash`/`web_fetch`/`cowork__present_files`/`visualize`，見 §A 權威清單）——第三方工具排不進去。

機制（與 §「名稱走 attachment delta、schema 走 ToolSearch」一致）：
1. 開場 `<system-reminder>` deferred 名單**只列工具名、無 schema**；外接 server 常先標 **"still connecting"**，連上後再經 JSONL `deferred_tools_delta`（`addedNames`，`pendingMcpServers` 欄位）陸續補入 → 證明 deferred 名單是**會變動的執行期狀態**，外接 server 是「事後加入」而非開場寫死。
2. 要用得先 `ToolSearch` 載 schema（對**有必填參數**的工具是必須；無參數工具沿用「deferred≠不可呼叫」可直接叫，見 §更正）。
3. OAuth 類 connector 連上後常先露 `authenticate`/`complete_authentication` 一對工具。

**即時證據（本 session）**：`github` MCP server 即以此模式載入——開場 system-reminder 先報「still connecting」，隨後一次補進 **55 個 `mcp__github__*` 工具，僅名稱無 schema**，呼叫前須 ToolSearch。為「使用者自己的 MCP server = deferred」的活樣本。

### Plugin 內建 MCP server（2026-06-15 即時內省）

本 session 安裝了 `engineering` 與 `finance` 兩個 plugin，各自 **bundle 了一組 MCP server**：

- **`engineering` plugin**：`asana`、`atlassian`、`datadog`、`github`、`linear`、`notion`、`pagerduty`、`slack`（8 個）
- **`finance` plugin**：`bigquery`（1 個）

機制觀察：

- **延遲連接**：session 開頭這些 server 標為「still connecting」，其 `mcp__plugin_*__*` 工具尚未就緒；system-reminder 指示「即使使用者沒點名，若請求可能用到就用關鍵字呼叫 ToolSearch，它會等待 connecting server 連上再搜」。
- **OAuth 流程工具**：連上後先露出的是 `authenticate` / `complete_authentication` 一對工具（如 `mcp__plugin_engineering_slack__authenticate`），即需使用者授權的 connector 採 MCP elicitation/OAuth 流程（呼應 directMcpHost 的 `UrlElicitationRequired`）。
- **plugin ≠ 一定帶 MCP server**：同 session 也裝了 `brightdata-plugin`（純 skill，無 MCP server）、`cowork-plugin-management`、`cowork-session-analyze`、`anthropic-skills`（提供 docx/pdf/pptx/xlsx/schedule/skill-creator 等 skill）。即 plugin 可只帶 skill、只帶 MCP server、或兩者皆有。
- 對照 6/12 的「12 個 MCP server」權威清單：本 session 在平台內建 + connector 之外，**又多出 9 個 plugin-bundled server**，總數明顯更多。可見 MCP server 清單**高度依 session 當下的帳號 plugin/connector 設定**而變。

### `mcp__` 前綴 ≈ 「Cowork 平台工具（App 層）vs 引擎原生」的分界（2026-06-15）

問題起點：使用者問「包成 MCP server 的內建工具是不是大多是 Cowork 的，而非原生引擎（Claude Code）工具？」→ 是，且有結構性原因。

| 類別 | 判別 | 工具 |
|---|---|---|
| **引擎原生**（與 Claude Code 共用） | **無** `mcp__` 前綴 | `Read`/`Write`/`Edit`/`Glob`/`Grep`/`Agent`/`AskUserQuestion`/`Skill`/`ToolSearch`/`TaskCreate/Get/List/Stop/Update`/`WebSearch` |
| **Cowork 平台工具**（App 層，包成 MCP server） | **有** `mcp__` 前綴 | `cowork`/`visualize`/`session_info`/`scheduled-tasks`/`mcp-registry`/`plugins`/`skills`/`cowork-onboarding`/`computer-use`/`Claude in Chrome`/`workspace` |

**深層原因**：這批之所以非得包成 MCP server，是因為它們要碰**引擎（尤其沙盒內）碰不到的東西**——GUI 渲染（artifact/widget/present_files）、OS/桌面（computer-use）、瀏覽器擴充（Claude in Chrome）、跨 session 檔案（session_info）、host 排程（scheduled-tasks）、connector 註冊（mcp-registry）。Cowork 用「平台功能即 MCP server」把 **host/GUI 側能力暴露給引擎**，故「被包成 MCP」與「Cowork 專屬、非引擎原生」高度相關。對照 Claude Code：`mcp__` 前綴專留給使用者外接的 MCP server，原生工具（Bash/Read…）無前綴——Cowork 拿同機制來掛**平台自身**功能，是 Cowork 的設計選擇。

**兩個但書**：
1. `mcp__workspace__bash`/`web_fetch` 是「核心能力被 MCP 橋接」的特例：Shell/抓網頁在 Claude Code 是**引擎原生**（`Bash`/`WebFetch`，無前綴），Cowork 改成 MCP 是為了跨進隔離 VM 執行 → 「被包成 MCP」≠「非核心能力」。
2. App/引擎界線**隨版本漂移**：`ArtifactTool`/`ProjectsTool` 在 2.1.177 下沉進引擎（170 仍 App 層，見 binary.md）→ 此前綴分界是「當前版本快照」，非永久歸屬。

### 跨 session 環境差異（提醒：清單會變）

| 面向 | 6/12 記錄 | 本 session（6/15） |
|---|---|---|
| 模型 | Sonnet 4.6 → Fable 5 | **Opus 4.8**（`claude-opus-4-8`） |
| 使用者 connector | Gmail（`5f1729b4-…`） | Notion（`a8d37d66-…`） |
| plugin-bundled server | （未觀察到） | engineering ×8 + finance ×1 |

→ 結論：tools.md 的「權威清單」是**某一 session 的快照**，工具/server 組合會隨模型、已連 connector、已裝 plugin 變動；驗證機制時應同時記錄觀察日期與當時的模型/plugin 狀態。

## ★ 權威清單（binary 層，audit.jsonl 的 system/init）

來源：`audit.jsonl` 每輪重發的 `system/init` record，2026-06-12。這是引擎啟動時的完整宣告。

**12 個 MCP server**（全 connected）：`5f1729b4-...`（Gmail，uuid 命名）、`Claude in Chrome`、`computer-use`、`cowork`、`cowork-onboarding`、`mcp-registry`、`plugins`、`scheduled-tasks`、`session_info`、`skills`、`visualize`、`workspace`。
→ 比第一輪內省多抓到 **`cowork-onboarding`**（含 `show_onboarding_role_picker`）。

**6 種 agent**：claude、claude-code-guide、Explore、general-purpose、Plan、statusline-setup。

**slash_commands（24 個，含 UI 未明列的隱藏指令）**：`clear`、`compact`、`context`、`heapdump`、`init`、`reload-skills`、`review`、`security-review`、`usage`、`insights`、`goal`、`team-onboarding`，加上 plugin/skill 提供的（`anthropic-skills:*`、`cowork-plugin-management:*`）。
→ `heapdump`、`insights`、`goal`、`team-onboarding`、`usage`、`context` 等為內省未見的內建指令。

其他 init 欄位：`model: claude-fable-5`、`apiKeySource: none`、`output_style: default`、`memory_paths.auto`、`plugins[]`（附 inline 路徑）、`fast_mode_state: off`。

## `/` slash 輸入行為（2026-06-14，使用者實測）

- 可用指令集 = session 的 `slashCommands` 陣列（`system/init` 下發的完整 24 個）+ 內建動作(`add-files`/`export`)；GUI 下拉底部「Type to filter」→ 是**可過濾視圖**，預設只露 6 項，非白名單。
- **嚴格 exact-match 驗證**：打不存在/近似的指令（實測 `/contextd`、`/context.`）→ 跳 **「Unknown skill: X」並把訊息卡掉（不送出、不當文字發出）**。修正先前「沒匹配就當文字送」的錯誤推測。
- 推論（未完全實測）：有註冊但沒列在預設視圖的指令，打全名應可過濾出並執行；待以 `/usage` 等已註冊全名驗證。
- 對照 Claude Code：引擎 slash 機制共用（`clear`/`compact`/`context`/`init`/`review` 等重疊），但 Cowork 為 GUI 可過濾下拉 + 混入桌面動作/skill + exact-match 卡訊息；Claude Code 為 CLI 文字自動完成。

## 工具兩大類：渲染 UI vs 做事/取資料（2026-06-14）

Cowork 工具的一個明顯特徵：**一大類工具的「輸出」就是在對話渲染 UI 元件**（呼叫=畫卡片/widget），而非回傳資料。

- **渲染型（agent→GUI 的繪圖指令）**：`present_files`(檔案卡)、`show_widget`(SVG/HTML)、`AskUserQuestion`(選擇題)、`list_skills`/`suggest_skills`、`list_connectors`/`suggest_connectors`、`list_plugins`/`suggest_plugin_install`、`create_artifact`/`update_artifact`、`show_onboarding_role_picker`、`TaskCreate`/`TaskUpdate`(驅動 Progress widget)。呼叫後 agent 收到的是 JSON 摘要，使用者看到的是 App renderer 畫的原生元件。
- **做事/取資料型**：`bash`、`web_fetch`、`WebSearch`、`Read`/`Write`/`Edit`/`Glob`/`Grep`、`scheduled-tasks`、`session_info`、`Agent`、`ToolSearch`、`Skill`。
- **中間地帶**：`request_cowork_directory`/`allow_cowork_file_delete`(觸發原生對話框)、`read_widget_context`(反向**讀** UI 狀態)。

→ 渲染型工具幾乎都是 **Cowork 專屬**（Claude Code 為 CLI、輸出以文字為主）。本質上 Cowork 把「渲染某 UI 元件」也包裝成 MCP 工具，呼應「平台功能即 MCP server」：其中很大一部分 server 的職責就是把 GUI 渲染能力暴露給 agent。

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

## ★ 平台內建工具完整清單（即時內省，2026-06-15，Opus 4.8）

範圍：**僅平台內建**——含 pre-loaded、deferred、及平台內建 MCP server 的所有 tool。**不含**使用者 connector（Notion uuid）與 plugin-bundled server（`plugin:*`）的 tool。

### A. Pre-loaded（14，session 開場即有完整 schema）

非 MCP（引擎原生 6）：`Agent`、`AskUserQuestion`、`Edit`、`Glob`、`Grep`、`Read`、`Skill`、`ToolSearch`、`Write`（按字母 9 個）。
平台 MCP（5）：`mcp__cowork__present_files`、`mcp__visualize__read_me`、`mcp__visualize__show_widget`、`mcp__workspace__bash`、`mcp__workspace__web_fetch`。

### B. Deferred — 非 MCP 引擎工具（6）

`TaskCreate`、`TaskGet`、`TaskList`、`TaskStop`、`TaskUpdate`、`WebSearch`。

### C. Deferred — 平台內建 MCP server 及其 tool

| server | tool（`mcp__{server}__` 前綴省略） | 數 |
|---|---|---|
| `workspace` | `bash`、`web_fetch`（皆 pre-loaded） | 2 |
| `cowork` | `present_files`(pre-loaded)、`create_artifact`、`update_artifact`、`list_artifacts`、`request_cowork_directory`、`allow_cowork_file_delete`、`read_widget_context` | 7 |
| `visualize` | `read_me`、`show_widget`（皆 pre-loaded） | 2 |
| `session_info` | `list_sessions`、`read_transcript` | 2 |
| `scheduled-tasks` | `create_scheduled_task`、`list_scheduled_tasks`、`update_scheduled_task` | 3 |
| `mcp-registry` | `list_connectors`、`search_mcp_registry`、`suggest_connectors` | 3 |
| `plugins` | `list_plugins`、`search_plugins`、`suggest_plugin_install` | 3 |
| `skills` | `list_skills`、`suggest_skills` | 2 |
| `cowork-onboarding` | `show_onboarding_role_picker` | 1 |
| `computer-use` | `screenshot`、`cursor_position`、`mouse_move`、`left_click`、`right_click`、`middle_click`、`double_click`、`triple_click`、`left_click_drag`、`left_mouse_down`、`left_mouse_up`、`scroll`、`key`、`hold_key`、`type`、`wait`、`zoom`、`read_clipboard`、`write_clipboard`、`open_application`、`switch_display`、`list_granted_applications`、`request_access`、`request_teach_access`、`teach_step`、`teach_batch`、`computer_batch` | 27 |
| `Claude in Chrome`（server 名 `Claude_in_Chrome`） | `navigate`、`read_page`、`get_page_text`、`find`、`computer`、`form_input`、`file_upload`、`upload_image`、`javascript_tool`、`read_console_messages`、`read_network_requests`、`resize_window`、`gif_creator`、`tabs_context_mcp`、`tabs_create_mcp`、`tabs_close_mcp`、`browser_batch`、`shortcuts_list`、`shortcuts_execute`、`list_connected_browsers`、`select_browser`、`switch_browser` | 22 |

**平台內建 server = 11 個**（workspace、cowork、visualize、session_info、scheduled-tasks、mcp-registry、plugins、skills、cowork-onboarding、computer-use、Claude in Chrome）。
**平台內建 tool 合計**：pre-loaded 14 + deferred 非 MCP 6 + deferred MCP（cowork 餘 6 + session_info 2 + scheduled-tasks 3 + mcp-registry 3 + plugins 3 + skills 2 + cowork-onboarding 1 + computer-use 27 + Claude in Chrome 22 = 69）= **89**。

備註：`computer_batch`/`browser_batch`/`teach_batch` 為「批次包裝」工具（一次送多個原子動作）；`read_me`/`show_widget`、`present_files`、artifact 系列等渲染型工具見上方「渲染 UI vs 做事」分類。

### pre-loaded / deferred 是「逐工具」而非「逐 server」（2026-06-15 釐清）

同一個 MCP server 的工具可被拆到 pre-loaded 與 deferred 兩邊——**`cowork` server 即被拆開的例子**：

- pre-loaded 僅 `present_files`（1 個）
- deferred 為其餘 6 個：`create_artifact`、`update_artifact`、`list_artifacts`、`request_cowork_directory`、`allow_cowork_file_delete`、`read_widget_context`

對照：`workspace`（bash/web_fetch）、`visualize`（read_me/show_widget）兩 server **整組** pre-loaded；其餘平台 server（session_info、scheduled-tasks、mcp-registry、plugins、skills、cowork-onboarding、computer-use、Claude in Chrome）**整組** deferred。

→ 選 pre-loaded 的判準是「高頻 / 開場常用」的單一工具（呈現結果用的 `present_files`、`bash`、`web_fetch`、視覺化、加上引擎原生 Read/Write/Edit/Skill/ToolSearch…）；專門或重量級工具（artifact、排程、computer-use 等）放 deferred。劃分粒度 = 單一工具的 **schema 是否進 context**，不是 server。

#### ⚠️ 更正：「deferred ≠ 不可呼叫」（2026-06-15 實測，先前過度宣稱）

先前把「deferred」寫成「需先 ToolSearch 才能用」是**未驗證的過度宣稱**。實證測試推翻之：

- **測試**（本 session，未先 ToolSearch）：直接呼叫 deferred 的 `mcp__cowork__list_artifacts`、`mcp__session_info__list_sessions` → **兩者皆成功回傳資料，無 InputValidationError**。
- **結論（實測）**：deferred 只是「**不把該工具的 schema 放進我的 context**」的省 token 設計，**不是把工具鎖住**。
- **機制（推論，非實測）**：底層 MCP host 仍握有所有已連接工具的真實 schema；我送出呼叫時引擎拿參數去比對 host 端 schema。上述兩工具**無必填參數**，送空參數即通過 → 直接執行。
- **system-reminder 警告「直接呼叫會 InputValidationError」真正會中的對象 = 需要參數的工具**：沒 schema 在 context 就猜不出正確參數，才驗證失敗；無參數工具天生不會中。故那句警告對「需參數的 deferred 工具」成立，對「無參數的 deferred 工具」不成立。
- **保留成立的部分**：schema 載入確為逐工具（開場 cowork 群組僅 `present_files` 有 schema，其餘 6 個僅列名）——「per-tool 而非 per-server」對 **schema 是否進 context** 仍正確；被更正的只是「deferred 是否等於不可呼叫」。
- 待補測：對一個**有必填參數**的 deferred 工具直接送空/亂參數，確認回的是 InputValidationError（以完整證實機制）。

## 待研究

- Hooks 是否存在於 Cowork（Claude Code 有 21 種事件）
- 權限系統：permission_request IPC 是否同 Claude Code；computer-use 的 tier 強制機制
- `web_fetch` 與 `WebSearch` 的網域限制實作
- Artifacts 的 `window.cowork.*` API（callMcpTool / askClaude / runScheduledTask）細節 → features.md
- MCP sampling/elicitation 在實際 connector 使用中的觀察記錄
