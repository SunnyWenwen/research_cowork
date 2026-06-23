# Cowork 機制分析

本文件為索引，各主題詳見對應檔案。研究方法見 [CLAUDE.md](CLAUDE.md)。

核心發現：**Cowork = App 層（Electron/app.asar：UI、VM 管理、egress、稽核、host-loop）+ 引擎層（Claude Code 2.1.170：agentic loop、session 記錄、Memory、工具）+ sandbox VM**。binary 層 grep 已可乾淨切分機制歸屬（見 binary.md）。session JSONL、ToolSearch、Skill、Memory 後處理等底層機制與 Claude Code 共用。

---

## [tools.md](tools.md) — 工具系統

- **Pre-loaded / Deferred 分類**：與 Claude Code 同機制、不同組合；無 Bash/TodoWrite，改用 `mcp__workspace__bash` 與 TaskCreate 系列
- **ToolSearch**：`select:`/關鍵字/`+詞` 載入；回傳 `<functions>` JSONSchema。**底層 = Anthropic API server-side tool（官方文件證實）**：deferred 工具以 `defer_loading:true` 留在 `tools` 參數、只是不進 system-prompt prefix；搜到時 API 插 `tool_reference` block 並自動展開。變體 regex/BM25（`*_20251119`，引擎 2.1.170 用較舊 `tool-search-tool-2025-10-19`）；亦支援 client-side 自訂版（`[ToolSearch:optimistic]` 第一方走 server、否則 fallback）。**deferred≠不可呼叫**（無參數工具不載也能叫）。session log **不記** API request payload。已更正先前兩處 binary 推論（tools 參數內容、純 server 與否），來源：官方文件 + binary（2026-06-15）
- **MCP 架構**：server 三種來源——平台內建（語意名 cowork/workspace/visualize/session_info...）、使用者 connector（純 uuid）、**plugin 內建（`plugin:{plugin}:{server}` 前綴，2026-06-15 新增）**；plugin 可只帶 skill / 只帶 server / 兩者皆有，清單高度依 session 帳號設定而變。**使用者自己的 / plugin 的 MCP server 工具一律 deferred、永不 pre-loaded**（開場 system-reminder 只列名、常先 "still connecting" 再經 deferred_tools_delta 補入；本 session github MCP 55 工具即此模式，2026-06-23）
- **MCP registry 自我擴充**：search_mcp_registry → suggest_connectors 主動建議流程
- **Skill 系統**：同 Claude Code 但唯讀快取，session 內不可修改
- **與 Claude Code 差異總表**

## [sandbox.md](sandbox.md) — Linux Sandbox VM

- **三層架構**：Windows → Ubuntu 22.04 VM → 每次 bash 呼叫一個 bwrap（--unshare-net/--unshare-pid）
- **每次呼叫獨立的原因**：bwrap 重新啟動，PID 1 即 bwrap
- **路徑對映**：virtiofs + FUSE；實體位置在 MS Store 套件 LocalCache；隱藏掛載 `.claude/projects`（session JSONL，ro）、`.auto-memory`（ro）、`.claude/skills`（ro）
- **網路 allowlist proxy**：unix socket 橋接主機端 proxy；pypi/npm/github 通、一般網站擋（curl 000）；**按精確主機名放行**（`github.com` 通／`api.github.com` 擋），**與 HTTP method 無關**（POST 可用）；**使用者可在 Cowork 設定擴充白名單，但 agent 不能自改、且改了要新 session 才生效**（2026-06-15 實測）
- 環境特徵：`SANDBOX_RUNTIME=1`、隨機人名 session slug
- **VM 內部組成（2026-06-14 新發現）**：VM 實裝完整引擎 `/usr/local/bin/claude`（BuildID 與 cache ELF 一致）+ 活的 `coworkd` daemon（`/run/coworkd/cli-plugin.sock`）+ `cli-wrapper`；沙盒由 `@anthropic-ai/sandbox-runtime`(ASRT) 管理，實測 seccomp-bpf + cap-drop + no-new-privs。修正「VM 為笨 shell」印象
- **agentic loop 執行位置定論（2026-06-14）**：兩顆引擎對應兩模式——**本機/hostLoopMode session 引擎跑在 host**（claude.exe），**VM/remote 模式跑 VM 內 `/usr/local/bin/claude`**。決定性證據：本 session 活躍 transcript 寫入「從 VM 唯讀」的 host `.claude/projects/`，VM 行程不可能寫之 → 引擎在 host（詳見 sandbox.md）

## [session.md](session.md) — Session 機制

- **底層即 Claude Code session**：version 2.1.170、entrypoint `local-agent`、JSONL 格式相同
- **目錄結構**：`local-agent-mode-sessions\{id}\{id}\local_{uuid}\`（outputs/uploads/.claude）+ `spaces\{uuid}\memory`
- **兩層 session id**：Cowork `local_{uuid}` vs SDK JSONL sessionId（**一對多**：resume/重啟新增 jsonl，compaction 不分檔只插 `compact_boundary`，2026-06-14 實證）
- **新 JSONL 記錄類型**（Claude Code 文件未記錄）：`queue-operation`、`last-prompt`、`attachment`（deferred_tools_delta）、`mode`（`{type,mode,sessionId}`，實測 normal）
- **cache 全 12 session 清單**：僅 1 個 Fable 5、餘 Sonnet 4.6；MCP server 數 6/10=10 → 6/12=11~12；無一用 Agent/subagent
- **`system/status` 值固定 `requesting`**（171 筆核對）；勿與其他 record 的 `status` 鍵（connected/allowed/completed/in_progress）混淆
- **session_info 工具**：list_sessions / read_transcript（跨 session 觀察，Claude Code 無）
- bash 可直接唯讀本 session JSONL（自我觀察）

## [prompt-schema.md](prompt-schema.md) — System Prompt 結構

- **組成順序**：工具定義 → application_details → claude_behavior（chat 式行為規範）→ Cowork 功能指引 → computer_use → user/env/preferences → 動態（路徑表/artifacts/scheduled tasks）→ Memory → MCP instructions → skills
- **身分**：「Claude agent on Agent SDK」，明示不自稱 Claude Code
- **運行時注入**：CLAUDE.md 以 system-reminder 附於 user turn；deferred 清單後補；UI hint 進使用者訊息
- **Prompt cache 設計**：`{{promptCacheBoundary}}`(~37128 字元處)擺在所有變動佔位符之前 → 靜態 prefix 跨 session/帳號全域快取(`tengu_system_prompt_global_cache:true`),變動只在邊界後,故替換佔位符不破壞 KV cache

## [binary.md](binary.md) — Desktop App 程式碼與資料目錄

- **複製進來的結構**：app.asar（App 層）、claude-code-vm/claude（Linux 引擎 ELF，就是 VM 內跑的）、local-agent-mode-sessions（所有 log）
- **三層架構 binary 證據**：用特徵字串 grep 切分——`queue-operation`/`last-prompt`/`originSessionId`/`node_type` 屬引擎層；`_audit_hmac`/`hostLoopMode`/`egressAllowedDomains`/`VirtualMachine` 屬 App 層
- **雙平台同源驗證**：Windows standalone CLI 2.1.170 ↔ Linux 引擎 ELF 2.1.170 字串計數逐項一致、長字串交集 94,625 條 → 同一 JS bundle 雙平台 build，引擎特徵字串非 Cowork 專屬
- **版本 forward diff 2.1.170→2.1.177**：核心 session/ToolSearch/Memory 機制不變；177 新增 v2 subagent / teammate / background agent、ArtifactTool/ProjectsTool 下沉引擎；effort 範圍 low→xhigh→max 確定；Mythos Preview→Fable 模型鏈（Project Glasswing）
- **UUID 身分對應**：bc71ab19=帳號(account)、**9de92944=組織(organizationId，2026-06-14 修正，原標環境/裝置)**、219d9c7e=spaceId、local_*=session、cliSessionId=引擎
- **App data 其他檔案（2026-06-14）**：GrowthBook flag 快取(`cowork-gb-cache.json`,含 Fable 5 停用訊息)、client_data 快取(`cwkCfgKeyForModel`)、policy-limits 快取、`spaces.json`(space登錄)、`artifacts.json`(artifact登錄)、DXT 擴充黑/白名單、git-worktrees、buddy-tokens(每日用量)
- App 設定檔重點（coworkUserFilesPath、模型自動降級等）

## [features.md](features.md) — Cowork 獨有功能

- **Artifacts**：存於 `C:\Users\User\Claude\Artifacts\{id}\index.html`；html_path 檔案式建立；CDN 三庫 allowlist + SRI；`window.cowork` API（callMcpTool/askClaude/runScheduledTask）；更新需核准
- **Scheduled Tasks**：實作為 Skill（`C:\Users\User\Claude\Scheduled\{taskId}\SKILL.md`）；cron 本地時區 / fireAt 一次性；只在 App 開啟時跑；跨 session 完成通知
- **Memory**：依 space 區分；**寫入被後處理改寫**（自動注入 `node_type`、`originSessionId`）；bash 端唯讀即時同步
- **檔案刪除權限**：連接資料夾預設 read-write-no-delete（FUSE 強制）；`allow_cowork_file_delete` 以資料夾為單位解鎖
- **computer-use**：三層工具優先序；App tier 制（read/click/full）；無 sandbox（對比 bash）
- **官方安全架構**：HCS/AVF hypervisor、host-mode 演進、keychain 憑證隔離、VM 內 MITM proxy（來源：How we contain Claude across products）
- Local vs Remote session 的存在證據

---

## 已解決（spSectionPrompts / MCP / ELF strings，2026-06-13）

- ✅ **spSectionPrompts（"starling"）vs spVariantPrompts（"marigold"）完全不同系統**：前者作用於 sub-agent（section 級注入），後者作用於主 agent（整份 prompt replace）
- ✅ `Cc` 常數物件：14 個 section key 代碼（`cu_safety`、`subagent_env_hl/vm`、`html_artifacts`、`computer_use`、`dispatch_*` 等）
- ✅ `Du(spSectionPrompts, key, default)`：section 選擇器，feature flag `lt("124685897")` 控制；flag 關閉直接回傳 hardcoded 預設
- ✅ `Lk(text, vars, key)`：渲染器，支援 `{{#if}}`/`{{else}}`/`{{/if}}` 條件式（不支援巢狀）+ `{{var}}` 替換
- ✅ `Jfr({vmProcessName, hostLoopMode, hostCwd, spSectionPrompts})`：sub-agent 環境說明生成；host-loop vs VM 沙盒各一份硬編碼預設，可被 `spSectionPrompts` 覆寫
- ✅ **MCP 協議版本 2025-11-25**（`directMcpHost.js`）；向後相容 5 版本至 `2024-10-07`；StreamableHTTP 傳輸
- ✅ **MCP sampling + elicitation 支援確認**：connector server 可向 LLM / 使用者主動請求；OAuth 完整流程含 `UrlElicitationRequired`（-32042）
- ✅ 引擎 ELF（2.1.170）strings 確認：`queue-operation`、`last-prompt`、`deferred_tools_delta`、`total_deferred_tools`、`attachmentSent`、`attachment_` 全部存在於引擎層 → 確認是引擎層功能
- ✅ ELF `nm` 只見 V8/Node.js C++ 符號（1068 個），JS 邏輯改用 `strings` 提取

## 已解決（雙平台同源 + 版本 forward diff，2026-06-13）

- ✅ 專案 root 的 `2.1.170`（232M PE32+）是 **Windows standalone Claude Code CLI**；同版本跨平台比對（vs Linux 引擎 ELF）字串計數逐項一致、長字串交集 94,625 條、App 層字串兩邊皆 0 → **同一 JS bundle 雙平台 build**，引擎特徵字串為 Claude Code 核心、非 Cowork 專屬
- ✅ 使用者再複製 `2.1.177`（245M PE32+，較新）→ forward diff：核心 session/ToolSearch/Memory 機制 170→177 **無結構性變動**（queue-operation/last-prompt/deferred_tools_delta 計數不變）
- ✅ 177 真正新增（170 計數=0 已驗證）：**v2 subagent / teammate / background agent**、`ArtifactTool`/`ProjectsTool` 下沉進引擎、skill sync 強化、tool-use 重試遙測
- ✅ **effort 參數範圍確定**（解決下方研究方向 #5）：`low`→`xhigh`(`x-high`)→`max`；xhigh/max 須 `max_tokens ≥ 64000`
- ✅ **模型世代鏈**：Mythos Preview(`claude-mythos-preview`) → Fable，遷移代號 **Project Glasswing**
- ✅ 方法學教訓：comm 可讀字串差集假陽性多（minifier/換行），須改用識別字 token 差集 + 計數驗證
- ⚠️ 仍**未解（backward）**：queue-operation 等是否為 2.1.170 新增——177 更新、170 同版，皆無法回答；需 **2.1.70/2.1.72 較舊** binary

## 下一輪研究方向

1. **（阻塞中）backward 版本 diff**：需手動複製**較舊**版本 `C:\Users\User\.local\share\claude\versions\2.1.70`（或姊妹專案的 2.1.72）進專案，才能確認 `queue-operation`/`last-prompt`/`attachment` 是否為 2.1.170 新增。已有的 2.1.170/2.1.177 都不夠舊
2. **追蹤 v2 subagent / teammate / background agent**：177 已現雛形，待 Cowork 引擎升級後觀察是否啟用；釐清 `subagent_fork_remote_isolation` 與 Remote session 的關係
2. ~~Remote session 形態~~（**部分解決 2026-06-14**：kind=local/remote/cloud-sync、經「委派 coding 任務→選 local/cloud→launch」建立、CCR bridge + attestation、綁 space，見 features.md）；**仍開放**：`@anthropic-ai/conway-client` 用途（宣告依賴但 bundle 內無使用處）、RFB 實際連線流程
3. `gVisor` 在 HCS VM 內部的確切角色（雙層隔離？）
4. bootstrap `/api/claude_cli/bootstrap` 回應的 `client_data` 完整欄位
5. `effort` 參數範圍與 extended thinking 的對應關係
6. MCP sampling/elicitation 在真實 connector session 中的 audit.jsonl 觀察

## 已解決（app.asar 解包，2026-06-13）

- ✅ `local_{uuid}.json` 的 systemPrompt 是**模板**（含 `{{cwd}}` 等 placeholder），非渲染版——**修正先前記錄的錯誤**
- ✅ System prompt 完整 placeholder 清單（12 個，見 binary.md）；`{{cwd}}` = `/sessions/{slug}`
- ✅ `spVariantPrompts` 選擇邏輯：key 由 `GET /api/claude_cli/bootstrap` 伺服器下發（feature flag），優先序 `cwk_cfg` > `cowork_sp_variant` > defaultKey
- ✅ `mode: "append"` 存在（除 replace 外）；replace-mode 必須含 `{{promptCacheBoundary}}`
- ✅ HMAC = 鏈式 SHA-256：`HMAC(key, prevHmac ‖ recordJSON)`，任一筆竄改破壞整鏈
- ✅ `model_refusal_fallback` 有 3 種 direction：retry / revert / sticky；企業可設 `vmEgressPolicy` 覆寫 egress
- ✅ 引擎 config `Qi` 含 `REPL`/`JavaScript`/`NotebookEdit` 工具——技術上注冊但由 system prompt 行為規範過濾
- ✅ VM runtime = `"gvisor"`（HCS 之上再一層 user-space kernel 隔離）
- ✅ `smol-bin.x64.vhdx` = VM image，元件含 `rootfs.vhdx` + `vmlinuz` + `initrd`；download URL = `downloads.claude.ai/vms/linux/{arch}/{sha}`
- ✅ `@ant/rfb-client` = Remote session 的 VNC/遠端桌面顯示機制

## 已解決（multi-session 比對，2026-06-13）

- ✅ `system/model_refusal_fallback`：Fable 5 安全機制觸發 → 自動降級 Opus 4.8，`retracted_message_uuids` 撤銷原回應；研究 session 觸發 3 次（分析 binary 時）
- ✅ `system/status: "requesting"` 值固定，每次 API call 觸發一筆（工具呼叫多時每輪多筆）
- ✅ `system/thinking_tokens` 僅 Fable 5（auto_thinking）出現；Sonnet 4.6 完全沒有
- ✅ `system/permission_request` 適用對象：**AskUserQuestion + 危險操作**（非僅 computer-use）
- ✅ `result` record 含完整計費（`total_cost_usd`）、延遲（`ttft_ms`）、`modelUsage` 拆分
- ✅ `spVariantPrompts["marigold"]` = Fable 5 system prompt 變體；base 為 Sonnet 4.6 基準；5 處精確差異（見 prompt-schema.md）
- ✅ session 路徑（slug）不存於 systemPrompt 模板，runtime 動態注入
- ✅ 模型升級時間線（audit.jsonl 時間戳 UTC 核對）：6/10～6/12 13:23 為 Sonnet 4.6，**切換點 6/12 13:23–14:58 UTC 之間**，14:58 起的研究 session 已是 Fable 5（見 session.md）

## 已解決（binary 層，2026-06-12）

- ✅「是否只是部分 log」→ 是，VM 只見引擎層 62 行快照；完整為 App 層 audit.jsonl 612 行（HMAC 簽章）
- ✅ VM 實作 = HCS（Windows）；host-mode = `hostLoopMode:true` 確認
- ✅ 完整 egress allowlist（23 網域）；web_fetch 為獨立動態 allowlist
- ✅ Memory 後處理在引擎層；session 記錄新類型在引擎層
- ✅ 完整工具/server/slash-command 清單（system/init）；systemPrompt **模板** 46918 字元（注意：此為含 `{{cwd}}` 等未替換 placeholder 的模板長度，非渲染後實際 prompt——後經 asar 解包修正，見 prompt-schema.md / binary.md）
