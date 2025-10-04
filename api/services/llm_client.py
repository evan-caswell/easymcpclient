import json
import inspect
from typing import Any, Awaitable, Callable

import httpx

from api.services.store_protocol import ConversationStore


class LLMClient:
    """Async client for OpenAI-compatible chat models with optional tool calling."""

    def __init__(
        self,
        base_url: str,
        model_name: str,
        store: ConversationStore,
        api_key: str | None = None,
        instructions: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialize the client and create an underlying HTTPX session."""
        self.base_url = base_url
        self.model_name = model_name
        self.api_key = api_key
        self._chat_url = f"{base_url}chat/completions"
        self._system_message = (
            {"role": "system", "content": instructions} if instructions else None
        )
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=timeout,
            http2=True,
        )
        self.store = store
        self.tool_registry: dict[str, dict[str, Any]] = {}

    def register_tool(
        self,
        func: Callable[..., Any] | Callable[..., Awaitable[Any]],
        description: str,
        parameters_schema: dict[str, Any],
        name: str | None = None,
    ) -> None:
        """Register a callable so the LLM can trigger it via tool calls."""
        tool_name = name or func.__name__
        self.tool_registry[tool_name] = {
            "function": func,
            "definition": {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": description,
                    "parameters": parameters_schema,
                },
            },
        }

    def _headers(self) -> dict[str, str]:
        """Create HTTP headers for completion requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def close(self) -> None:
        """Close the underlying HTTPX client."""
        await self._client.aclose()

    async def reset_conversation(self, thread_id: str) -> None:
        """Remove all stored messages for the provided thread."""
        await self.store.delete(thread_id)

    async def _ensure_system_message(self, thread_id: str) -> None:
        """Ensure the configured system prompt is at the start of history."""
        if not self._system_message:
            return

        history = await self.store.get(thread_id)
        if history and history[0].get("role") == "system":
            return

        await self.store.prepend(thread_id, self._system_message)

    @staticmethod
    def _is_async_callable(func: Any) -> bool:
        """Return True when the callable is coroutine based."""
        return inspect.iscoroutinefunction(func) or inspect.iscoroutinefunction(
            getattr(func, "__call__", None)
        )

    @classmethod
    def _stringify_tool_result(cls, value: Any) -> str:
        """Convert tool outputs to the string form expected by the API."""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    async def generate(
        self,
        prompt: str,
        thread_id: str,
        enabled_tool_names: list[str] | None = None,
        max_tool_iterations: int = 5,
        response_schema: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str | dict[str, Any]:
        """Send the prompt and history to the model and return its response."""
        await self._ensure_system_message(thread_id)

        user_message = {"role": "user", "content": prompt}
        await self.store.append(thread_id, user_message)

        api_tools = []
        if enabled_tool_names:
            for name in enabled_tool_names:
                if name in self.tool_registry:
                    api_tools.append(self.tool_registry[name]["definition"])

        for i in range(max_tool_iterations):
            messages = await self.store.get(thread_id)

            payload = {"model": self.model_name, "messages": messages}
            payload.update(kwargs or {})

            if api_tools:
                payload["tools"] = api_tools

            if response_schema:
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"schema": response_schema, "strict": True},
                }

            response = await self._client.post(self._chat_url, json=payload)
            response.raise_for_status()

            data = response.json()

            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError(f"No choices return: {data}")
            choice = choices[0]

            response_msg = choice.get("message") or {}

            if "reasoning_content" in response_msg:
                del response_msg["reasoning_content"]

            tool_calls = response_msg.get("tool_calls")

            if tool_calls:
                if i >= max_tool_iterations - 1:
                    await self.store.append(thread_id, response_msg)
                    return "Max tool iterations reached before executing requested tools."

                await self.store.append(thread_id, response_msg)

                for tool_call in tool_calls:
                    func_name = tool_call.get("function", {}).get("name")
                    raw_args = tool_call.get("function", {}).get("arguments", "{}")
                    tool_call_id = tool_call.get("id")

                    if not func_name or func_name not in self.tool_registry:
                        tool_result = (
                            f"Error: Requested tool '{func_name}' is not registered."
                        )
                        tool_content = self._stringify_tool_result(tool_result)
                        await self.store.append(
                            thread_id,
                            {
                                "tool_call_id": tool_call_id,
                                "role": "tool",
                                "name": func_name or "unknown",
                                "content": tool_content,
                            },
                        )
                        continue

                    tool_info = self.tool_registry[func_name]
                    tool_func = tool_info["function"]

                    try:
                        arguments = json.loads(raw_args or "{}")
                    except json.JSONDecodeError as exc:
                        tool_result = f"Error: invalid JSON for tool '{func_name}': {exc}"
                        tool_content = self._stringify_tool_result(tool_result)
                        await self.store.append(
                            thread_id,
                            {
                                "tool_call_id": tool_call_id,
                                "role": "tool",
                                "name": func_name,
                                "content": tool_content,
                            },
                        )
                        continue

                    try:
                        if self._is_async_callable(tool_func):
                            result = await tool_func(**arguments)
                        else:
                            result = tool_func(**arguments)
                    except Exception as exc:  # noqa: BLE001
                        result = f"Error executing tool '{func_name}': {exc}"

                    tool_content = self._stringify_tool_result(result)
                    await self.store.append(
                        thread_id,
                        {
                            "tool_call_id": tool_call_id,
                            "role": "tool",
                            "name": func_name,
                            "content": tool_content,
                        },
                    )

                continue

            await self.store.append(thread_id, response_msg)

            content = response_msg.get("content", "")
            if response_schema:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return content

            return content

        return "Max tool iterations exhausted without completion."
