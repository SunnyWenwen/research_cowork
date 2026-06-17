# Cowork Linux Sandbox VM

來源：即時內省（bash 探測），2026-06-12，agent 引擎版本 2.1.170

## 整體架構

```
Windows 主機（Claude Desktop, Electron）
 └─ Linux VM（hostname: claude, Ubuntu 22.04.5, kernel 6.8.0-124-generic, 2 vCPU, 3.8GiB RAM）
     └─ 每次 bash 呼叫 → bwrap（bubblewrap）隔離行程
         ├─ --unshare-net --unshare-pid（網路與 PID namespace 隔離）
         └─ socat 將 VM 內 TCP :3128/:1080 橋接到 unix socket → 主機端 proxy
```

三層結構：Windows → VM → bwrap。模型看到的「bash 工具」實際在最內層 bwrap 中執行。

### 生命週期：三層、三種週期（2026-06-14 實證）

**VM 不是 by session 建立**——是**一台機器一個、長期共用**的 VM，多個 session 共住其中。對應實測：`/sessions/` 下同時有 6 個 session 目錄（slug 命名，日期橫跨 6/10–6/14），但 VM uptime 僅 4h21m（當日重開）→ VM 會獨立重開，session 目錄存在持久 `/sessions` ext4 磁碟上、跨 VM 重開留存。

| 單位 | 週期 | 證據 |
|---|---|---|
| **bwrap** | 每次 bash 呼叫（秒級拋棄） | PID 1=bwrap、變數/cwd 不延續 |
| **session 目錄 + 專屬 Linux user**（`/sessions/{slug}` = `vmProcessName`） | 每個 Cowork session | HOME=`/sessions/{slug}`；user 名即 slug |
| **VM** | 每台機器一個、長期共用、獨立重開 | uptime 短但含跨日多 session 目錄 |

→ **「by session」的是目錄與專屬使用者，不是整台 VM**。跨 session 隔離靠**獨立 Linux 帳號 + `drwxr-x---`(750) 權限**：實測以本 session 帳號 `ls` 他人 session 目錄一律 `Permission denied`，只進得了自己的。

## 每次 bash 呼叫獨立的原因

每次呼叫都重新啟動一個 `bwrap --new-session --die-with-parent` 行程（ps 可見 PID 1 即 bwrap 本身），因此：

- 無 cwd / env / background job 延續（與 Claude Code 維持 shell session 不同）
- **⚠️ 「獨立」只限「行程狀態」，不含檔案系統**（2026-06-14 實證）：同 session 跨呼叫，`export` 變數/cwd/背景程式會歸零，但**裝的套件、寫的檔案會留存**（同一台活 VM）。實測：call 1 `pip install --break-system-packages cowsay` + 寫檔，call 2 仍可 import、檔案仍在。→ 不必每次重裝，只需每次重設 cwd/env/重新 activate。持久度分三層見下表（系統 `/usr` 安裝撐不過 VM 重開；掛載資料夾最持久）。
- `--unshare-pid`：看不到 VM 其他行程
- 使用者為非 root（如 `elegant-funny-keller`，每 session 隨機產生的人名 slug）
- HOME=`/sessions/{session-name}`，TMPDIR=`/sessions/{session-name}/tmp`
- 環境變數 `SANDBOX_RUNTIME=1` 可作為偵測 sandbox 的特徵

## 檔案系統：Windows ↔ VM 路徑對映

Windows 資料夾經 **virtiofs + FUSE** 掛載進 VM，根在 `/mnt/.virtiofs-root/shared/{磁碟代號小寫}/...`，再 bind 到 `/sessions/{session-name}/mnt/` 下：

| VM 路徑（mnt/ 下） | Windows 來源 | 權限 |
|---|---|---|
| `research_cowork/` | 使用者連接的資料夾（C:） | rw |
| `reseach_claude_code/` | 使用者連接的資料夾（D:） | rw |
| `outputs/` | session 暫存輸出區 | rw（**亦禁刪**） |
| `uploads/` | 使用者上傳檔案 | **ro** |
| `.auto-memory/` | Memory 目錄 | **ro**（agent 的 Write 工具走 Windows 端寫入，bash 端唯讀） |
| `.claude/projects/` | **session JSONL 目錄**（延遲快照） | **ro** |
| `.claude/skills/` | Skills 目錄 | **ro** |
| `.remote-plugins/plugin_*/` | 已安裝 plugin **內容**（host `rpm\plugin_{id}\`） | **ro** |

> **`.claude` 為「選擇性掛載」**（2026-06-14 實證）：底下**只掛 `projects` + `skills`**，同層的 `tasks`/`sessions`/`backups` **不掛**。`.remote-plugins` 也只掛各 `plugin_*/` 內容，**父層 `rpm\manifest.json`（plugin 登錄）不掛**。

#### 刻意「不」掛載（留在受保護 App 區、agent 無法存取）

`audit.jsonl`、`local_{uuid}.json`、`config.json`、`.audit-key`、`.claude/{tasks,sessions,backups}`、`rpm\manifest.json`、`spaces.json`/`artifacts.json`/`cowork-gb-cache.json` 等帳號層快取、App data 目錄本體。

**規律**：掛進來的只有「agent 跑任務需要的內容」（連接資料夾、scratch、Memory、引擎 transcript、skill/plugin 內容）；所有「管理 / 稽核 / 登錄 / 設定」檔一律不掛。連接資料夾與 `outputs` 可寫，其餘掛載多為 ro。

重要發現：

- **session JSONL 可直接從 bash 讀取**（`.claude/projects/`，唯讀），不需請使用者手動複製（詳見 [session.md](session.md)）
- Windows 端真實位置在 **Microsoft Store 套件**路徑下：`C:\Users\User\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\...`。檔案工具顯示的 `C:\Users\User\AppData\Roaming\Claude\...` 是同一位置的別名（Store App 的 Roaming 重導向）
- 檔案工具（Read/Write/Edit/Glob/Grep）只能存取已連接資料夾 + memory 目錄；嘗試讀其他路徑會被拒絕並提示用 `request_cowork_directory`
- bash 與檔案工具是兩套路徑：Windows 路徑（檔案工具）vs `/sessions/.../mnt/`（bash），系統 prompt 內附對映表

### 存取邊界的多層強制（實測 2026-06-12）

- **virtiofs 父目錄擋住**：`/mnt/.virtiofs-root/shared/c/...` 路徑在 VM 命名空間存在，但 bind 點以外的目錄（如 `Roaming\Claude\` 本體、`local-agent-mode-sessions\` 上層）一律 `Permission denied`——能存取的精確上限就是被 bind-mount 的子目錄
- **掛載請求的硬性驗證**：用 `request_cowork_directory` 請求 Cowork 內部 session 儲存目錄，**未送達使用者即被工具層拒絕**，錯誤訊息明示「transcripts、session state 刻意不可存取」，使用者同意也無法越過
  - **被擋範圍（2026-06-14 實測）= 整個 App userData 目錄**：`C:\Users\User\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\` 及其下（含 `local-agent-mode-sessions\`）——父目錄與該子目錄皆回同一拒絕。對應 bundle 內 `app.getPath("userData")` 為保護基準。
  - **拒絕原話（verbatim）**：*"That directory is Cowork's internal session storage. Tool-result files are already readable via the existing rules — read them directly. Other files there (transcripts, session state) are intentionally not accessible. Request a project folder on the user's machine instead."*
  - 訊息確認**例外**：tool-result 檔「already readable via the existing rules」→ 即 `.claude/projects` 讀回通道刻意放行（本 session JSONL 可讀的根因）。一般使用者資料夾（Downloads/專案夾等）不受此限，屬路徑式判斷。
- 同錯誤訊息透露：session 目錄下的 **tool-result 檔案有特別放行規則**可直接讀取（推測為大型工具結果外部儲存的讀回通道，細節待驗證）
- 防護共三層：agent 指引自限 → 工具層驗證 → virtiofs/ACL

## 網路限制（allowlist proxy）

bwrap 內無直接網路（`--unshare-net`），所有流量強制走 proxy：

- `HTTP_PROXY=http://localhost:3128`（HTTP CONNECT）、`ALL_PROXY=socks5h://localhost:1080`（SOCKS5）
- VM 內 socat 監聽 :3128/:1080，轉發到 unix socket（`claude-http-*.sock` / `claude-socks-*.sock`），由主機端 proxy 實際放行/攔截
- 另設 `GIT_SSH_COMMAND`（socat ProxyCommand）、`RSYNC_PROXY`、`DOCKER_*_PROXY`、`CLOUDSDK_*`、`GRPC_PROXY`，涵蓋常見工具
- 攔截方式：非 allowlist 網域連線直接失敗（curl 回 000），非 DNS 污染

實測（2026-06-12，curl）：pypi/npm/github/docs.claude.com 通；example.com/google.com 擋（000）。

**bash 能不能打 API POST？（2026-06-15 實測，問題起點：使用者問「可以用 bash 打 api post 嗎」）**

- **能，且閘門是「網域」不是「HTTP method」**：`POST https://pypi.org/` 回 **405**（伺服器層回應 → 連線確實到達，POST 沒被攔）；`POST https://httpbin.org/post` 回 **000/exit 56**（被 proxy 擋，未出 VM）。→ POST/GET/PUT 對白名單內網域皆可，白名單外一律 000。
- **白名單是 per-exact-host**：`github.com`→200，但 `api.github.com`→**000**；`files.pythonhosted.org`/`registry.npmjs.org`→200；`example.com`→000。與 `egressAllowedDomains` 列的精確主機名逐一吻合（`github.com` 在列、`api.github.com` 不在列）。
- **實務**：想用 bash curl 打第三方/SaaS API 的 POST **預設會失敗**（其主機不在那 23 條白名單）；要呼叫外部服務/抓網頁的正規路徑是 `web_fetch`/`WebSearch`/對應 MCP connector，且政策上也不應用 bash curl 繞過 web 工具。

**egress 白名單可由使用者擴充，但 (a) agent 不能自己改、(b) 改了要新 session 才生效（2026-06-15 使用者實測 + 我跨 session 驗證）**

問題起點：使用者問「白名單可以加入 api.github.com 嗎」→ 我先答「agent 不能加；個人帳號可能沒有使用者開關」。使用者隨後**調整 Cowork 設定並新開 session「GitHub API connectivity test」**，回報 `api.github.com` 通了。

- **驗證**：用 `session_info.read_transcript` 讀該 session（`local_aaa2ee6b-…`）→ 內有 `POST https://api.github.com/markdown` 回 **HTTP 200**（~0.4s，正常渲染 HTML）。確認 `api.github.com` 在新 session 從 sandbox 出得去。
- **更正先前過度宣稱**：原說「個人帳號通常沒有自由新增主機的使用者開關」**有誤**——Cowork **確有**讓使用者擴充 egress 白名單的設定。**UI 位置：File → Settings → Capability → Domain allowlist**（使用者 2026-06-15 提供）。即 `egressAllowedDomains` 那 23 條是預設底，使用者於此處新增的網域（如 `api.github.com`）會併入新 session 的清單。
- **仍成立**：「**agent 不能自行修改 egress 白名單**」不變（沙盒含容核心，見下方）。
- **印證「白名單 = session 啟動時 config 快照」**：使用者改設定後，**改設定前就已開啟的本 session 仍擋** `api.github.com`（重打多次皆 000），**新開的 session 才吃到擴充後的清單** → egress allowlist 在 session 建立當下由 App 層定版，不會對既存 session 即時生效。對應 `egressAllowedDomains` 是寫在各 session 的 `local_{uuid}.json`（per-session 狀態檔，見 binary.md）。

### 完整 egress allowlist（binary 層證實）

來源：App 層 session 狀態檔 `local_{uuid}.json` 的 `egressAllowedDomains`（23 條）。此欄位由 App 層管理（`egressAllowedDomains` 字串在 app.asar，見 [binary.md](binary.md)）：

```
套件/開發：registry.npmjs.org, npmjs.com/org(+www), yarnpkg.com,
          registry.yarnpkg.com, pypi.org, files.pythonhosted.org,
          pythonhosted.org, crates.io, index/static.crates.io,
          archive/security.ubuntu.com
工具：     playwright.download.prss.microsoft.com, cdn.playwright.dev
github：   github.com, objects.githubusercontent.com
Anthropic：*.anthropic.com, anthropic.com, claude.com, *.claude.com
```

→ 純套件管理 + 開發基礎設施 + Anthropic 自家網域，一般網站全不在內。`*.anthropic.com` 在列正是官方文章所述「經核准網域 exfiltration」風險點——故 VM 內另有 MITM proxy 只放行本 VM token（見 features.md）。

### web_fetch 的 allowlist 是動態的

`local_{uuid}.json` 另有 `webFetchAllowedUrls`（44 條），內容**恰好是本 session 經 WebSearch/web_fetch 接觸過的 URL**（含我這場查過的 how-we-contain-claude 等）。→ `web_fetch` 與 bash curl 是**兩套不同的網路限制**：curl 受 egress domain allowlist；web_fetch 走 App 層、按 search 結果動態擴充可存取 URL（回答原待研究項）。

**實證（2026-06-14）**：即時做 `web_fetch https://example.com` + `WebSearch`，再請使用者複製本 session live `local_json` → `webFetchAllowedUrls`(list,15 筆)**同時新增了** `https://example.com/`（web_fetch）**與該次 WebSearch 的多個結果 URL**（anthropic.com/product/claude-cowork、medium、tessl.io…）。→ 坐實「**web_fetch 抓取 + WebSearch 結果 URL 皆會被加入此動態白名單**」（原為推斷）。附帶再次印證掛載 JSONL 為延遲快照：當下該 fetch 未出現在 VM 可讀的 `.claude/projects` jsonl（仍停 502 行），記錄落在 App 層 local_json。

## ★ VM 內部組成（即時內省，2026-06-14）

來源：bash 在 VM rootfs 探測（`find -xdev`、`file`、`/proc/self/status`）。**修正「VM 只是執行 bash 的笨 shell」之簡化印象——VM 內有完整引擎 + 協調 daemon。**

- **VM 裝了一份完整 Claude Code 引擎**：`/usr/local/bin/claude`，237M Linux ELF、not stripped、**BuildID `2eabd56b93310e766961206f003fc2e163ec5f86`**——與 `RoamingClaude_cache/claude-code-vm/2.1.170/claude`（binary.md 記錄）**完全相同**。即我們分析的那顆 2.1.170 引擎就實裝在 VM 內。
- **coworkd 協調 daemon（新發現）**：`/run/coworkd/cli-plugin.sock` 為**活的 unix socket**（mtime 當日）→ Go 寫的常駐服務 `coworkd` 正在 VM 內執行；`/opt/cowork/cli-wrapper`（靜態連結 Go ELF，模組路徑 `coworkd/cmd/cli-wrapper`，build `20260611`）為其客戶端，經此 socket RPC 溝通。→ VM 內有執行協調層，非裸 bash。
- **沙盒由 ASRT 管理**：`@anthropic-ai/sandbox-runtime`（ASRT v0.0.43，自述「wrapping security boundaries around arbitrary processes」，bin 名 `srt`，`cli.js` 用 `SandboxManager`+`spawn` 包裹目標行程）。
- **我的 bash 行程沙盒實測**：`Seccomp: 2`（seccomp-bpf filter 啟用）、`CapEff: 0000000000000000`（capability 全砍）、`NoNewPrivs: 1`。→ 隔離為 **bwrap namespace + seccomp-bpf + cap-drop + no-new-privs** 多層疊加（補充先前僅記 bwrap 的內容）。
- **agentic loop 執行位置（2026-06-14 釐清，app.asar + 即時內省交叉證實）**：本機 session 的引擎跑在 **host**，VM 內那顆引擎是給 **VM/remote 模式** session 用的。兩顆引擎對應兩種模式：
  - App 同時備兩份 build：`binaryName = win32 ? "claude.exe" : "claude"`（`claude.exe.zst` for win32 / `claude.zst` for linux，`getVMTarget()`）。
  - `hostLoopMode` 是路徑模式開關（bundle 內 `hostLoopMode ? hostPath : /sessions/${vmProcessName}/...` 反覆出現）：true=host 路徑、false=VM 路徑。
  - 本 session 引擎自記 `cwd` 為 Windows 路徑（`C:\Users\...\outputs`）→ hostLoopMode=true。
  - **決定性證據**：本 session 的活躍引擎 transcript JSONL 持續寫入 host 的 `.claude/projects/`，而該目錄從 VM 視角是**唯讀掛載**——VM 內行程不可能寫它。既然寫得進去，寫入的引擎行程必**不在 VM**，只能是 host 端行程直接寫 host 檔案系統。（此論證靠 ro 掛載的物理約束，不靠可能被 App 翻譯的 cwd 字串。）
  - 對照：**VM/remote 模式** 引擎 = `/usr/local/bin/claude`、cwd=`/sessions/{vmProcessName}`（bundle 中 `pathToClaudeCodeExecutable:"/usr/local/bin/claude"` 即此路徑用）。
  - 修正先前對話中「無法判定 loop 在哪側」與更早「確定在 host（無據）」兩種說法。

### 何時用 VM 內的引擎（hostLoopMode 決策鏈，app.asar，2026-06-14）

```
hostLoopMode = TD()
TD() = (requireCoworkFullVmSandbox===true || forceDisableHostLoop) ? false   // → VM 引擎
     : (devOverride && env CLAUDE_FORCE_HOST_LOOP==="1")           ? true    // → host
     : lt("1143815894")                                                       // 伺服器 feature flag 決定預設
```
（`ZZ()`=full-VM 政策、`Kj()`=`forceDisableHostLoop`(預設 false)、`LQt()`=server flag、`GQt()=!TD()`。）

**hostLoopMode=false（引擎跑在 VM）的四種觸發**：
1. **企業/MDM 政策 `requireCoworkFullVmSandbox=true`**——最主要的刻意觸發；對應 config 的 `lastSeenRequireCoworkFullVmSandbox`（本機=`null`，未觸發）。
2. **`forceDisableHostLoop=true`**——本地設定，預設 false，除錯/強制用。
3. **server feature flag `1143815894` 關閉**——host-loop 為較新、flag 逐步放量的模式；未放量到的帳號回退 VM 引擎。
4. **remote / cloud-sync session**（另一軸）——sessionType `local`/`remote`/`cloud-sync`，remote 整個跑遠端機器，引擎在該端 VM（對應 `@ant/rfb-client` 顯示通道）。

**白話**：一般消費者機器（無企業政策、flag 已放量）**預設 host-loop，VM 內 claude 引擎不被用於 agent loop、處於休眠**，只有 bash 等執行型 tool 用到 VM。VM 引擎是「企業更嚴格隔離 / 遠端執行」的另一形態，非日常路徑。

## 其他觀察

- `/sessions` 為獨立 ext4 磁碟（約 10GB）且**持久**：實測含 6/10–6/13 多個舊 session 目錄、VM 當日才重開仍在 → session 目錄不隨 VM 重開消失（清除時機未定，非「session 結束即清」）；mnt 下的 Windows 資料夾本就持久（在主機）
- 存在空的 `/workspace`、`/smol` 目錄（用途待查）
- 預裝 Python 3、Node.js、常見 CLI 工具；pip 需 `--break-system-packages`
- system prompt 指示「workspace 在背景開機，可能回 Workspace still starting」→ VM 是 lazy boot

## 官方證實（2026-06-12 補充）

來源：[How we contain Claude across products](https://www.anthropic.com/engineering/how-we-contain-claude)

- **VM 實作**：Windows 用 HCS（Host Compute Service）、macOS 用 Apple Virtualization framework（解答原待研究項）
- **host-mode 架構**：agent loop 在主機執行、僅程式碼執行在 VM（原為 full-VM mode，因 VM 啟動失敗會讓 Cowork 整個不可用而改）——證實檔案工具（主機/Windows 路徑）與 bash（VM）的雙軌觀察
- **掛載模式**：read-only / read-write / **read-write-no-delete**（連接資料夾預設後者，rm 被 FUSE 擋，見 features.md 檔案刪除權限）
- **VM 內另有防禦性 MITM proxy** 攔截 api.anthropic.com 流量（只放行本 VM 的 session token）
- 憑證留在主機 keychain，VM 只拿 per-session scoped token
- 本機 MCP server 在主機執行（非 VM 內）

## 待研究

- 主機端 proxy 的完整 allowlist 清單與設定位置
- `web_fetch` 工具與 bash curl 的限制差異
- 六大隔離機制的完整清單（官方圖未逐項列出）
