# 實驗：deferred 工具是否隱藏 description

## 假設
Cowork 的 deferred 工具在 session 開場的 `<system-reminder>` 裡**只露名稱、無 description**，
description 要 `ToolSearch` 載入 schema 後才看得到。若成立 → 光看名字會被誤導。

## 受測物
`calc_server.py`：零依賴的 MCP stdio server，兩個工具「名實相反」：

| 工具名稱 | description（要載入才看得到） | 實際行為 |
|---|---|---|
| `add` | 「Multiplies… 相乘」 | 回傳 `a*b` |
| `multiply` | 「Adds… 相加」 | 回傳 `a+b` |

→ 只信名字：以為 `add` 是加法（錯）。看到 description 才知道 `add` 其實在相乘。

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
    """Multiplies two numbers and returns their product. (名為 add 實為相乘)"""
    return a * b

@mcp.tool()
def multiply(a: float, b: float) -> float:
    """Adds two numbers and returns their sum. (名為 multiply 實為相加)"""
    return a + b

mcp.run(transport="streamable-http")   # 端點預設掛在 /mcp
```
（FastMCP 用 **docstring 當 description**、type hint 產 schema，行為一致。）

## 觀察步驟（在新 session 裡）

1. **載入前**：看開場 deferred 名單，應只見兩個名字、無說明。
   問 agent：「**先不要 ToolSearch**，`add` 這個工具是做什麼的？」
   → 預期：agent 只能憑名字猜「加法」（被騙）。
2. **載入後**：請 agent `ToolSearch select:mcp__calc-swapped__add,mcp__calc-swapped__multiply`，
   再問同一題。→ 預期：看到 description，發現「`add` 其實相乘、`multiply` 其實相加」。
3.（可選）請 agent 實際呼叫 `add(a=2,b=3)`，回 `6` 而非 `5` → 行為與 description 一致、與名字相反。

## 預期結論
若 1. 被名字騙、2. 載入後更正、3. 行為=description → 證實
**deferred 只給名稱、description 需 ToolSearch 載入後才可見**（佐證 tools.md 既有記錄）。
