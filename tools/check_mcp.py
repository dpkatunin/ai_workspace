#!/usr/bin/env python3
"""
Проверка MCP-сервера без BDS и без MCP-клиента: обычный JSON-RPC по HTTP на stdlib.

Совместим с MCP SDK v2: сервер v2 обслуживает клиентов, которые начинают
с handshake (initialize) — это нужно для обратной совместимости.

Что делает:
  1. initialize  — рукопожатие, получает Mcp-Session-Id
  2. tools/list  — список инструментов сервера
  3. tools/call  — вызывает search_kb с вашим вопросом и печатает ответ

Запуск (сервер должен быть уже запущен):

    py tools/check_mcp.py "как настроить ордерный склад"
    py tools/check_mcp.py "что такое спецификация" --url http://127.0.0.1:8000/mcp --top-k 2
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-06-18"

def _parse_sse(raw: str) -> dict:
    """Достать JSON из ответа text/event-stream (MCP так умеет отвечать)."""
    last: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if not payload:
            continue
        try:
            last = json.loads(payload)
        except json.JSONDecodeError:
            continue
    return last

def _post(url: str, payload: dict, session_id: str | None = None, timeout: int = 300) -> tuple[dict, str | None]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        new_session = response.headers.get("Mcp-Session-Id") or session_id
        content_type = response.headers.get("Content-Type", "")
        raw = response.read().decode("utf-8", errors="replace")

    if not raw.strip():
        return {}, new_session
    if "text/event-stream" in content_type:
        return _parse_sse(raw), new_session
    return json.loads(raw), new_session

def main() -> int:
    parser = argparse.ArgumentParser(description="Ручная проверка MCP-сервера базы знаний")
    parser.add_argument("query", help="вопрос для search_kb")
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    try:
        # 1. Рукопожатие
        init_response, session_id = _post(
            args.url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "check-mcp", "version": "0.1.0"},
                },
            },
        )
        server_info = (init_response.get("result") or {}).get("serverInfo") or {}
        print(f"✓ initialize: {server_info.get('name', '?')} {server_info.get('version', '')}".rstrip())
        if session_id:
            print(f"  session: {session_id[:12]}…")

        # Уведомление о готовности (без id, ответ обычно пустой)
        try:
            _post(args.url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
        except Exception:
            pass

        # 2. Список инструментов
        tools_response, _ = _post(
            args.url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session_id
        )
        tools = (tools_response.get("result") or {}).get("tools") or []
        print(f"✓ tools/list: {', '.join(t.get('name', '?') for t in tools) or '—'}")

        # 3. Вызов поиска
        call_response, _ = _post(
            args.url,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "search_kb", "arguments": {"query": args.query, "top_k": args.top_k}},
            },
            session_id,
        )

        if "error" in call_response:
            print(f"✗ ошибка: {call_response['error']}", file=sys.stderr)
            return 1

        content = (call_response.get("result") or {}).get("content") or []
        texts = [item.get("text", "") for item in content if item.get("type") == "text"]
        print("\n" + ("\n".join(texts) if texts else json.dumps(call_response, ensure_ascii=False, indent=2)))
        return 0

    except urllib.error.HTTPError as exc:
        print(f"✗ HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:500]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"✗ не удалось подключиться к {args.url}: {exc.reason}", file=sys.stderr)
        print("  Сервер запущен? py tools/mcp_server.py", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
