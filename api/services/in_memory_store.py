import asyncio


class InMemoryStore:
    """Thread-safe in-memory message history store."""

    def __init__(self) -> None:
        """Initialise the store and its async lock."""
        self._data: dict[str, list[dict[str, str]]] = {}
        self._lock = asyncio.Lock()

    async def get(self, thread_id: str) -> list[dict[str, str]]:
        """Return a copy of the stored messages for the given thread."""
        async with self._lock:
            return list(self._data.get(thread_id, []))

    async def append(self, thread_id: str, msg: dict[str, str]) -> None:
        """Append a message to the end of the history for the thread."""
        async with self._lock:
            self._data.setdefault(thread_id, []).append(msg)

    async def prepend(self, thread_id: str, msg: dict[str, str]) -> None:
        """Insert a message at the beginning of the history for the thread."""
        async with self._lock:
            self._data.setdefault(thread_id, []).insert(0, msg)

    async def truncate(self, thread_id: str, max_messages: int) -> None:
        """Trim history to the most recent ``max_messages`` entries."""
        if max_messages <= 0:
            return
        async with self._lock:
            msgs = self._data.get(thread_id, [])
            if len(msgs) > max_messages:
                self._data[thread_id] = msgs[-max_messages:]

    async def delete(self, thread_id: str) -> None:
        """Remove the stored history for the thread if it exists."""
        async with self._lock:
            if thread_id in self._data:
                del self._data[thread_id]
