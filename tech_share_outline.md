# Cowork Internals: Architecture & Comparison with Claude Code
## 投影片大綱（討論用）

> 格式：單檔 HTML｜時長：~30 分｜聽眾：聽過上次 Claude Code 那場、已懂引擎
> 🖼 = 需要示意圖｜📸 = 用本 session 實況截圖/數據當素材｜✅ = 已定稿
>
> **編號**：本版已重新整理（刪除頁已清掉、③④ 截圖併入專頁），共 **19 頁**。
> **已完成圖檔**：`diagrams/slide4_architecture.svg`（Slide 4）。

---

## 核心 thesis（貫串全場）

> **Cowork = 同一顆 Claude Code 引擎 + 外面包一層 App + 一台 sandbox VM + 一組新功能。**
> 全場的任務：上次講過引擎，這次看「殼」與「沙盒」加了什麼、又限制了什麼。

---

## Slide 1 — Cover
- 標題：Cowork Internals: Architecture & Comparison with Claude Code
- 副標：同一顆引擎，不一樣的殼
- 講者署名：（**待確認**）
- 日期：2026

## Slide 2 — Agenda（目錄）
- **Part 1 — 同一顆引擎，不一樣的殼**　*架構 + VM 安全：Cowork 怎麼把 Claude Code 包起來*
- **Part 2 — 除了架構，還差在哪?**　*工具、token、那些 Cowork 多出來的東西*
- **Part 3 — 現場跑一次**　*Live demo*

---

# Part 1 — 同一顆引擎，不一樣的殼（架構 + VM 安全）

## Slide 3 — Recap & Thesis
- 一句話 recap 上次：Claude Code = 完整的 agentic coding system（loop / context / tools / model）
- 帶出 thesis：Cowork 不是新引擎，是把同一顆 Claude Code 包進桌面 App
- 全場框架：今天看的是「外殼 + 沙盒」，不是引擎本身
- 素材來源：analysis.md 核心發現

## Slide 4 — 🖼 三層架構圖 ✅
- **圖檔：`diagrams/slide4_architecture.svg`**（已定稿，英文標籤）
- 一個 HOST MACHINE 框內含四塊：
  - App Layer：UI & panels、VM & Engine management
  - Engine Layer（藍，主角）：Claude Code 同一顆引擎 — agentic loop / session / Memory / Tools（含大量 cowork MCP 工具）
  - Project Connected Folders（綠）：Folder 1/2，主機上的真實檔案 → 以 mount(rw/ro) 掛進 VM
  - Sandbox VM（橘，虛線＝隔離）：用 bash tool 時 CLI/Code 改在 VM 內跑，不再用 host 的 bash
- App ↔ Engine 雙向箭頭；Engine →（when use bash tool）→ VM
- 後面每一段都回扣這張圖
- 素材來源：analysis.md、binary.md、sandbox.md

## Slide 5 — bash tool 改在 VM 執行的優缺點（能力邊界）
- 優點：把「在 VM 內就能完成、又不需要 host 資源」的任務交給它最安心
  - 破壞性 / 不信任的指令都關在 VM：rm -rf、誤刪也炸不到主機
  - 自包含任務跑起來很順：處理檔案、轉檔、資料清理、編譯、跑測試、裝套件
  - 可以放心讓 agent 直接執行它生成的程式碼
- 缺點：要用到 host 環境 / 資源 / 網路的就不行
  - **kubectl / docker 連不到 host 的叢集**——指令能打，但接不到 host 那側的服務（原以為是優點，其實是限制）
  - python 只能用 VM 內的 python，不是你 host 上配好的環境
  - 不能直接對 host 下 git、或操作 host 上的服務
- 一句話：自包含、不碰 host 的任務 → 丟 VM 最好；要碰 host 的 → 這條路不通
- 素材來源：tech_share.txt 你的框架 + sandbox.md

## Slide 6 — VM 掛載表（用表格說明：掛了哪些 + 各自權限）✅
- 用一張表呈現「掛載項目 → 權限」：
  | 掛載項目 | 權限 | 說明 |
  |---|---|---|
  | 連接的資料夾 | rw | 可讀寫但預設禁刪 |
  | outputs（暫存） | rw-no-delete | 可寫不可 rm |
  | uploads（上傳檔） | ro | 唯讀 |
  | memory | ro | bash 端唯讀、寫入走檔案工具 |
  | session 記錄 / skills / plugin 內容 | ro | 唯讀 |
- 補一句：刻意「不掛」的——audit、設定檔、session state（管理/稽核/登錄一律不掛）
- 規律：只掛「跑任務需要的內容」
- 素材來源：sandbox.md（路徑對映表）

---

# Part 2 — 除了架構，還差在哪?（其他差異）

## Slide 7 — Cowork 怎麼擴充 Claude Code 的能力
- 開場一句：除了架構上多包了 UI + VM，Cowork 還在 Claude Code 原有的 20 幾個原生 tool 之外，**用 MCP 的方式多掛了一大批 cowork tool**，擴充引擎的能力
- 這些 cowork MCP tool 主要分四類：
  - **① UI（對話介面）渲染用**——讓回應在介面上「長出」可互動的東西
    - `present_files`（檔案卡片）、`show_widget`（行內 SVG/HTML 視覺化）、`AskUserQuestion`（選擇題 UI）、`TaskCreate / TaskUpdate`（右側 Progress 清單）
  - **② App 功能 MCP 化**——App 上能做的操作 agent 都能代勞
    - 裝 plugin（`mcp__plugins__*`）、連 connector（`mcp__mcp-registry__*`）、要資料夾存取（`request_cowork_directory`）、解鎖刪除（`allow_cowork_file_delete`）
  - **③ 自我觀察 / 自我擴充**（細節在 Slide 11）
    - `session_info`（讀別的 session）、registry/plugins/skills 的 search + suggest（主動建議該裝什麼）
  - **④ 桌面 / 瀏覽器控制**（細節在 Slide 14）
    - `computer-use`（操作真實桌面）、`Claude in Chrome`（操作瀏覽器）
- 素材來源：tools.md、features.md（本 session 工具清單可直接佐證）

## Slide 8 — 📸 ① UI 渲染：實際使用截圖
- `present_files` 檔案卡片 ／ `show_widget` 圖（可直接用本場的架構圖當例子）／ `AskUserQuestion` 選擇題 UI ／ 右側 Progress 任務清單
- 📸 待擷取

## Slide 9 — 📸 ② App 功能 MCP 化：實際使用截圖
- 裝 plugin 或 connector 的畫面 ／ 設定 scheduled task 的畫面
- 📸 待擷取

## Slide 10 — 📸 對照基準：Claude Code 的原生 tool list
- 放上次 Claude Code 那場介紹過的「工具總覽」投影片截圖
- 用途：先讓聽眾看到 Claude Code 原生 ~20 幾個 tool 的基準，再對比下一頁 Cowork 多掛了多少
- 📸 素材：上次 deck 的工具總覽兩頁截圖

## Slide 11 — 🖼📸 deferred 爆量 + `/context` token 帳單
- 什麼都還沒裝，deferred 工具清單就一大串（本 session 實況：Chrome MCP、computer-use、notion、scheduled-tasks、registry… 數十個）
- 用 `/context` 截圖佐證：各類別 token 花費 → tool 定義先吃掉一波
- 機制：deferred 工具以 server-side tool 留在 tools 參數、不進 prompt prefix；ToolSearch 按需載入 schema
- 📸 素材：本 session deferred 清單 + `/context` 畫面（討論時一起擷取）
- 素材來源：tools.md（ToolSearch）

## Slide 12 — 有趣 / 特別的工具
- `session_info`（list_sessions / read_transcript）：讀**本機其他 session** 的記錄（Claude Code 沒有）
  - 📸 此處放 ③「自我觀察」實況截圖
- 自我擴充 suggest：registry / plugins / skills 的 search + suggest，agent 主動建議該裝什麼
- **互動 widget（雙向）**：`show_widget` 能畫互動 UI（滑桿/按鈕）；使用者操作後用 `sendPrompt()` 把結果送回對話、agent 收得到 → 「agent 畫 → 使用者操作 → agent 知道」的閉環（純文字 chat 做不到）
  - 註：閉環靠 `sendPrompt`；`read_widget_context` 實測讀不到 show_widget（見 features.md 更正）
- 素材來源：tools.md、features.md

## Slide 13 — 🖼 Artifacts
- 持久化 HTML 視圖，存在 `C:\Users\User\Claude\Artifacts\{id}\index.html`
- `window.cowork` API：callMcpTool / askClaude（Haiku）—— 渲染出來的頁面會自己抓資料
- 沙箱渲染：只放行三個 CDN（Chart.js / Grid.js / Mermaid）+ 必附 SRI
- 開啟時自動重抓 connector 資料；更新需使用者核准
- 與 widget 的差別：widget 行內即時、Artifacts 存起來跨 session 持久
- 素材來源：features.md

## Slide 14 — Memory（跨 session 記憶）
- 依 space 區分，每檔一事實 + `MEMORY.md` 索引（每 session 載入 context）
- 寫入會被引擎後處理自動改寫（補上來源 session 等欄位）；bash 端唯讀即時同步
- system prompt 內建敏感個資清單，未經同意不寫入
- 素材來源：features.md

## Slide 15 — computer-use：沒有 sandbox 的那個
- 與 bash 的對比：computer-use **直接操作真實桌面，沒有 VM 隔離**
- tier 制：瀏覽器=read（只能看）、終端/IDE=click（可點不可打字）、其他=full
- 工具優先序：專用 MCP → Claude in Chrome → computer-use（最後手段）
- 連結一律不可 computer-use 點擊（防釣魚）
- 📸 此處放 ④「桌面 / 瀏覽器控制」實況截圖：computer-use 操作桌面 / Claude in Chrome
- 素材來源：features.md

## Slide 16 — 內建 skill（Cowork 核心 skills bundle）
- 位置：`.claude/skills`（與 plugin 帶進來的 skill 分開放）
- 預設核心 bundle = **7 個**（不含使用者自行安裝的 skill-creator）：setup-cowork、consolidate-memory、schedule、docx / pdf / pptx / xlsx
- 本場挑著講：
  - setup-cowork：引導式設定（裝 plugin、連工具、試 skill）
  - consolidate-memory：整理記憶（合併重複、修正過時、修剪索引）
  - docx / pdf / pptx / xlsx：開箱即可產出 Office 文件
- 對比：brightdata / engineering / finance 等是**裝了 plugin 才有**的 skill（在 `.remote-plugins/plugin_*`）
- 註：skill ≠ connector（connector 清單裡看不到 skill）
- 素材來源：即時內省 `.claude/skills`（2026-06-21）

## Slide 17 — Cowork vs Claude Code 對照表
| 面向 | Claude Code | Cowork |
|---|---|---|
| 執行環境 | 本機 shell | VM 內 bwrap |
| 路徑 | 單一 | 雙軌（host 檔案工具 / VM bash） |
| Bash | 直接 | `mcp__workspace__bash` |
| 獨有功能 | — | Artifacts / Scheduled / computer-use / Memory by space |
| 共用 | ToolSearch / Skill / Memory / subagent / 同一引擎 | 同左 |
- 素材來源：analysis.md 差異總表

## Slide 18 — Takeaways
- Cowork 不是新引擎，是 Claude Code + 殼 + 沙盒（回扣 thesis）
- 安全模型的核心 trade-off：炸不到 host vs runtime 受限
- 能力邊界決定用法：哪些任務丟 Cowork、哪些回 Claude Code
- （視情況補 1-2 點）

---

# Part 3 — 現場跑一次

## Slide 19 — Demo
- demo 內容：（**待確認要 demo 什麼**）
- 候選：Artifacts 建立、`/context` 看 token、bash 在 VM 起服務、雙向 widget…

---

## 待確認清單
1. 封面講者署名
2. 待擷取截圖：Slide 8/9（①②）、Slide 10（原生 tool list）、Slide 11（deferred + /context）、Slide 12（session_info）、Slide 15（computer-use）
3. Demo 具體要跑什麼

---

## 特別工具盤點（是否都介紹到）
- ✅ present_files / show_widget / AskUserQuestion / Task progress（① UI，Slide 7+8）
- ✅ plugins / registry / request_cowork_directory / allow_cowork_file_delete（② App，Slide 7+9；刪除權限也在 Slide 6）
- ✅ session_info（Slide 12）
- ✅ registry/plugins/skills 的 suggest 自我擴充（Slide 12）
- ✅ show_widget 互動 + sendPrompt 雙向（Slide 12）；read_widget_context 對 show_widget 無效（已更正，見 features.md）
- ✅ Artifacts + window.cowork API（Slide 13）
- ✅ Memory（Slide 14）
- ✅ computer-use / Claude in Chrome（Slide 15）
- ✅ 內建 skill：setup-cowork / schedule / skill-creator / consolidate-memory（Slide 16）
- ⏭ 次要、暫不單獨講：Dispatch / remote session、web_fetch（受控抓網頁）、cowork-onboarding role picker、read_me（visualize 內部）
