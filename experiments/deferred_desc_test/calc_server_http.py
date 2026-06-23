#!/usr/bin/env python3
"""
Deferred-description 驗證用 MCP server —— Streamable HTTP / localhost 版（零外部依賴）。

對應 Cowork 的 MCP client（directMcpHost.js 的 StreamableHTTPClientTransport）。
連接方式：Cowork → 新增自訂 connector → URL 填 http://127.0.0.1:8765/mcp

工具「名實相反」（同 stdio 版）：
  - add      → description 說「相乘」，實作回 a*b
  - multiply → description 說「相加」，實作回 a+b

實作 Streamable HTTP transport 最小子集：
  POST /mcp  ：收一則 JSON-RPC，回 application/json（單則回應）或 202（notification）
  GET  /mcp  ：回 405（本 server 不做 server→client 主動串流，client 會容忍）
  DELETE /mcp：結束 session，回 200
  initialize 時發 Mcp-Session-Id header。
"""
import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST, PORT, PATH = "127.0.0.1", 8765, "/mcp"
DEFAULT_PROTOCOL = "2025-03-26"

TOOLS = [
    {
        "name": "add",
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

_sessions = set()


def run_tool(name, args):
    a, b = args.get("a"), args.get("b")
    if name == "add":
        return a * b          # 行為跟著 description：add 相乘
    if name == "multiply":
        return a + b          # 行為跟著 description：multiply 相加
    raise ValueError(f"unknown tool: {name}")


def dispatch(req):
    """回 (response_dict_or_None, new_session_id_or_None)。"""
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        sid = uuid.uuid4().hex
        _sessions.add(sid)
        proto = (req.get("params") or {}).get("protocolVersion") or DEFAULT_PROTOCOL
        return ({
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "protocolVersion": proto,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "calc-swapped", "version": "0.1.0"},
            },
        }, sid)

    if method == "notifications/initialized":
        return (None, None)  # notification

    if method == "tools/list":
        return ({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}, None)

    if method == "tools/call":
        params = req.get("params") or {}
        try:
            result = run_tool(params.get("name"), params.get("arguments") or {})
            return ({
                "jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text", "text": str(result)}]},
            }, None)
        except Exception as e:  # noqa: BLE001
            return ({
                "jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text", "text": f"error: {e}"}],
                           "isError": True},
            }, None)

    if rid is not None:
        return ({"jsonrpc": "2.0", "id": rid,
                 "error": {"code": -32601, "message": f"method not found: {method}"}}, None)
    return (None, None)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # 安靜
        pass

    def _json(self, obj, code=200, session_id=None):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if session_id:
            self.send_header("Mcp-Session-Id", session_id)
        self.end_headers()
        self.wfile.write(body)

    def _empty(self, code):
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        if self.path.rstrip("/") != PATH:
            self._empty(404); return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            req = json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            self._json({"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "parse error"}}, 400)
            return
        resp, sid = dispatch(req)
        if resp is None:
            self._empty(202)            # notification → 202 Accepted
        else:
            self._json(resp, 200, session_id=sid)

    def do_GET(self):
        # 不支援 server→client 主動串流；client 會容忍 405
        self._empty(405)

    def do_DELETE(self):
        sid = self.headers.get("Mcp-Session-Id")
        _sessions.discard(sid)
        self._empty(200)


if __name__ == "__main__":
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"MCP (Streamable HTTP) listening on http://{HOST}:{PORT}{PATH}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
