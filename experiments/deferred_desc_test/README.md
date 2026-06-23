# 實驗：deferred 工具是否隱藏 description

## 假設
Cowork 的 deferred 工具在 session 開場的 `<system-reminder>` 裡**只露名稱、無 description**，
description 要 `ToolSearch` 載入 schema 後才看得到。若成立 → 光看名字會被誤導。

## 受測物
`calc_server.py`（stdio）/ `calc_server_http.py`（HTTP）：兩個工具「名實相反」，
且 description 會**互相導向**對方，形成連鎖式發現：

| 工具名稱 | description（要載入才看得到） | 實際行為 |
|---|---|---|
| `add` | 「我其實是相乘；**要相加請改用 `multiply`**」 | 回傳 `a*b` |
| `multiply` | 「我其實是相加；**要相乘請改用 `add`**」 | 回傳 `a+b` |

→ 連鎖陷阱：agent 想「相加」→ 憑名字載入 `add` → 讀 description 才發現 `add` 不是加法、
且被導向 `multiply` → 再載入 `multiply` → 才用對工具。整條路徑都靠「載入後才看得到的
description」驅動；deferred（只有名字）時完全看不到這層指引。

server 本體已在沙盒 VM smoke-test 通過：`initialize` / `tools/list` / `tools/call` 正常，
`add(2,3)=6`、`multiply(2,3)=5`。

## 連接到 Cowork（Claude Desktop）

> ⚠️ 待驗證點之一：Cowork agent 模式是否載入 desktop config 的**本機 stdio** MCP server。
> 知識庫目前只記錄了「遠端 uuid connector（StreamableHTTP）」。這個實驗同時會回答
> 「Cowork 吃不吃本機 stdio server」。

1. 確認機器有 Python：命令列打 `python --version`（或 `python3`）。
2. 編輯 Claude Desktop 設定檔（Settings → Developer → Edit Config，或直接開
   `%APPDATA%\Claude\claude_desktop_config.json`），加入：

   ```json
   {
     "mcpServers": {
       "calc-swapped": {
         "command": "python",
         "args": ["C:\\path\\to\\experiments\\deferred_desc_test\\calc_server.py"]
       }
     }
   }
   ```
   （把 `args` 改成這支檔案在該機器上的**絕對路徑**；Windows 路徑用雙反斜線。）
3. **完全重開 Claude Desktop**，並**開一個新的 Cowork session**（MCP 清單變更通常要新 session 才生效）。
   工具會以 `mcp__calc-swapped__add` / `mcp__calc-swapped__multiply` 出現。

## 連接到 Cowork（B：localhost HTTP，**較可能成功**）

`calc_server_http.py`：零依賴的 **Streamable HTTP** 版，對應 Cowork client
（`directMcpHost.js` 的 `StreamableHTTPClientTransport`）。VM 已 smoke-test 通過
（initialize 發 `Mcp-Session-Id`、tools/list 回兩工具、add(2,3)=6、multiply(2,3)=5、GET→405）。

1. 在機器上啟動：`python calc_server_http.py`
   → 顯示 `MCP (Streamable HTTP) listening on http://127.0.0.1:8765/mcp`（保持此視窗開著）。
2. Cowork → 設定 → Connectors → **新增自訂 connector**，URL 填：
   ```
   http://127.0.0.1:8765/mcp
   ```
3. 連上後**開新 session**。工具會以 `mcp__{server}__add` / `mcp__{server}__multiply` 出現
   （自訂 connector 的 server 名常是 uuid）。

> 為何 HTTP 比 stdio 更可能成功：知識庫實證 Cowork 的 MCP 傳輸是 StreamableHTTP，
> connector 透過 URL 連接；本機 stdio 是否被 agent 模式採用尚未驗證。

### 替代：官方 SDK（FastMCP，需 `pip install mcp`）
若機器可裝套件，等價的精簡寫法：
```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("calc-swapped", host="127.0.0.1", port=8765)

@mcp.tool()
def add(a: float, b: float) -> float:
    """Multiplies two numbers (a*b). To ADD, use the `multiply` tool instead. (名為 add 實為相乘；要相加請改用 multiply)"""
    return a * b

@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Adds two numbers (a+b). To MULTIPLY, use the `add` tool instead. (名為 multiply 實為相加；要相乘請改用 add)"""
    return a + b

mcp.run(transport="streamable-http")   # 端點預設掛在 /mcp
```
（FastMCP 用 **docstring 當 description**、type hint 產 schema，行為一致。）

## 觀察步驟（在新 session 裡）— 連鎖式

給 agent 一個**相加**任務，例如：「請用這個 connector 把 2 和 3 **相加**」，然後觀察：

1. **載入前**：deferred 名單只見 `add` / `multiply` 兩個名字、無說明。
   理性的 agent 為了「相加」會先去**載入名字看起來對的 `add`**。
2. **載入 `add` 後**：description 揭露「`add` 其實是相乘、要相加請改用 `multiply`」
   → agent 發現被名字騙，**改去載入 `multiply`**。
3. **載入 `multiply` 後**：description 確認它才是相加 → agent 呼叫 `multiply(a=2,b=3)` → 回 `5`（正確的和）。
   （若 agent 偷懶沒讀 description、直接照名字呼叫 `add`，會得到 `6`＝乘積＝錯。）

對照測試：步驟 1 時直接問「**先不要 ToolSearch**，要相加該用哪個工具？」
→ 預期 agent 只能憑名字答 `add`（錯），印證 deferred 看不到 description 的導向資訊。

## 預期結論
若「想相加 → 先載 add → 被導向 → 再載 multiply → 才用對」這條鏈成立，即證實
**deferred 只給名稱；description（含『改用哪個工具』的導向）須 ToolSearch 載入後才可見**
（佐證 tools.md 既有記錄）。
