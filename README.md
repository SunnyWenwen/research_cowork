# research_cowork

逆向研究 Claude **Cowork**（Claude 桌面 App 的 agent 模式，研究預覽版）的內部機制筆記。

研究方法：即時內省（agent 觀察自身運行環境）＋ 真實 session 記錄 ＋ 官方文件 ＋ 桌面 App / 引擎 binary 分析。所有個人識別碼（帳號/組織/space UUID、裝置名、session id）已以佔位符去識別化。

## 文件

- `analysis.md` — 索引與總結
- `tools.md` — 工具系統（pre-loaded/deferred、ToolSearch、Skill、MCP）
- `sandbox.md` — Linux sandbox VM（mount、網路、bwrap/ASRT、host-loop、生命週期）
- `session.md` — session 機制與 JSONL 格式
- `prompt-schema.md` — system prompt 結構
- `features.md` — Cowork 獨有功能（Artifacts、Scheduled Tasks、Memory、computer-use）
- `binary.md` — Desktop App 程式碼與資料目錄分析
- `CLAUDE.md` — 專案研究方法說明

> 非官方研究筆記，內容可能隨 Cowork 版本變動而過時。
