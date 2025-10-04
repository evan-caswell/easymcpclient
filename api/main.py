from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastmcp import Client as McpClient
from fastmcp.client.transports import StreamableHttpTransport

from api.routers import (
    SYSTEM_INSTRUCTIONS,
    configure_llm,
    llm_store,
    register_mcp_tool,
    router,
    set_mcp_tool_names,
)
from api.services.llm_client import LLMClient
from api.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage the MCP and LLM lifecycles, registering tools at startup."""
    transport = StreamableHttpTransport(url=settings.DMR_MCP_URL)
    app.state.mcp = McpClient(transport)

    llm = LLMClient(
        base_url=settings.LLM_MODEL_URL,
        model_name=settings.LLM_MODEL_NAME,
        api_key="dmr",
        store=llm_store,
        timeout=60.0,
        instructions=SYSTEM_INSTRUCTIONS,
    )
    configure_llm(llm)
    app.state.llm = llm

    try:
        async with app.state.mcp:
            tools = await app.state.mcp.list_tools()
            names: list[str] = []
            for tool in tools:
                tool_name = tool.name

                def make_tool(n: str) -> Callable[..., Awaitable[Any]]:
                    """Build an async wrapper that delegates to the MCP tool."""

                    async def _wrapper(**kwargs: Any) -> Any:
                        """Invoke the remote MCP tool and normalize its response."""
                        result = await app.state.mcp.call_tool(n, kwargs)

                        if result.is_error:
                            message = (
                                result.content[0].text
                                if result.content and hasattr(result.content[0], "text")
                                else "Tool error"
                            )
                            raise RuntimeError(message)

                        if result.data is not None:
                            return result.data

                        if result.structured_content is not None:
                            return result.structured_content

                        for content_item in result.content or []:
                            if hasattr(content_item, "text"):
                                return content_item.text
                        return None

                    return _wrapper

                tool_func = make_tool(tool_name)

                parameters_schema = tool.inputSchema or {
                    "type": "object",
                    "properties": {},
                }

                register_mcp_tool(
                    name=tool_name,
                    description=tool.description or "",
                    parameters_schema=parameters_schema,
                    func=tool_func,
                )
                names.append(tool_name)
            set_mcp_tool_names(names)
            yield
    finally:
        await llm.close()


app = FastAPI(lifespan=lifespan)
app.include_router(router)
