#!/usr/bin/env python3
"""
Deferred-description 驗證用 MCP server（零外部依賴，stdio transport）。

實驗目的：驗證 Cowork 的 deferred 工具「開場只露名稱、description 要 ToolSearch
載入後才看得到」。本 server 故意讓「名稱」與「description／實際行為」相反：

  - 工具 add      → description 說它「相乘」，實作也真的回傳 a*b
  - 工具 multiply  → description 說它「相加」，實作也真的回傳 a+b

預期：agent 在 deferred 狀態只看到 add / multiply 兩個名字，若只憑名字會誤判
（以為 add=加法）；ToolSearch 載入 schema 後才看到 description 揭露真相。

協議：實作 MCP stdio 最小子集——newline-delimited JSON-RPC 2.0，
方法 initialize / notifications/initialized / tools/list / tools/call。
"""
import sys
import json

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "add",
        # ↓ 故意說謊：名字叫 add，description 卻說它做乘法、並把「相加」導向 multiply
        "description": "Multiplies two numbers and returns their product (a*b). "
                       "This tool does NOT add — to ADD two numbers, use the `multiply` tool instead. "
                       "(此工具名為 add，但實際是『相乘』；要相加請改用 multiply。)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "第一個數"},
                "b": {"type": "number", "description": "第二個數"},
            },
            "required": ["a", "b"],
        },
    },
    {
        "name": "multiply",
        # ↓ 故意說謊：名字叫 multiply，description 卻說它做加法、並把「相乘」導向 add
        "description": "Adds two numbers and returns their sum (a+b). "
                       "This tool does NOT multiply — to MULTIPLY two numbers, use the `add` tool instead. "
                       "(此工具名為 multiply，但實際是『相加』；要相乘請改用 add。)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "number", "description": "第一個數"},
                "b": {"type": "number", "description": "第二個數"},
            },
            "required": ["a", "b"],
        },
    },
]


def call_tool(name, args):
    a = args.get("a")
    b = args.get("b")
    if name == "add":          # 行為跟著 description：add 做乘法
        return a * b
    if name == "multiply":     # 行為跟著 description：multiply 做加法
        return a + b
    raise ValueError(f"unknown tool: {name}")


def send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle(req):
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "calc-swapped", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        return None  # notification，無需回應

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        params = req.get("params", {})
        name = params.get("name")
        args = params.get("arguments", {})
        try:
            result = call_tool(name, args)
            return {
                "jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text", "text": str(result)}]},
            }
        except Exception as e:  # noqa: BLE001
            return {
                "jsonrpc": "2.0", "id": rid,
                "result": {
                    "content": [{"type": "text", "text": f"error: {e}"}],
                    "isError": True,
                },
            }

    # 未知方法
    if rid is not None:
        return {
            "jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(req)
        if resp is not None:
            send(resp)


if __name__ == "__main__":
    main()
