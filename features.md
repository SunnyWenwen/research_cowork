# Cowork 獨有功能

來源：即時內省（工具 schema 載入 + 實測），2026-06-12；官方文章 [How we contain Claude across products](https://www.anthropic.com/engineering/how-we-contain-claude)（2026-05-25）

## Artifacts（持久化 HTML 視圖）

來源：即時內省（create/update/list_artifacts schema + list 實測）

- **儲存位置**：`C:\Users\User\Claude\Artifacts\{id}\index.html`（使用者可直接看到的路徑，非 AppData）
- **建立流程**：先用 Write 寫完整 HTML 檔 → 傳 `html_path` 給 `create_artifact`（**非 inline 傳 HTML**，設計上強迫 agent 可 Read 回來驗證）
- **沙箱渲染**：網路全擋，只允許三個精確 CDN URL（Chart.js 4.5.0 / Grid.js 5.0.2 / Mermaid 11.10.0），**必須附 SRI integrity hash**，其他一律 inline
- **`window.cowork` API**：`callMcpTool(name, args)`（限 `mcp_tools` 參數宣告過的工具，且要求「本 session 實際呼叫並驗證過輸出形狀」）、`askClaude(prompt, data[])`（Haiku 輕量推論）、`runScheduledTask(taskId)`（需 userActivation）
- **更新需使用者核准**：`update_artifact` 要求 `update_summary`，顯示在核准框
- 開啟時自動重新拉 connector 資料（讀取有透明快取）；`localStorage` 跨重啟持久
- **登錄表**：`{...}/9de92944.../artifacts.json` 記每個 artifact 的 `id/name/description/createdBySessionId/lastModifiedBySessionId/mcpTools/isStarred`（2026-06-14，見 binary.md）

## Scheduled Tasks（排程任務）

來源：即時內省（schema + list 實測）

- **實作為 Skill**：儲存在 `C:\Users\User\Claude\Scheduled\{taskId}\SKILL.md` —— 排程任務就是一個定時觸發的 skill
- 三種模式：`cronExpression`（重複，**以本地時區解釋**）/ `fireAt`（一次性，ISO 8601，觸發後自動停用）/ 都不給（ad-hoc 手動執行）
- **只在 App 開啟時執行**；錯過的任務於下次啟動補跑
- 重複任務派發時加數分鐘確定性延遲（平衡伺服器負載）；一次性任務不延遲
- 每次執行是全新 session（無對話記憶），prompt 必須自包含
- `notifyOnCompletion`：完成時通知**建立它的 session**（跨 session 通知機制，單一訂閱者）

## Memory（跨 session 記憶）

來源：即時內省（實際寫入測試，2026-06-12）

- 位置：`{local-agent-mode-sessions}\{id}\{id}\spaces\{space-uuid}\memory\`，**依 space 區分**，每檔一事實 + `MEMORY.md` 索引（每 session 載入 context）
- **寫入會被系統改寫**：實測用 Write 寫入後，frontmatter 的 `metadata` 被自動注入 `node_type: memory` 與 `originSessionId: {本 session 的 SDK session id}`——存在後處理層。**binary 證實**：`originSessionId`/`node_type` 字串在**引擎 binary**（非 App 層），即 Memory 後處理由 Claude Code 引擎執行（見 [binary.md](binary.md)）
- `MEMORY.md`（無 frontmatter）不被改寫——後處理只針對 memory 條目檔
- bash 端 `.auto-memory` 掛載**唯讀**且**即時同步**（Write 後立刻可見）；寫入只能走檔案工具（Windows 路徑）
- system prompt 內建敏感個資清單（健保、政府證號、帳密等），未經明示同意不得寫入

## 檔案刪除權限（read-write-no-delete）

來源：即時內省（rm 實測 + allow_cowork_file_delete 流程實測）；官方文章證實

- 連接資料夾預設掛載為 **read-write-no-delete**：可寫但 `rm` 回 `Operation not permitted`（FUSE 層強制，非 chmod）
- `allow_cowork_file_delete` 工具 → 使用者核准 → **以資料夾(mount)為單位**解鎖刪除（實測訊息：「File deletion is now enabled for the "research_cowork" folder」），之後 rm 即成功。**逐 mount 獨立**：對 `research_cowork` 解鎖後，`outputs` 仍禁刪，需另對 `outputs` 解鎖（2026-06-14 實測）
- **`outputs` scratch 也是 rw-no-delete**（非全自由）：可寫/建檔但 `rm` 預設被擋，與連接資料夾同制
- 官方說明共有三種掛載模式：read-only / read-write / read-write-no-delete；企業可由 MDM 設定 mount-path allowlist
- 對照：`uploads`、`.auto-memory`、`.claude/*` 為 read-only

## computer-use（桌面控制）

來源：即時內省（MCP instructions）；官方 support 文章

- 工具選擇優先序強制三層：專用 MCP → Claude in Chrome → computer-use（最後手段）
- `request_access` 逐 App 核准；**tier 制**：瀏覽器=read（只能看截圖）、終端機/IDE=click（可點不可打字）、其他=full。由「最前景 App 檢查」強制——前景是受限 App 時對應操作直接回錯誤
- 投資/交易/加密貨幣類 App 預設封鎖（官方）；連結一律不可用 computer-use 點擊（防釣魚，須走 Chrome MCP 看完整 URL）
- UI 會把使用者指向的視窗以 `<cu_window_hints>` 注入訊息（見 session.md）
- 官方明示：computer-use **沒有 sandbox**，直接操作真實桌面——與 bash 的 VM 隔離成對比

## UI 右側面板資料來源（2026-06-14，截圖 + 即時實驗確認）

| 面板 | 顯示內容 | 決定規則 |
|---|---|---|
| **Progress** | 任務清單 + 完成狀態 | agent 的 `TaskCreate`/`TaskUpdate`，持久化於 `.claude/tasks/{cliSessionId}/{id}.json`（見 session.md） |
| **Working folders** | 連接資料夾下「本 task 被碰過的檔」 | **= 本 task 被任何工具(含 bash/Read/Write/Edit)碰過的檔，按連接資料夾分組；事後排除 gitignored 路徑與 dotfile**；**非**資料夾完整列表 |
| **Context** | **選擇性**收錄：把外部內容帶進任務的 connector + 引用檔案 | 面板自述 "Track tools and referenced files used in this task"，但**非「所有工具呼叫」**——實測 **WebSearch 進**(Connectors → Web search，可點開看 query+全部結果)、**`search_mcp_registry`(registry 目錄查詢)不進**。推測分界：帶外部內容進來的 connector(web search / 連上的 MCP 如 Gmail/Slack)算；內部/平台操作(registry 瀏覽、ToolSearch、TaskCreate…)不算。⚠️ 僅 2 資料點，確切收錄集未定，需連真實 connector 再驗 |

**Working folders 規則的推導（含修正）**：
- 連接的 `reseach_claude_code` 一開始空白 → 用 **Read** 開 `docs-reference.md` 後它**立即出現**（證實「被碰過才顯示、非完整列表」）。
- 但 `2.1.170`、`Claude - 捷徑.lnk` **只經 bash(strings/grep) 碰過、未用檔案工具**，仍顯示 → **修正先前「bash 不算數」的錯誤結論**：bash 碰過也算。
- 兜合全部觀察的最佳假設：**「被任何工具碰過」為主因，gitignored 路徑與 dotfile 為事後排除濾網**。`reseach_claude_code` 早先唯一碰過的是 `cat .gitignore`(dotfile→隱藏)故空白；`RoamingClaude_cache`/`asar_extracted` 內檔雖大量 bash 過但整夾被 gitignore→隱藏。
- ⚠️ 此為最佳擬合假設，未逐因素隔離驗證（本題曾兩次判斷有誤）。同名檔重複(如 `analysis.md`×2)= 原檔 + `repo_push/` 副本皆被碰過。

## 視覺化 Widget 與互動

- `mcp__visualize__show_widget`：行內 SVG/HTML widget，有 `sendPrompt()` 可由使用者互動觸發新訊息
- `mcp__cowork__read_widget_context`：agent 可回讀 widget 當前狀態（widget 是有狀態的，使用者操作可被 agent 觀察）
- `AskUserQuestion`：結構化選擇題 UI，回答以工具結果回傳（含 annotations）

## MCP Registry（connector 自我擴充）

- `search_mcp_registry`（關鍵字搜尋，回傳含 connected 狀態）→ `suggest_connectors`（渲染 Connect 按鈕卡片）
- 工具呼叫遇驗證錯誤時，可從工具名 `mcp__{uuid}__{tool}` 取出 uuid 直接建議重新連接
- `list_connectors`：渲染已安裝清單卡片

## Local vs Remote Sessions（2026-06-14 app.asar 補充）

來源：即時內省（request_cowork_directory schema）＋ app.asar / 引擎 bundle grep。

- session id 前綴 `local_`；`request_cowork_directory` 在 local session 可開原生資料夾選擇器、remote session 必須給路徑。
- **session kind 三種**：`local` / `remote` / `cloud-sync`（bundle 內可見；`canUseTool` 對 `cloud-sync` 另有權限分支）。
- **建立入口 = 「委派 coding 任務」工具**：描述為「為需要完整 editor/terminal/file system 的 codebase 變更開一個 session……寫一份 spec，使用者檢視後**選『本機資料夾或 cloud environment』並啟動**」。→ 即「寫 spec → 選 local/cloud → launch」的遠端/雲端代理派發流程。**UI 對應左側選單「Dispatch (Beta)」**（截圖證實 2026-06-14）。
- **CCR（Claude Code Remote）bridge**：一整組 `tengu_ccr_*` / `tengu_bridge_*` flag 控制（`bridge_min_version:"2.1.70"`、attestation `accept_level:"VERIFIED_BY_GATE"`、`ccr_bridge_multi_session`）；host↔遠端的輪詢/心跳參數見 `tengu_bridge_repl_v2_config`、`tengu_bridge_poll_interval_config`。
- **remote session 綁定 space**：`CoworkSpaces.setRemoteSessionSpace` / `getRemoteSessionSpaces` / `removeRemoteSessionSpace`。
- **顯示通道**：`@ant/rfb-client`（RFB/VNC，binary.md 記過）為遠端桌面畫面；`@anthropic-ai/conway-client`（0.2.0-dev）為宣告依賴，**但 bundle 內找不到使用處**（推測動態載入或原生模組，疑為 cloud-agent 後端 client，待確認）。
- `tengu_kestrel_arch` flag gate 一則「本機或遠端執行 Claude Code」的提示。

## 官方安全架構（交叉驗證內省發現）

來源：[How we contain Claude across products](https://www.anthropic.com/engineering/how-we-contain-claude)，2026-05-25

- **VM 實作確認**：Windows 用 **HCS**（Host Compute Service）、macOS 用 Apple Virtualization framework——解答 sandbox.md 待研究項
- **host-mode 演進**：原為 full-VM mode（agent loop 在 VM 內）；現行架構 agent loop 在主機、只有程式碼執行在 VM——**完全符合內省觀察**（檔案工具走 Windows 路徑=主機、bash 走 VM）。改動原因：VM 啟動失敗時 agent 仍能回應
- **本機 MCP server 也在主機執行**（非 VM 內），與 Claude Desktop 一致
- **憑證隔離**：credentials 留在主機 keychain；VM 只拿 per-session scoped token，可獨立撤銷
- **VM 內防禦性 MITM proxy**：攔截對 api.anthropic.com 的流量，只放行帶本 VM session token 的請求（修補「經核准網域exfiltration」漏洞：惡意檔案曾誘導用攻擊者的 API key 上傳檔案）
- 六大隔離機制中兩項在 guest kernel 之外強制（agent 取得 VM root 也突破不了）
- symlink 解析在路徑驗證**之前**（防 symlink 逃逸）
- EDR 看不進 VM；企業以 OTLP pull-based 匯出事件日誌補償

## 待研究

- Remote session 的實際形態（雲端 VM？）
- `askClaude` 的 Haiku 呼叫計費與限制
- widget context 的儲存位置與格式
- OTLP 匯出的事件種類
