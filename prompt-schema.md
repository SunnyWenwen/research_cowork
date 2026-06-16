# Cowork System Prompt 結構

來源：即時內省（agent 觀察自身收到的 system prompt），2026-06-12，引擎版本 2.1.170

注意：以下為結構與重點摘要（非全文逐字）。內省所見即模型實際收到的內容，可信度最高，但會隨版本變動。

## ★ binary 層驗證（2026-06-12；asar 解包修正，2026-06-13）

App 層 session 狀態檔 `local_{uuid}.json`（見 [binary.md](binary.md)）含 `systemPrompt` 欄位（46918 字元）與 `memoryGuidelinesTemplate`（13526 字元）及 `spVariantPrompts`。

**⚠️ 修正（2026-06-13）**：`local_{uuid}.json` 的 `systemPrompt` 是**原始模板**，不是渲染後版本。實測確認欄位中含有 `{{cwd}}`（idx=37258）、`{{currentDateTime}}`（idx=46160）、`{{promptCacheBoundary}}`（idx=34283）、`{{modelName}}` 等未替換佔位符。真正的渲染版本（替換所有 placeholder 後）在每次 API call 時由 App 層動態組裝，不持久化儲存。

grep 出的 XML section tag 順序（從模板）與內省記錄一致，結構仍可信；但 46918 字元是模板長度，實際渲染後 prompt 較長（需加上 placeholder 替換的實際內容）。

實際 section tag（依出現序，節錄）：`application_details` → `tool_call_style` → `claude_behavior`（`product_information`/`refusal_handling`/`legal_and_financial_advice`/`tone_and_formatting`/`lists_and_bullets`/`progress_updates`/`user_wellbeing`/`anthropic_reminders`/`evenhandedness`/`responding_to_mistakes_and_criticism`/`search_first`/`knowledge_cutoff`）→ `ask_user_question_tool` → `todo_list_tool`/`verification_step` → `citation_requirements` → `computer_use`（`file_creation_advice`/`web_content_restrictions`/`escalate_unhelpful_web_fetch_to_chrome`/`suggesting_claude_actions`/`artifacts`/`skills`/`file_handling_rules`/`working_with_user_files`/`notes_on_user_uploaded_files`/`producing_outputs`）→ `env`/`country`。

system/init record（audit.jsonl，每輪重發）另確認執行期事實：`model: claude-fable-5`、`output_style: default`、`apiKeySource: none`、`permissionMode: default`、12 個 mcp_servers、agents 6 種、隱藏 slash command（見 tools.md）。

## `{{...}}` 與 `<...>` 的本質差異（勿混為「佔位符」）

- **`{{var}}` = 模板變數（build-time）**：由 renderer `Lk(text,vars,key)` 在組裝時替換成值，**填完即消失**，模型只看到填入的值；支援 `{{#if}}/{{else}}/{{/if}}` 條件式。例：`{{cwd}}`、`{{currentDateTime}}`、`{{promptCacheBoundary}}`→`ViA`。
- **`<tag>` = XML 結構標籤（content）**：是 prompt 內容本身、**不被替換**，原樣送進模型，用來分段（`<claude_behavior>`/`<env>`/`<computer_use>`…）。
- 兩者**巢狀**：XML 標籤包住的內容裡可含 `{{}}` 變數（如 `<env>Today's date: {{currentDateTime}}</env>`）→ 標籤靜態、值動態。這也是為何 `<env>` 標籤可能在快取區、但其日期值在邊界後才填。

## 整體組成順序

1. **工具使用說明**：如何以 function call 格式呼叫工具、平行呼叫規則
2. **工具定義**：pre-loaded 工具的完整 JSONSchema（`<functions>` 區塊）
3. **deferred 工具說明**：宣告有延遲載入工具，schema 後續以 `<functions>` 格式出現
4. **身分宣告**：「You are a Claude agent, built on Anthropic's Claude Agent SDK」+ 工具清單可能變動的提醒
5. `<application_details>`：Cowork 是 Claude 桌面 App 的功能（research preview）；明示「基於 Claude Code/Agent SDK 但**不要自稱 Claude Code**」、不要對使用者提實作細節
6. `<claude_behavior>`：行為規範，子 section 包括：
   - `<product_information>`：模型家族與產品資訊
   - `<refusal_handling>`、`<legal_and_financial_advice>`
   - `<tone_and_formatting>`（含 `<lists_and_bullets>` 詳細格式規則）
   - `<progress_updates>`、`<user_wellbeing>`、`<anthropic_reminders>`、`<evenhandedness>`、`<responding_to_mistakes_and_criticism>`
   - `<search_first>`（時事必先搜尋）、`<knowledge_cutoff>`
7. **Cowork 專屬功能指引**（多個 section）：
   - `<ask_user_question_tool>`：開工前必先用 AskUserQuestion 釐清需求
   - `<todo_list_tool>`：幾乎所有含工具呼叫的任務都要 TaskCreate；含 `<verification_step>`（要求最後加驗證步驟）
   - `<send_user_message_tool>`：工具間文字會被摘要，逐字內容須用此工具。**⚠️ 僅出現在 Fable 5（marigold）變體，base（Sonnet 4.6）prompt 無此 section**（見下方 marigold diff 與 [tools.md](tools.md) 證據）
   - `<citation_requirements>`：引用本地檔案/MCP 內容須附 Sources
8. `<computer_use>`：檔案建立觸發規則、`<web_content_restrictions>`（**禁止用 curl/python 繞過 web_fetch 限制**）、`<suggesting_claude_actions>`（主動查 MCP registry）、`<artifacts>`（React/HTML artifact 規則、禁用 localStorage）、`<skills>`（先研究後讀格式 skill）、`<file_handling_rules>`（outputs 暫存區 vs 連接資料夾）、`<producing_outputs>`、`<sharing_files>`、`<package_management>`、`<examples>`
9. `<user>`：使用者名稱與 email
10. `<env>`：日期、模型名、是否已連接資料夾
11. `<user_preferences>`：使用者自訂偏好（如要求簡潔）
12. **動態功能說明**：Scheduled tasks、Artifacts（`window.cowork` API）、**Shell access**（含本 session 的 Windows↔VM 路徑對映表，session-name 動態生成）
13. **Memory 指引**：memory 目錄路徑、frontmatter 格式、MEMORY.md 索引規則、敏感個資不可儲存清單
14. **MCP server instructions**：各 server 自帶的使用說明（如 computer-use 的 tier 權限說明）
15. **可用 skill 清單**：name/description/location

## 與 Claude Code system prompt 的差異

| 面向 | Claude Code（見 reseach_claude_code/prompt-schema.md） | Cowork |
|---|---|---|
| 組裝 | `dj()` 函式、Ws6/js6 等靜態 section | 結構不同，大量 Cowork 專屬 XML section（推測仍由 SDK 組裝，函式名待 binary 驗證） |
| 身分 | Claude Code CLI | 「Claude agent on Agent SDK」，明示非 Claude Code |
| 行為規範 | 偏工程慣例 | 完整 claude.ai 式行為規範（wellbeing、evenhandedness 等），更接近 chat 產品 |
| 動態內容 | memory/env/output_style/mcp | 多了路徑對映表、artifacts、scheduled tasks、user preferences |
| CLAUDE.md | 注入專案 CLAUDE.md | 同樣注入（以 system-reminder 形式附在 user turn，含連接資料夾的 CLAUDE.md） |

## 運行時注入（非 system prompt 本體）

- 連接資料夾的 `CLAUDE.md` 以 `<system-reminder>` 附加於 user message（標註「IMPORTANT: These instructions OVERRIDE...」）
- deferred 工具清單與 MCP server instructions 在第一個 user turn 後以 system 訊息補充
- UI 動作 hint 直接附加在使用者訊息內（如 `<cu_window_hints>`）
- **`@`-mention 機制（2026-06-14 即時內省）**：UI 的「@」選擇器(App 層)解析使用者指到的視窗/檔案/資料夾，再把結果**注入 user turn**——不是另一條即時通道。@ **視窗** → 注入 `<cu_window_hints>`（含視窗標題 + exe 路徑 + 「截圖、勿 open_application」指示）；@ **檔案/資料夾** → 注入路徑參照（某些檔型連內容）。關鍵：注入的是**「指標 + 存取指示」而非內容**——@ 視窗只給標題，agent 仍須 screenshot / Claude-in-Chrome / Read 才取得實際內容。即「機制 resolve+注入 → 我端看到的是 prompt 文字」。
- `<anthropic_reminders>` 機制：分類器觸發的提醒（long_conversation_reminder 等）

## ★ spVariantPrompts 機制（`marigold` = Fable 5 變體）

來源：bash 比對多個 local_{uuid}.json，2026-06-13。

`local_{uuid}.json` 儲存兩份 system prompt：

- `systemPrompt`（46918 chars）：**base 版本**，以 Sonnet 4.6 為基準，所有 session 相同
- `spVariantPrompts["marigold"]`（47854 chars，`mode:"replace"`）：**Fable 5 專屬完整替換版本**；僅在使用 Fable 5 的 session 中出現

`mode:"replace"` 意味 App 層選擇：若模型為 Fable 5，使用 `marigold.text` 完整替換 `systemPrompt`。

#### marigold vs base 的精確差異（5 個 block，difflib 分析）

| # | 操作 | 內容摘要 |
|---|---|---|
| 1 | **刪除** 319 chars | `<tool_call_style>` 整段：「不要在工具呼叫間摘要、不要寫 Let me…」—— Fable 5 不需要此明示規則 |
| 2 | **插入** 696 chars | `<product_information>`：Fable 5 / Mythos 5 介紹、雙用途安全措施說明 |
| 3 | **插入** 16 chars | "Fable 5, Claude"（加入 Fable 5 到模型名稱列表） |
| 4 | **插入** 18 chars | "'claude-fable-5',"（加入 API 模型字串） |
| 5 | **插入** 525 chars | `<send_user_message_tool>` 完整段落（Sonnet 4.6 無此工具） |

> ✅ **block 5 強化驗證（2026-06-13）**：跨 cache 內 **12 個 session 的 `local_*.json`** 比對，`send_user_message` 字串**只**出現在 Fable 5 的 `marigold` 變體，11 個 Sonnet 4.6 session 的 base systemPrompt **全部沒有**；且該字串在引擎 binary `2.1.170`/`2.1.177` **計數皆 0**（純 App 層 `cowork` MCP 工具）。→ 證實此工具確為 **Fable 5 變體專屬**，非 base。先前「base 已更新、Sonnet 也有」之推測未獲證據支持（見 [tools.md](tools.md) 註）。

關鍵推論：
- `<tool_call_style>` 是 Sonnet 4.6 的行為補丁，Fable 5 原生行為更好，不需明示
- `<send_user_message_tool>` 是 Fable 5 新增工具，Sonnet 4.6 沒有
- 'marigold' = Fable 5 的內部代號

#### session 路徑未存於 systemPrompt（runtime 動態注入）

實測：`systemPrompt` 欄位中找不到 session slug（`elegant-funny-keller`）。路徑對映表在**實際 API call 時由 App 層動態拼接**，不預存在 local_{uuid}.json。`local_{uuid}.json` 的 `systemPrompt` 是**初始化模板**；CLAUDE.md 內容、路徑表、Memory 條目、user preferences 均在每次 API call 時注入。

## Prompt cache 設計：邊界擺在所有變動佔位符之前（2026-06-14 實證）

來源：bash 量測 `local_c821ac90.json` 的 `systemPrompt` 模板內各佔位符位元組位置。

`{{promptCacheBoundary}}`（renderer 替換為 cache_control marker `ViA`）位於模板 **~37128** 字元處，而**所有會變動的佔位符全在其後**：`{{cwd}}`(40138)、`{{workspaceFolder}}`(40454)、`{{accountName}}`(49124)、`{{emailAddress}}`(49156)、`{{currentDateTime}}`(49206)、`{{modelName}}`(49267)、`{{folderSelected}}`(49306)。

含義：
- **邊界前(0–37128)= 純靜態**（行為規範、工具定義），跨所有 session/帳號逐字相同 → 這段是被快取的 prefix。
- **邊界後 = 動態尾段**，放 cwd/帳號/資料夾/日期/模型；替換佔位符只動尾段，不影響前面已快取的大塊。
- **`{{currentDateTime}}` 是「粗粒度」（只到日，非到秒）**：即時內省確認 env 原文為 `Today's date: Sunday, June 14, 2026 (for more granularity, use bash)`。→ session 內每輪 render 相同、**不破前綴**，只跨日才變；刻意粗粒度化即為保 cache 的設計。
- 故「佔位符每次替換」**不破壞 KV cache**：變動只發生在 cache 邊界之後。
- 佐證 GrowthBook flag `tengu_system_prompt_global_cache: true`：靜態 prefix 為**全域快取**，跨不同 session/帳號共用（因逐字相同）。這也是把 cwd/帳號/日期趕到邊界後的目的。
- 呼應 binary.md「replace-mode 變體必須含 `{{promptCacheBoundary}}`」——無邊界即無從快取。

**section 落在邊界哪側（c821ac90 模板，邊界=37128）：**
- **快取區（邊界前）**：工具定義 → `<application_details>`(2770) → `<tool_call_style>`(3365) → `<claude_behavior>`(3692，含 product_information/tone_and_formatting/user_wellbeing/knowledge_cutoff 等子段，跨度大) → `<ask_user_question_tool>`(22638) → `<todo_list_tool>`(24533) → `<citation_requirements>`(25969) → `<computer_use>`(26404) → `<artifacts>`(32096)。
- **動態尾段（邊界後）**：`<skills>`(37155，緊接邊界、動態生成) → `<producing_outputs>`(44071) → `<user_preferences>`(49586) → 路徑表 / Memory / 真正日期值(`{{currentDateTime}}`@49206)。
- → 邊界精確落在 `<artifacts>` 與 `<skills>` 之間。`<claude_behavior>` 是快取區的主要成分**之一**，但快取區 ≠ 只有 claude_behavior（還含工具定義與多個行為/用法 section）。
- 注意：21476 處的 `<env>` 是行為規範內文對 env 的**引用**，非帶日期的實際 env 區塊（日期值在邊界後）。

**快取範圍的正確理解（勿誤為「只有邊界前能快取」）：**
- 邊界前(0–37128) = **全域快取 prefix**：跨 session/帳號逐字相同，連首訊都可能 cache hit（`tengu_system_prompt_global_cache:true`）。
- 邊界後尾段 + 對話歷史 = **仍可快取，但 per-session 範圍**：Anthropic prompt caching 支援多斷點(≤4)、prefix-incremental；session 內固定的尾段(cwd/帳號/skills)與歷史會在後續斷點被快取。
- 真正永不快取 = 最新一輪未固定的增量。（`{{currentDateTime}}` 為日粒度、session 內穩定，只跨日才變，不算「每 request 變」——見上方更正。）
- ⚠️ 證據邊界：**僅直接確認模板內這 1 個 `{{promptCacheBoundary}}`**；「後續斷點」為 SDK 標準行為之推論，未從 Cowork 實際 request body 驗證（模板不含 message-level cache_control）。

**對話訊息同樣會被快取（非僅 system prompt）：** prefix 快取涵蓋「跨連續請求穩定的前綴」，而對話歷史 append-only → 第 N 輪的 [system + turn1..N-1] 與上輪逐字相同 → 整段 cache hit，只有最新一輪是新算。證據：`result` record 的 `cache_read_input_tokens`（「1+1」session 即達 23352，遠超單一 system 片段；多輪會隨歷史增長）。永不快取者僅最新一輪未固定的增量（`{{currentDateTime}}` 為日粒度、session 內穩定，不破前綴）。TTL 預設 ~5 分鐘，`tengu_prompt_cache_1h_config` 可延長至 1 小時；斷點 ≤4。

## 待研究

- 用 binary（Claude Desktop 的 JS bundle）驗證組裝函式與完整 section 原文
- 其他 `spVariantPrompts` key（是否有 `opus`、`haiku` 等對應不同模型？）
- `memory_paths.auto` 的注入時機（systemPrompt 模板中是否有佔位符？）
- 各 MCP server instructions 的注入時機與條件
