# CLAUDE.md

## 專案說明

本專案專門研究 Cowork（Claude 桌面 App 的 agent 模式，研究預覽版）的內部機制與行為，所有工作圍繞著理解、記錄、驗證 Cowork 的運作方式。姊妹專案：`D:\project\test_claude_code_online\reseach_claude_code`（研究 Claude Code）。Cowork 與 Claude Code 同樣建立在 Claude Agent SDK 之上，可互相對照。

## Cowork 機制知識庫

當對話中討論到任何 Cowork 的機制（包括但不限於：工具載入、ToolSearch、Skill 系統、sandbox VM、session 格式、Memory、Artifacts、MCP connectors 等），請執行以下步驟：

1. 讀取 `analysis.md`（索引），找到對應的子檔案
2. 讀取對應子檔，確認該機制是否已有記錄
3. 若未記錄或記錄不完整，將新內容更新進對應子檔
4. 更新時維持現有的文件結構與格式風格

機制分析文件：
- `analysis.md`：索引
- `tools.md`：工具系統（pre-loaded/deferred、ToolSearch、Skill、MCP）
- `sandbox.md`：Linux sandbox VM（mount 對映、網路限制、與 Windows 橋接）
- `session.md`：session 機制與 transcript 格式（三層記錄：引擎 JSONL / App audit.jsonl / App session.json）
- `prompt-schema.md`：system prompt 結構
- `features.md`：Cowork 獨有功能（Artifacts、Scheduled Tasks、Memory、computer-use）
- `binary.md`：Desktop App 程式碼與資料目錄、App 層 vs 引擎層的 binary 證據

## 機制驗證方法

驗證 Cowork 機制時，依以下優先順序使用四種方式，並在文件中標註來源：

### 1. 即時內省（最優先，Cowork 獨有優勢）

研究者就是 Cowork agent 本身，可直接觀察自己的運行環境，最可信。

- system prompt 內容：agent 可直接讀到自己收到的指示
- 工具清單與 schema：pre-loaded 工具直接可見；deferred 工具經 ToolSearch 載入後可見完整 schema
- sandbox 內部：用 `bash` 工具在 VM 內執行探測指令（`mount`、`env`、`ps`、網路測試等）
- 記錄時標註（例如：「來源：即時內省，2026-06-12」）
- 注意：不同 session 的環境可能隨版本更新改變，重要結論應記錄觀察日期

### 2. 真實 session 記錄（次優先）

- **本 session 的原始 JSONL 可直接從 bash 唯讀存取**：`/sessions/{session-name}/mnt/.claude/projects/`（見 sandbox.md），自我觀察首選
- Cowork 內建 `session_info` MCP 工具（`list_sessions`、`read_transcript`）可列出並讀取本機**其他** session（整理過的 transcript，非原始 JSONL）
- 其他 session 的原始 JSONL 位於 `C:\Users\User\AppData\Roaming\Claude\local-agent-mode-sessions\`，檔案工具與 bash 都碰不到——需使用者手動複製到本專案的 `cowork_sessions/` 資料夾
- 發現描述與記錄不符時，以實際記錄為準並更新對應子檔
- 記錄時附上來源 session id

### 3. 官方文件

- Cowork 使用說明：`https://support.claude.com`（搜尋 Cowork 相關文章）
- Claude Agent SDK 文件：`https://docs.claude.com`
- Claude Code 文件（底層共用機制可參照）：`https://code.claude.com/docs/llms.txt`
- 記錄時附上頁面名稱或 URL

### 4. 桌面 App 程式碼（找不到或太細的機制才用）

Claude Desktop 是 Electron App，agent 邏輯為打包的 JS bundle。本機為 **Microsoft Store（MSIX）版**（來源：即時內省，mount 路徑含 `Packages\Claude_pzs8sxrjxfjjc`，2026-06-12）。

- 程式本體：`C:\Program Files\WindowsApps\Claude_{版本}_x64__pzs8sxrjxfjjc\`（ACL 保護；用 `Get-AppxPackage *Claude*` 查確切版本與 InstallLocation）
- App 資料：`C:\Users\User\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\`（`AppData\Roaming\Claude\` 為其別名）
- 注意：`AppData\Local\AnthropicClaude\` 是非 Store 安裝版位置，本機不適用
- Cowork 的檔案工具與 bash 都無法直接存取上述路徑，需使用者手動複製檔案進本專案後再 grep/分析
- **已複製進專案**（2026-06-12）：`Claude_1.11847.5.0_x64__pzs8sxrjxfjjc/`（含 app.asar、claude.exe）與 `RoamingClaude_cache/`（含 claude-code-vm 引擎 ELF、local-agent-mode-sessions log）。分析見 `binary.md`
- 引擎 binary `claude-code-vm/2.1.170/claude` 為 not-stripped ELF，可用符號表分析
- **不可修改**任何 App 檔案；config.json 含 OAuth token、.audit-key 為 HMAC 金鑰，**機敏不分析/不外洩**
- 記錄時附上函式名稱或特徵字串

## 專案結構

- 工作目錄：`C:\Users\User\Claude\Projects\research_cowork`（即 Cowork 連接的資料夾）
- sandbox 內對應路徑：`/sessions/{session-name}/mnt/research_cowork/`（session-name 每次 session 不同）
- session 記錄複製區：`cowork_sessions/`（手動從 `AppData\Roaming\Claude\local-agent-mode-sessions\` 複製）
- 機制分析文件：本目錄下的 `analysis.md`（索引）及各子檔

## Cowork 與 Claude Code 的已知差異（研究時注意）

- Cowork 的 bash 在隔離 Linux VM 內執行（非本機 shell）；Claude Code 直接在本機執行
- Cowork 檔案工具用 Windows 路徑、bash 用 VM 路徑，存在雙軌路徑對映
- Cowork 每次 bash 呼叫獨立（無 cwd/env 延續）；Claude Code 維持 shell session
- Cowork 有 Claude Code 沒有的功能：Artifacts、Scheduled Tasks、computer-use、MCP registry 建議、視覺化 widget
- 兩者都有：ToolSearch/deferred tools、Skill 系統、Memory、subagent（Agent 工具）
