from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter

from api.schemas import ChatRequest
from api.services.in_memory_store import InMemoryStore
from api.services.llm_client import LLMClient

router = APIRouter()

SYSTEM_INSTRUCTIONS = """
You are a helpful assistant with access to Tavily web tools.
Do not fabricate answers that require real-time or external information - instead, call the appropriate Tavily tool.

MOST IMPORT RULES:
- ONLY USE TOOLS IF ABSOLUTELY NECESSARY!
- DO NOT USE TOOLS IF THE USER IS BEING CONVERSATIONAL!

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
_llm: LLMClient | None = None
_MCP_TOOL_NAMES: list[str] = []


def configure_llm(client: LLMClient) -> None:
    """Cache the LLM instance configured during application startup."""
    global _llm
    _llm = client


def _require_llm() -> LLMClient:
    """Return the configured LLM instance or raise if it is missing."""
    if _llm is None:
        raise RuntimeError("LLM client is not configured.")
    return _llm


def register_mcp_tool(
    *,
    name: str,
    description: str,
    parameters_schema: dict[str, Any],
    func: Callable[..., Any] | Callable[..., Awaitable[Any]],
) -> None:
    """Register a tool wrapper with the shared LLM client."""
    llm = _require_llm()
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
async def chat(request: ChatRequest) -> dict[str, str | dict[str, Any]]:
    """Send a prompt to the LLM and return its reply."""
    llm = _require_llm()
    response = await llm.generate(
        request.prompt,
        thread_id="thread-1",
        enabled_tool_names=["tavily-search"],
        temperature=0.0,
    )
    return {"reply": response}


@router.get("/memory")
async def get_memory() -> dict[str, list[dict[str, Any]]]:
    """Expose the persisted conversation history for the default thread."""
    return {"history": await llm_store.get("thread-1")}
