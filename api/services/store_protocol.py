from typing import Protocol


class ConversationStore(Protocol):
    """Protocol describing async storage for chat message history."""

    async def get(self, thread_id: str) -> list[dict[str, str]]:
        """Retrieve all messages stored for ``thread_id``."""
        ...

    async def append(self, thread_id: str, msg: dict[str, str]) -> None:
        """Append ``msg`` to the existing history."""
        ...

    async def truncate(self, thread_id: str, max_messages: int) -> None:
        """Limit history to at most ``max_messages`` records."""
        ...

    async def delete(self, thread_id: str) -> None:
        """Remove all persisted messages for ``thread_id``."""
        ...

    async def prepend(self, thread_id: str, msg: dict[str, str]) -> None:
        """Insert ``msg`` at the beginning of the history."""
        ...
