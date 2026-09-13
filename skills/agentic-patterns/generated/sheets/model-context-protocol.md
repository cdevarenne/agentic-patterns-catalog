# Model Context Protocol

Category: tool-use | Complexity: high

Standardized protocol for sharing context and capabilities between AI models and tools

## In 30 seconds

- **What:** Standardized protocol that lets AI models discover, describe, and use tools through structured context and capability exchange.
- **When:** Systems needing multiple models to share tools, maintain session state, or hand off work across different AI services.
- **Watch out:** Protocol overhead and versioning mismatches between client and server implementations can silently degrade or break tool availability.

## Key features

- Standardized context sharing
- Tool capability discovery
- Cross-model interoperability
- Session state management

## Use cases

- multi-model-systems
- tool-integration
- context-handoffs
- agent-coordination

## Walkthrough example

> Illustrative scenario from the source; figures are not measurements.

```text
MCP Context Sharing:

```json
{
  "protocol": "mcp/1.0",
  "context": {
    "session_id": "sess_123",
    "conversation_history": [...],
    "user_preferences": {...},
    "active_tools": ["web_search", "calculator"]
  },
  "capabilities": {
    "tools": [
      {
        "name": "web_search",
        "schema": {...},
        "version": "1.2.0"
      }
    ]
  }
}
```

Enables seamless handoffs between different AI models
```

## Implementation (python)

```python
#!/usr/bin/env python3

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Response:
    id: int
    result: Any = None
    error: Optional[str] = None


@dataclass
class ToolDef:
    name: str
    description: str
    input_schema: Dict[str, str]
    handler: Callable[[Dict[str, Any]], Any]


@dataclass
class ResourceDef:
    uri: str
    name: str
    read: Callable[[], str]


# Channel abstraction: in a real deployment this is stdio or a socket.
class McpServer:
    def __init__(self) -> None:
        self.tools: Dict[str, ToolDef] = {}
        self.resources: Dict[str, ResourceDef] = {}

    def register_tool(self, tool: ToolDef) -> None:
        self.tools[tool.name] = tool

    def register_resource(self, res: ResourceDef) -> None:
        self.resources[res.uri] = res

    def handle(self, req: Dict[str, Any]) -> Response:
        rid, method, params = req["id"], req["method"], req.get("params", {})
        try:
            if method == "tools/list":
                return Response(rid, [
                    {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
                    for t in self.tools.values()
                ])
            if method == "tools/call":
                tool = self.tools.get(params.get("name"))
                if not tool:
                    raise ValueError(f"No such tool: {params.get('name')}")
                return Response(rid, tool.handler(params.get("arguments", {})))
            if method == "resources/list":
                return Response(rid, [{"uri": r.uri, "name": r.name} for r in self.resources.values()])
            if method == "resources/read":
                res = self.resources.get(params.get("uri"))
                if not res:
                    raise ValueError(f"No such resource: {params.get('uri')}")
                return Response(rid, {"uri": res.uri, "contents": res.read()})
            raise ValueError(f"Unknown method: {method}")
        except Exception as exc:
            return Response(rid, error=str(exc))


class McpClient:
    def __init__(self, server: McpServer) -> None:
        self.server = server
        self.seq = 0

    def _call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self.seq += 1
        res = self.server.handle({"id": self.seq, "method": method, "params": params or {}})
        if res.error:
            raise RuntimeError(res.error)
        return res.result

    def list_tools(self) -> List[dict]:
        return self._call("tools/list")

    def call_tool(self, name: str, args: Dict[str, Any]) -> Any:
        return self._call("tools/call", {"name": name, "arguments": args})

    def list_resources(self) -> List[dict]:
        return self._call("resources/list")

    def read_resource(self, uri: str) -> Any:
        return self._call("resources/read", {"uri": uri})


def main() -> None:
    server = McpServer()
    server.register_tool(ToolDef(
        "add", "Add two integers", {"a": "number", "b": "number"},
        lambda args: args["a"] + args["b"],
    ))
    server.register_tool(ToolDef(
        "get_weather", "Return canned weather for a city", {"city": "string"},
        lambda args: {"city": args["city"], "tempC": 21, "sky": "clear"},
    ))
    server.register_resource(ResourceDef(
        "file:///readme.txt", "Project README",
        lambda: "This project demonstrates the Model Context Protocol.",
    ))

    client = McpClient(server)

    print("Discovered tools:")
    for t in client.list_tools():
        params = ", ".join(t["inputSchema"].keys())
        print(f"  {t['name']}({params}) - {t['description']}")

    print("\nInvoking tools:")
    print(f"  add(2, 40) = {client.call_tool('add', {'a': 2, 'b': 40})}")
    print(f"  get_weather('Paris') = {client.call_tool('get_weather', {'city': 'Paris'})}")

    print("\nResources:")
    for r in client.list_resources():
        print(f"  {r['uri']} ({r['name']})")
    doc = client.read_resource("file:///readme.txt")
    print(f"  read {doc['uri']}: \"{doc['contents']}\"")

    print("\nError handling:")
    try:
        client.call_tool("divide", {"a": 1, "b": 0})
    except RuntimeError as exc:
        print(f"  {exc}")


if __name__ == "__main__":
    main()
```

## References

- Model Context Protocol Official Website - https://modelcontextprotocol.io
- MCP Specification 2025-06-18 (Current) - https://modelcontextprotocol.io/specification/2025-06-18
- Anthropic MCP Documentation - https://docs.anthropic.com/en/docs/agents-and-tools/mcp
- Claude Desktop MCP Setup Guide - https://support.anthropic.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop
- MCP GitHub Organization (Core Repositories) - https://github.com/modelcontextprotocol

---
Source: https://agentic-design.ai/patterns/tool-use/model-context-protocol (extraction: free-pack, content sha256 cbfaa7878e15…)
