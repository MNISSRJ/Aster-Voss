"""Tool registry with explicit schemas and permission metadata."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ToolDefinition:
    handler: Callable[[dict[str, Any]], str]
    description: str
    properties: dict[str, dict[str, Any]]
    required: tuple[str, ...] = ()
    permission: str = "read"
    timeout_seconds: float = 5.0


def _status(args: dict[str, Any]) -> str:
    return json.dumps({"project": "Aster Voss", "status": "ready"}, ensure_ascii=False)


def _safe_project_path(raw_path: str) -> Path | None:
    candidate = (ROOT / raw_path).resolve()
    try:
        candidate.relative_to(ROOT)
    except ValueError:
        return None
    return candidate


def _read(args: dict[str, Any]) -> str:
    raw_path = str(args.get("path", "")).strip()
    if not raw_path:
        return "Path is required."
    path = _safe_project_path(raw_path)
    if path is None:
        return "Refused: outside project."
    if not path.is_file():
        return "File not found."
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:12000]
    except OSError as exc:
        return f"Tool error: {type(exc).__name__}"


REGISTRY: dict[str, ToolDefinition] = {
    "project_status": ToolDefinition(
        handler=_status,
        description="Return the current Aster Voss project status.",
        properties={},
        required=(),
        permission="read",
    ),
    "read_project_file": ToolDefinition(
        handler=_read,
        description="Read a UTF-8 text file inside the Aster Voss project.",
        properties={
            "path": {
                "type": "string",
                "description": "Project-relative path, such as agent.py",
            }
        },
        required=("path",),
        permission="read",
    ),
}


def tool_specs() -> list[dict[str, Any]]:
    specs = []
    for name, definition in REGISTRY.items():
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": definition.description,
                    "parameters": {
                        "type": "object",
                        "properties": definition.properties,
                        "required": list(definition.required),
                        "additionalProperties": False,
                    },
                },
            }
        )
    return specs


def tool_permission(name: str) -> str | None:
    definition = REGISTRY.get(name)
    return definition.permission if definition else None


def run_tool(name: str, args: dict[str, Any] | None = None) -> str:
    definition = REGISTRY.get(name)
    if definition is None:
        return "Unknown tool."
    try:
        return definition.handler(args or {})
    except Exception as exc:
        return f"Tool error: {type(exc).__name__}: {exc}"
