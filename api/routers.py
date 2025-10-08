from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request

from api.schemas import ChatRequest
from api.services.in_memory_store import InMemoryStore
from api.services.llm_client import LLMClient

router = APIRouter()

SYSTEM_INSTRUCTIONS = """
You are a helpful assistant with access to Tavily web tools.
Do not fabricate answers that require real-time or external information - instead, call the appropriate Tavily tool.
Do not use tools for questions you confidently already know the answer to.

MOST IMPORT RULES:
- ONLY USE TOOLS IF ABSOLUTELY NECESSARY!
- DO NOT USE TOOLS IF THE USER IS BEING CONVERSATIONAL! (e.g., Hello)

Tool Usage Rules:

- tavily-search -> Use for general information, current events, news, weather, or any time-sensitive facts.
- tavily-crawl -> Use to explore a website starting from a base URL, following internal links.
- tavily-extract -> Use to extract specific raw content from one or more given URLs.
- tavily-map -> Use to generate a structured map of a website's structure and navigation.

Best Practices:

- Always explain why you chose a tool.
- Summarize results clearly and include the source URL(s).
- Only crawl/extract from domains explicitly given by the user.
- Avoid dumping long raw text unless requested.
- If multiple tools apply, choose the most direct and efficient.
"""

llm_store = InMemoryStore()
_MCP_TOOL_NAMES: list[str] = []


def register_mcp_tool(
    *,
    llm: LLMClient,
    name: str,
    description: str,
    parameters_schema: dict[str, Any],
    func: Callable[..., Any] | Callable[..., Awaitable[Any]],
) -> None:
    """Register a tool wrapper with the shared LLM client."""
    llm.register_tool(
        func=func,
        description=description,
        parameters_schema=parameters_schema,
        name=name,
    )
    if name not in _MCP_TOOL_NAMES:
        _MCP_TOOL_NAMES.append(name)


def set_mcp_tool_names(names: list[str]) -> None:
    """Replace the cached list of available MCP tool names."""
    _MCP_TOOL_NAMES.clear()
    _MCP_TOOL_NAMES.extend(names)


@router.get("/healthz")
async def health() -> dict[str, str]:
    """Report API readiness and the registered MCP tools."""
    return {"status": "ok", "tools": ",".join(_MCP_TOOL_NAMES)}


@router.post("/chat")
async def chat(
    request: Request, chat_request: ChatRequest
) -> dict[str, str | dict[str, Any]]:
    """Send a prompt to the LLM and return its reply."""
    llm = request.app.state.llm
    response = await llm.generate(
        chat_request.prompt,
        thread_id=chat_request.thread_id,
        enabled_tool_names=["tavily-search"], # <-- Tools available to LLM
        temperature=0.0,
    )
    return {"reply": response}


@router.get("/memory")
async def get_memory() -> dict[str, list[dict[str, Any]]]:
    """Expose the persisted conversation history for the default thread."""
    return {"history": await llm_store.get("thread-1")}
