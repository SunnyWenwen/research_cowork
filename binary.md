# Desktop App 程式碼與資料目錄（binary 層）

來源：使用者手動複製 App 與 RoamingClaude 資料進 `research_cowork/`，bash 分析，2026-06-12。App 版本 1.11847.5.0（MS Store, `Claude_pzs8sxrjxfjjc`），引擎 2.1.170。

## 複製進來的結構

```
research_cowork/
├─ Claude_1.11847.5.0_x64__pzs8sxrjxfjjc/   # App 本體（Electron）
│  └─ app/
│     ├─ claude.exe (213M)                  # Electron 主程式（Windows）
│     ├─ resources/app.asar (25M)           # ★ Cowork App 層邏輯（UI/orchestration）
│     └─ locales/, *.dll, icudtl.dat ...
└─ RoamingClaude_cache/                       # = AppData\Roaming\Claude\
   ├─ claude-code/2.1.170/claude.exe (232M)   # 引擎 binary（Windows 版）
   ├─ claude-code-vm/2.1.170/claude (237M)    # ★ 引擎 binary（Linux ELF，在 VM 內跑的就是它）
   ├─ local-agent-mode-sessions/              # ★ 所有 session 記錄（見 session.md）
   ├─ spaces/.../memory/                       # Memory
   ├─ config.json                             # App 設定（含 OAuth token cache，機敏）
   ├─ claude_desktop_config.json              # Cowork 偏好（coworkUserFilesPath 等）
   └─ logs/, sentry/, Cache/ ...
```

`claude-code-vm/2.1.170/claude`：ELF 64-bit、**not stripped**（符號表在）、BuildID `2eabd56b...`。這顆就是我 bash 工具背後執行的引擎。

## 三層架構（binary 證據確認）

用特徵字串在「引擎 binary」vs「App 層 app.asar」分別 grep，乾淨地分出歸屬：

| 機制 / 字串 | 引擎 binary (`claude-code-vm`) | App 層 (`app.asar`) | 歸屬結論 |
|---|---|---|---|
| `local-agent` | 30 | — | 引擎（entrypoint） |
| `queue-operation` | 4 | — | **引擎層** session 記錄 |
| `last-prompt` | 10 | — | **引擎層** |
| `deferred_tools_delta` | 11 | — | **引擎層**（ToolSearch 機制） |
| `originSessionId` / `node_type` | 5 / 4 | — | **引擎層**（Memory 後處理在引擎做，證實 features.md 推斷） |
| `SANDBOX_RUNTIME` | 2 | — | 引擎/runtime |
| `_audit_hmac` | 0 | 1 | **App 層**（稽核簽章） |
| `hostLoopMode` | 0 | 8 | **App 層**（host-mode 開關） |
| `egressAllowedDomains` | 0 | 5 | **App 層**（網路 allowlist 管理） |
| `lastSeenRequireCoworkFullVmSandbox` | — | 1 | **App 層**（full-VM 模式殘留旗標） |
| `VirtualMachine` | — | 19 | **App 層**（VM 生命週期管理） |

結論：**Cowork = App 層（Electron, app.asar：UI、VM 管理、egress、稽核、host-loop）＋ 引擎層（Claude Code 2.1.170：agentic loop、session 記錄、Memory、工具）**。`queue-operation`/`last-prompt`/`deferred_tools_delta` 在引擎 binary 內 → 這些是 Claude Code 引擎本身的記錄類型，**新版 Claude Code（≥2.1.170）很可能也有**（回答 session.md 待驗證項；姊妹專案研究的 2.1.72 可回頭比對）。

## 雙平台同源驗證：Windows CLI ↔ Linux 引擎 ELF（同為 2.1.170）

來源：即時內省 bash 比對，2026-06-13。比對對象：
- **Windows standalone CLI**：專案 root 的 `2.1.170`（PE32+ console x86-64, 232M, `@anthropic-ai/claude-code`）＝使用者從 `C:\Users\User\.local\share\claude\versions\2.1.170` 複製進來；內容等同 cache 內已記錄的 `claude-code/2.1.170/claude.exe`。
- **Linux 引擎 ELF**：`RoamingClaude_cache/claude-code-vm/2.1.170/claude`（VM 內實際執行的引擎）。

**目的**：原訂優先項是 2.1.70 vs 2.1.170 版本差異比對，但專案內目前**無 2.1.70** binary（姊妹專案也未保存 binary，232M 多半被 .gitignore）。改做同版本跨平台比對，回答另一個問題：standalone CLI 與 VM 引擎是否為同一 codebase？

| 量測 | Windows CLI | Linux ELF | 判讀 |
|---|---|---|---|
| 獨立 `2.1.170` token 數 | 106 | 106 | 同版本 |
| `ISSUES_EXPLAINER`（CLI 簽名常數） | 有 | 有 | 同 codebase |
| `queue-operation` | 4 | 4 | 引擎記錄類型，**兩平台皆有** |
| `last-prompt` | 10 | 10 | 同上 |
| `deferred_tools_delta` | 11 | 11 | ToolSearch 機制，**兩平台皆有** |
| `total_deferred_tools` | 2 | 2 | 同上 |
| `attachmentSent` | 4 | 4 | 引擎層 |
| `originSessionId` / `node_type` | 5 / 4 | 5 / 4 | Memory 後處理，引擎層 |
| `isSidechain` / `ToolSearch` / `auto_memory` | 39 / 45 / 2 | 39 / 45 / 2 | 全數一致 |
| App 層字串（`hostLoopMode`/`spSectionPrompts`/`spVariantPrompts`/`egressAllowedDomains`/`marigold`/`starling`/`_audit_hmac`/`coworkUserFilesPath`/`vmEgressPolicy`/`directMcpHost`） | **全 0** | **全 0** | App 層機制不在引擎 binary 內 |

**字串集合重疊**：長字串（≥20 字元）去重後，Windows 與 ELF 交集 **94,625** 條；各自 only ~24k/22k 條經抽樣全為（a）每次 build 不同的 minifier 變數名（`${H}`/`${q}`/`${$}` 同一段程式）、（b）平台原生 runtime 字串（V8/Node/libuv C++，如 `eval_callback`）、（c）CRLF/LF 差異，**非應用邏輯差異**。

**結論**：
1. Cowork VM 引擎與 standalone Claude Code CLI 是**同一份 JS bundle 的雙平台 build**（同 2.1.170），徹底坐實「Cowork 底層即 Claude Code 引擎」的核心論點。
2. `queue-operation`/`last-prompt`/`deferred_tools_delta`/`node_type` 等先前判定為「引擎層」的字串，在**獨立 Windows CLI 也存在** → 確定是 Claude Code 引擎核心功能，**非 Cowork 專屬**（強化 session.md 推斷）。
3. App 層字串在兩個引擎 binary 皆 0，再次乾淨切分：host-loop/egress/audit/spPrompts 系統只活在 app.asar。
4. **未解**：本比對為同版本，無法回答「這些記錄類型是否為 2.1.170 新增」——仍需 2.1.70（或姊妹專案 2.1.72）較舊 binary 才能做版本 diff。

## 版本 forward diff：2.1.170（Cowork 引擎版）→ 2.1.177（較新 CLI）

來源：即時內省 bash 比對，2026-06-13。使用者複製 `C:\Users\User\.local\share\claude\versions\2.1.177`（PE32+, 245M）進專案 root。**注意方向**：177 比 Cowork 目前引擎 170 **更新**，因此這是 forward diff（看 170 之後新增了什麼），**仍無法**回答「queue-operation 等是否為 170 新增」的 backward 問題。

### 方法學教訓（重要）

`comm` 對「可讀長字串」做 X-only 差集會產生**大量假陽性**：minifier 每次 build 變數名不同、長字串被 `\r`/換行截斷位置不同，都會讓同一段程式「看起來像新增」。例如初步 comm 列出 `"type":"adaptive"`、`ThinkingConfigAdaptive`、`CLAUDE_CODE_USE_POWERSHELL_TOOL` 像是 177 新功能，但**逐字串計數**證明三者在 170 已存在（11=11、14=14、13=13）。**可靠方法 = 抽取識別字 token（`[A-Za-z_]\w{6,40}`）做差集 + 對候選字串做 170/177 計數驗證**，只採 170 計數為 0 者。

### 引擎特徵字串：跨版本穩定

| 字串 | 2.1.170 | 2.1.177 | 判讀 |
|---|---|---|---|
| `queue-operation` / `last-prompt` | 4 / 10 | 4 / 10 | 不變 |
| `deferred_tools_delta` / `total_deferred_tools` | 11 / 2 | 11 / 2 | 不變 |
| `attachmentSent` / `attachment_` | 4 / 17 | 4 / 17 | 不變 |
| `originSessionId` / `node_type` | 5 / 4 | 5 / 4 | 不變 |
| `ToolSearch` / `isSidechain` | 45 / 39 | 48 / 38 | 微幅（用法增減，機制不變） |
| `spVariantPrompts` / `hostLoopMode`（App 層） | 0 / 0 | 0 / 0 | standalone CLi 從不含 App 層 |

→ 核心 session/ToolSearch/Memory 機制 170→177 **無結構性變動**。

### 2.1.177 真正新增（170 計數為 0，已驗證）

| 新 token | 170→177 | 推斷功能 |
|---|---|---|
| `v2_subagent` | 0→2 | **subagent v2 架構** |
| `teammateAgentId` / `subagent_teammate_control_chars` | 0→3 | **「teammate」協作 agent** 概念 |
| `subagent_fork_remote_isolation` | 0→2 | subagent 遠端隔離 fork |
| `pending_background_agent_count` | 0→2 | **背景 agent**（非同步執行） |
| `restrictedAgentModel` / `normalizeAgentType` | 0→3 | agent 類型/模型限制 |
| `ArtifactTool` / `ARTIFACT_TOOL_NAME` | 0→8 | **Artifact 工具下沉進引擎**（170 時 Artifacts 純 App 層）|
| `ProjectsTool` / `allow_projects_tool` / `CLAUDE_PROJECT_TOOL` | 0→3/7 | **Projects 工具** |
| `AgentsView` / `agentsView` | 0→ | Agents 檢視 UI |
| `CLAUDE_IN_CHROME_DOMAIN_RULE_TOOL` | 0→ | Claude in Chrome 網域規則工具 |
| `evictSentSkillNames` / `skills_sync_extract_retry` | 0→2 | skill 同步/驅逐機制強化 |
| `tengu_malformed_tool_use_retry_outcome` / `_clean_retry` | 0→2 | tool-use 解析失敗重試遙測 |
| `MYTHOS_ID` / `MYTHOS_NAME` / `Project Glasswing` | 0→11/9 | **模型世代遷移文件** |

### 兩個延伸發現

1. **`output_config.effort` 範圍確定（回答 analysis.md 研究方向 #5）**：177 bundle 內文件明載 effort 支援 **`low` → `xhigh`（亦寫作 `x-high`）→ `max`**；並有守則「effort 為 `xhigh`/`max` 時須設 `max_tokens ≥ 64000`，否則輸出截斷」。此參數 170 已存在（計數 4→9，文件擴充）。

2. **模型世代鏈：Mythos Preview → Fable**：177 文件描述新模型「**succeeding the invitation-only Claude Mythos Preview (`claude-mythos-preview`)**」，遷移工程代號 **Project Glasswing**（`{{MYTHOS_ID}}` → `{{FABLE_ID}}`）。佐證先前 session 觀察到的 Fable 5 與本機記憶（Fable 5 因出口管制暫停）。注意：**interleaved scratchpad「Mythos Preview migrators only」不支援**，inter-tool reasoning 改走 thinking。

**整體結論**：Cowork 目前用的引擎 2.1.170 與最新 CLI 2.1.177 在 session/工具搜尋/Memory 等底層機制**完全一致**；177 的增量集中在 **agent 協作層**（v2 subagent / teammate / background agent）與**工具面**（ArtifactTool、ProjectsTool 下沉進引擎）。這暗示未來 Cowork 升級引擎後，Artifacts/Projects 可能從 App 層協調改為引擎原生工具。

## App 設定檔重點（非機敏部分）

`claude_desktop_config.json`：
- `coworkUserFilesPath: C:\Users\User\Claude` — Cowork 預設輸出根（Artifacts、Scheduled 都在此下）
- `coworkScheduledTasksEnabled / coworkWebSearchEnabled: true`、`sidebarMode: task`
- `bypassPermissionsGateByAccount: {帳號: false}`、`coworkModelAutoFallbackByAccount: {帳號: true}` — 模型自動降級開啟
- `remoteToolsDeviceName: sunny`

`config.json`：`updaterLastSeenVersion: 1.11847.5`、`lastSeenRequireCoworkFullVmSandbox: null`、含 `oauth:tokenCache`（加密，不分析）；另有 `dxt:allowlistEnabled/Cache/LastUpdated:{orgId}`（擴充白名單，org 範圍）、`remote_uploads_migration_done`/`remote_marketplace_migration_done`（遠端功能遷移旗標）。

UUID 身分對應（從 config + audit + dxt URL 確認）：
- `bc71ab19-...` = **ownerAccountId（帳號）**（`cowork-enabled-cli-ops.json` 證實）
- `9de92944-...` = **organizationId（組織）**（修正先前「環境/裝置層」——`extensions-blocklist.json` 的 `/api/organizations/9de92944.../dxt/blocklist` 與 config 的 `dxt:allowlist:9de92944...` 證實，2026-06-14）
- `219d9c7e-...` = **spaceId**（Memory 依此區分；`spaces.json` 為 space 登錄表）
- `local_{uuid}` = Cowork session；`f98841bb...`(cliSessionId) = 引擎 SDK session

## App data 目錄其他檔案（2026-06-14 測繪）

來源：使用者 robocopy 刷新 `RoamingClaude_cache` 後 bash 解析。頂層大多為 Electron/Chromium 標準產物（Cache/GPUCache/IndexedDB/Local Storage/Crashpad/DIPS/Dictionaries/Network/Session Storage…—非 Cowork 機制）。以下為 Anthropic/Cowork 專屬、有機制意義者：

### 頂層
- `extensions-blocklist.json`：**DXT 擴充（plugin）黑名單**，從 `claude.ai/api/organizations/{orgId}/dxt/blocklist` 拉取（org 範圍治理；配合 config 的 `dxt:allowlist*` 白名單）。
- `git-worktrees.json`：git worktree 追蹤（`{worktrees:{}, schemaVersion:2}`），對應 Agent `isolation:worktree`。
- `buddy-tokens.json`：**每日 token 用量計數**（`{tokens-today:{date,tokens}}`，非祕密；quick/buddy 視窗用）。
- `ant-did`：Anthropic device id（base64 → 一個 UUID）。
- `cowork-enabled-cli-ops.json`：僅 `ownerAccountId`。
- `pending-uploads/`：待上傳圖片佇列（對應 remote_uploads 機制）。

### `local-agent-mode-sessions/{accountId}/{orgId}/` 層的快取 json（除 `local_*.json` 外）
- **`cowork-gb-cache.json` = GrowthBook feature-flag 快取**：`cachedGrowthBookFeatures` 含大量 `tengu_*` 旗標；**Fable 5 停用訊息存於此**（`tengu-model-error-overrides → claude-fable-5: "Claude Fable 5 is currently unavailable…"`）。→ 模型可用性與功能開關由此份伺服器下發 flag 控制（與 host-loop 的數字 flag `lt("1143815894")` 為不同命名體系）。
- **`cowork-clientdata-cache.json`**：bootstrap `client_data` 快取；`cwkCfgKeyForModel: {apiModel:"claude-sonnet-4-6[1m]", cwkCfgKey:null}` → 證實目前模型 Sonnet 4.6、prompt 變體 key = null（用 base，非 marigold），對上「Sonnet 無 send_user_message」結論。
- **`cowork-policy-limits-cache.json`**：伺服器下發合規限制（`restrictions.allow_cobalt_plinth:false`、`enforce_web_search_mcp_isolation:false`、`compliance_taints:[]`）。
- **`spaces.json`**：space 登錄表（每筆 `id/name/folders/projects/links/origin/時間`；name 常為資料夾路徑）→ spaceId ↔ 資料夾對映，Memory 分區依據。
- **`artifacts.json`**：artifact 登錄表（`id/name/description/createdBySessionId/lastModifiedBySessionId/mcpTools/isStarred`）。

注意：上述 cache 檔在複製當下若正被 App 寫入，會得到**截斷的 JSON**（本次 gb-cache/clientdata/spaces/artifacts 皆部分截斷，僅開頭可靠）。

## ★ app.asar 解包分析（2026-06-13）

來源：`npx asar extract` 解包後 grep `asar_extracted/.vite/build/index.js`（13MB minified bundle）。

### package.json 關鍵依賴

| 套件 | 版本 | 意義 |
|---|---|---|
| `@anthropic-ai/claude-agent-sdk` | `0.3.170` | 與引擎版本 2.1.170 對應 |
| `@anthropic-ai/claude-agent-sdk-future` | `0.3.167-dev.20260606` | 測試中的下一版 SDK |
| `@anthropic-ai/conway-client` | `0.2.0-dev` | 不明代號（內部專案） |
| `@ant/rfb-client` | — | RFB/VNC 客戶端 → **Remote session 的遠端桌面顯示** |
| `@ant/imagine-server` | — | 圖像生成 server |
| `@ant/cowork-win32-service` | — | `cowork-svc.exe` 的本體 |
| `@ant/computer-use-mcp` | — | computer-use MCP 內部套件 |
| `electron` | `41.6.1` | Electron 框架版本 |

其他重要資源：`smol-bin.x64.vhdx`（VM image）、`cowork-svc.exe`（Windows VM 服務）、`chrome-native-host.exe`（Chrome 擴充原生通訊）

---

### System Prompt 組裝邏輯（JS 原始碼，函式層）

`local_{uuid}.json` 的 `systemPrompt` 欄位是**原始模板**（非渲染後版本）。渲染在每次 session 啟動時由 App 層執行，依序替換以下 placeholder：

| Placeholder | 替換為 |
|---|---|
| `{{promptCacheBoundary}}` | `ViA`（Anthropic prompt cache boundary 字串） |
| `{{currentDateTime}}` | `Yfr()` 當前日期時間 |
| `{{currentTimezone}}` | `Intl.DateTimeFormat().resolvedOptions().timeZone` |
| `{{cwd}}` | `/sessions/{sessionName}`（local）或遠端路徑 |
| `{{cwd}}/mnt/uploads` | 指定 uploads 路徑（若存在） |
| `{{workspaceFolder}}` | 第一個連接資料夾的 VM 路徑 |
| `{{userSelectedFolders}}` | 所有連接資料夾的格式化清單 |
| `{{skillsDir}}` | `/sessions/{name}/mnt/.claude`（VM 路徑） |
| `{{modelName}}` | 模型顯示名稱（如 "Claude"） |
| `{{accountName}}` | 使用者帳號名稱 |
| `{{emailAddress}}` | 使用者 email |
| `{{workspaceContext}}` | 檔案存取情況描述（有無連接資料夾） |
| `{{folderSelected}}` | `"yes"` 或 `"no"` |

替換後：
1. 呼叫 `generateSkillsSystemPrompt()` 附加 `<skills>` 區塊
2. Memory files 內容附加（由引擎層處理，非 App 層）

**修正先前記錄**：`prompt-schema.md` 中「完整 rendered systemPrompt = 46918 字元」是錯誤的——46918 是模板長度，包含未替換的 `{{cwd}}`、`{{currentDateTime}}` 等佔位符。實際渲染後的 prompt 較長。

---

### spVariantPrompts 選擇邏輯（`VRr` 函式）

```javascript
function VRr(clientConfig, spVariantPrompts, defaultKey) {
  // key 來源優先序：
  const key = clientConfig?.cwk_cfg     // 1. 伺服器下發的 feature flag
           ?? clientConfig?.cowork_sp_variant  // 2. session 本地設定
           ?? defaultKey                // 3. 預設 key
           ?? undefined;
  
  if (typeof key !== "string") return {key:null, variant:null, reason:"no_key"};
  
  // 先查硬編碼測試變體（xYA）
  if (Object.hasOwn(xYA, key)) { ... }
  
  // 再查 spVariantPrompts[key]
  const variant = spVariantPrompts[key];
  
  // 驗證：replace 模式必須包含 {{promptCacheBoundary}}
  if (variant.mode === "replace" && !variant.text.includes("{{promptCacheBoundary}}"))
    return {key, variant:null, reason:"missing_boundary"};
  
  return {key, variant: {mode, text}};
}
```

- **`cwk_cfg_key` 由伺服器 bootstrap API 下發**：`GET {apiHost}/api/claude_cli/bootstrap?entrypoint=local-agent&model={model}`（Auth: `Bearer {token}`, `anthropic-beta: oauth-2025-04-20`），回傳 `{client_data, cwk_cfg_key}`
- 這是**伺服器控制的 feature flag**：Anthropic 可遠端控制每個帳號使用哪個 prompt 變體
- `xYA`（硬編碼測試變體）：`test_replace`（replace 模式，含 `{{promptCacheBoundary}}`）和 `test_footer`（append 模式）
- `mode` 只有 `"replace"`（替換整個 systemPrompt）和 `"append"`（附加到尾端）兩種
- `'marigold'` = Fable 5 的 variant key，key 的命名是花卉代號

---

### 稽核 HMAC 簽章流程（`SFe` + `PRr`）

```javascript
// SHA-256 chained HMAC
function SFe(key, prevHmac, recordJSON) {
  return crypto.createHmac("sha256", key)
               .update(prevHmac)  // 上一筆記錄的 HMAC（初始值 V$ = ""）
               .update(recordJSON)
               .digest("hex");
}

class PRr {
  sign(record) {
    const {_audit_hmac, ...rest} = record;
    const json = JSON.stringify(rest);
    const hmac = SFe(this.key, this.prevHmac, json);
    this.prevHmac = hmac;  // 更新鏈狀態
    return JSON.stringify({...rest, _audit_hmac: hmac});
  }
  
  static verify(key, lines) { /* 驗證整個鏈 */ }
}
```

- **鏈式 HMAC**：每筆 record 的 HMAC 依賴前一筆的 HMAC → 類 blockchain 結構，任一筆竄改會導致後續全部失效
- `.audit-key` = HMAC 金鑰（binary，由 `ORr(auditDir)` 讀取）
- `YRr(auditDir)` 初始化 audit logger（winston）+ 讀 key + 恢復上次的 `prevHmac`（從 jsonl 末尾掃描）
- `PRr.verify(key, lines)` 可完整驗證整個稽核檔

---

### Egress Allowlist 注入（`resolveVmAllowedDomains`）

```javascript
resolveVmAllowedDomains(egressAllowedDomains, otelConfig) {
  const policy = Nt().vmEgressPolicy();  // 企業/org 管理員覆寫
  const domains = policy ? yuA(policy) : egressAllowedDomains;
  return Pwr(domains, otelConfig);  // 可附加 OTLP endpoint host
}
```

- **企業可覆寫**：`vmEgressPolicy()` 若有值（MDM 設定），忽略 session 的 `egressAllowedDomains`
- `Pwr()` 額外邏輯：若有 OTLP endpoint，自動將其 hostname 加入 allowlist
- 最終值（`Ca`）傳入 `canUseTool` 作為 WebFetch 的 URL 驗證依據

---

### model_refusal_fallback 處理邏輯（3 種 direction）

```javascript
// App 層攔截引擎送來的 model_refusal_fallback 記錄
if (record.subtype === "model_refusal_fallback") {
  const direction = record.direction;  // "retry" | "revert" | "sticky"
  
  if (direction === "retry")   { session.model = normalize(record.fallback_model); }
  if (direction === "revert")  { session.model = session.preRefusalModel; }
  if (direction === "sticky")  { session.model = normalize(record.fallback_model); }
  // "revert"/"sticky" 清空 preRefusalModel
}

// eQ()：normalize model name（移除 [1m] 等後綴和 -YYYYMMDD 日期）
// yy()：僅移除 -YYYYMMDD 日期後綴
```

- `"retry"`：本輪改用 fallback model 重試，下輪可能回復
- `"revert"`：切回原始 model（Fable 5 安全審查通過後？）
- `"sticky"`：永久切換到 fallback model
- `coworkModelAutoFallbackByAccount: {帳號: true}`（config.json）確認這個帳號的自動降級功能已開啟

---

### 引擎 Session Config（`Qi` 物件）

App 層透過 Agent SDK 呼叫引擎時傳入的完整 config：

```javascript
Qi = {
  cwd: `/sessions/${sessionName}`,
  model: rA,               // 解析後的模型名稱
  effort: ...,             // extended thinking budget
  maxTurns: ljA(sessionType),  // 依 session 類型不同
  pathToClaudeCodeExecutable: "/usr/local/bin/claude",  // VM 內路徑（sub-agent 用）
  getOAuthToken: () => ...,
  getHostAuthToken: async () => ...,
  tools: ["Task","Bash","Glob","Grep","Read","Edit","Write",
          "NotebookEdit","WebFetch","WebSearch","Skill",
          "REPL","JavaScript","AskUserQuestion","ToolSearch",
          ...SessionTypeSpecific],
  allowedTools: [...],  // 預核准工具（無需 permission_request）
  canUseTool: async (toolName, input, ctx) => { ... },  // 工具執行前驗證
  ...
}
```

- **`tools` 清單含 `REPL`、`JavaScript`、`NotebookEdit`**：這些 Claude Code 工具在 Cowork 系統中實際注冊，但 system prompt 明示不使用（由行為規範過濾，非技術層面禁止）
- `pathToClaudeCodeExecutable: "/usr/local/bin/claude"` = VM 內路徑，用於 sub-agent（Agent 工具）spawn
- `effort` 對應 extended thinking budget；`maxTurns` 依 session 類型（排程任務 vs 互動式）有不同上限

---

### VM 啟動流程（Windows HCS）

```javascript
// 1. 架構檢測
function HBA() { return process.arch === "x64" ? "x64" : "arm64"; }

// 2. 複製 VM image（smol-bin.x64.vhdx → bundle 目錄）
await pipeline(readStream("smol-bin.x64.vhdx"), writeStream("smol-bin.vhdx"));
// 若 EBUSY/EACCES/EPERM（VM 已在跑）→ skip copy

// 3. 設定 Windows VM service
await f.configure();

// 4. 啟動 VM
await f.startVM(sessionDir, mountConfig, agentConfig, "gvisor", probeTarget);
// runtime: "gvisor"（非原生 Linux kernel，有額外隔離層）

// 5. 等待 VM API 可達
```

**VM 元件 checksum（Windows x64）**：
- `rootfs.vhdx`：`859e4e42...`（0-80%）
- `vmlinuz`：`588bfd1d...`（80-90%）
- `initrd`：`8815a253...`（90-100%）

VM 下載 URL：`https://downloads.claude.ai/vms/linux/{arch}/{sha}`（sha=`c9b42670...`）

- `"gvisor"` 是 runtime 類型，表明 Cowork 在 HCS VM 內用 gVisor（user-space kernel）作為額外安全隔離——比 native Linux 更強的 sandboxing
- `f` = Windows VM service（`cowork-svc.exe`）的 IPC 介面
- HCS 不可用時：錯誤碼 `hcs_not_available`，顯示缺少的服務清單

---

---

### ★ spSectionPrompts 機制（"starling" 系統，2026-06-13）

來源：`asar_extracted/.vite/build/index.js` 分析，feature flag `lt("124685897")`。

**spSectionPrompts vs spVariantPrompts 的本質差異：**

| | spVariantPrompts（"marigold"） | spSectionPrompts（"starling"） |
|---|---|---|
| 作用對象 | **主 agent** system prompt | **sub-agent**（Agent 工具生成的 subagent）system prompt |
| 範圍 | 整份 system prompt replace/append | section 級別注入，選擇性覆寫特定 section |
| 控制鍵 | `cwk_cfg_key`（bootstrap API 下發） | 同一個 `spSectionPrompts` dict，不同 section key |
| 代號 | marigold（花卉命名） | starling（鳥類命名，`lt("124685897")` 功能旗標） |

#### `Cc` 常數物件（14 個 section key 對照）

```javascript
Cc = {
  cuSafetyRules:           "cu_safety",
  cuSafetyRulesCuOnly:     "cu_safety_cuonly",
  cuOptedOutStub:          "cu_optout_a",
  cuOptedOutSettings:      "cu_optout_b",
  dispatchOrchestratorBase:"dispatch_base",
  scheduledTasks:          "scheduled_tasks",
  dispatchChildFsHostLoop: "dispatch_child_fs_hl",
  dispatchChildFsVm:       "dispatch_child_fs_vm",
  subagentEnvHostLoop:     "subagent_env_hl",
  subagentEnvVm:           "subagent_env_vm",
  htmlArtifacts:           "html_artifacts",
  hostFsSkeleton:          "skeleton_home",
  computerUseMain:         "computer_use",
  dispatchSeedGreeting:    "dispatch_seed_greeting",
}
```

- `cu_safety*`：computer-use 安全規則（三種：通用 / 僅 CU / 已 opt-out）
- `dispatch_*`：Orchestrator（dispatch）與子任務（child）的 system prompt section
- `subagent_env_*`：sub-agent 環境說明（host-loop 模式 vs VM 沙盒模式各一份）
- `html_artifacts`、`computer_use`：特定功能的 section
- `skeleton_home`：host-loop 模式的檔案系統框架

#### `Du()` — Section 選擇器

```javascript
function Du(spSectionPrompts, sectionKey, hardcodedDefault) {
  if (!lt("124685897")) return hardcodedDefault;  // feature flag 未開則用硬編碼預設
  const override = spSectionPrompts?.[sectionKey];
  if (typeof override !== "string" || override.trim().length === 0) {
    D.debug(`[systemPromptSections] ${sectionKey}: using default`);
    return hardcodedDefault;
  }
  return override;
}
```

- `lt("124685897")`：starling 系統的 feature flag（Anthropic 遠端控制）
- flag 關閉時直接回傳 hardcoded 預設文字，等同無 spSectionPrompts
- `spSectionPrompts` 是鍵值對，key = `Cc` 中的字串值（如 `"cu_safety"`）

#### `Lk()` — Section 渲染器

```javascript
function Lk(text, vars, sectionKey) {
  // 處理 {{#if var}}...{{else}}...{{/if}} 條件式（不支援巢狀）
  let result = text.replace(
    /\{\{#if (\w+)\}\}([\s\S]*?)(?:\{\{else\}\}([\s\S]*?))?\{\{\/if\}\}/g,
    (_, varName, ifBlock, elseBlock) => vars[varName] ? ifBlock : (elseBlock ?? "")
  );
  if (result.includes("{{#if ")) {
    D.warn(`[systemPromptSections] ${sectionKey}: unresolved {{#if}} — nesting not supported`);
  }
  // 替換 {{key}} 變數
  for (const [key, val] of Object.entries(vars)) {
    if (typeof val === "string") result = result.replaceAll(`{{${key}}}`, val);
  }
  return result;
}
```

- 支援條件式（`{{#if}}`/`{{else}}`/`{{/if}}`），但**不支援巢狀**
- 條件後再替換 `{{key}}` 變數
- 比主 prompt 的 `{{placeholder}}` 更豐富的模板語法

#### `Jfr()` — Sub-agent 環境 section 生成

```javascript
function Jfr({vmProcessName, hostLoopMode, hostCwd, spSectionPrompts}) {
  const vmCwd = `/sessions/${vmProcessName}`;
  
  // 依 hostLoopMode 選不同的環境說明文字
  const defaultText = hostLoopMode
    ? `## Cowork environment\n\nYou are running as a subagent inside a Cowork session on the user's machine. ` +
      `File operations reach the user's real filesystem (working directory \`${hostCwd ?? vmCwd}\`), ` +
      `so only read or write inside folders the user has attached to this session. ` +
      `Shell commands run via \`mcp__${VE}__${OB}\` in an isolated Linux environment where those folders are mounted under \`${vmCwd}/mnt/\`.`
    : `## Cowork environment\n\nYou are running as a subagent inside a Cowork session. ` +
      `Shell commands execute in an isolated Linux sandbox rooted at \`${vmCwd}\` — ` +
      `files created there (or under \`/tmp\`) exist only in the sandbox, not on the user's real computer. ` +
      `User-attached folders are mounted under \`${vmCwd}/mnt/\`.`;
  
  const sectionKey = hostLoopMode ? Cc.subagentEnvHostLoop : Cc.subagentEnvVm;
  const text = Du(spSectionPrompts, sectionKey, defaultText);
  return `\n\n${Lk(text, {vmCwd, hostCwd: hostCwd ?? vmCwd, workspaceBash: `mcp__${VE}__${OB}`}, sectionKey)}`;
}
```

**關鍵洞察**：sub-agent（Agent 工具生成的）收到的 system prompt 包含一個由 `Jfr()` 生成的環境說明 section，明確告知：
- 自己是「Cowork 內的 subagent」
- host-loop 模式（`hostLoopMode: true`）：說明可存取使用者真實檔案系統
- VM 模式：說明只有沙盒，所有檔案變化都在 sandbox 內

---

### ★ directMcpHost.js 分析（MCP 協議層，2026-06-13）

來源：`asar_extracted/.vite/build/mcp-runtime/directMcpHost.js`（571KB）。

**MCP 協議版本**：
```javascript
LATEST_PROTOCOL_VERSION = "2025-11-25";
SUPPORTED