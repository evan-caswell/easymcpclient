# Easy MCP Client

## Overview
This project delivers an end-to-end conversational assistant that combines a FastAPI backend, a Streamlit chat UI, and a Model Context Protocol (MCP) gateway so the assistant can call external tools (e.g., Tavily search). The API wraps a Docker Model Runner-hosted LLM endpoint behind an OpenAI-compatible interface, persists chat history in memory, and exposes endpoints for health checks, chat, and troubleshooting.

## Architecture & Capabilities
- **FastAPI service** (`api/`): boots with a lifespan hook that connects to the MCP gateway, discovers remote tools, and registers them on a shared LLM client for tool calling.
- **LLM client** (`api/services/llm_client.py`): async wrapper around an OpenAI-style `/chat/completions` endpoint with tool support, structured output, and conversation tracking.
- **Conversation store** (`api/services/in_memory_store.py`): thread-safe in-memory history store used by the LLM client (intended to be swappable).
- **Streamlit UI** (`ui/app.py`): provides a simple chat experience against the FastAPI backend.
- **Docker Compose** (`compose.yaml`): orchestrates the API, the Streamlit UI, and a docker-based MCP gateway.

## Tech Stack
- **FastAPI** for the HTTP API.
- **Streamlit** for the web UI.
- **fastmcp** client library for Model Context Protocol access.
- **HTTPX** for async HTTP calls with HTTP/2 support.
- **Docker / Docker Compose** for containerized deployment, including Docker Model Runner integration.
- **Python 3.13** (see Dockerfile) with type hints and pydantic settings management.

## Prerequisites
- Docker Desktop with the Docker MCP Toolkit extension enabled.
- At least one MCP server added in Docker Desktop (e.g., Tavily) so the gateway can proxy tool calls.
- For servers that require credentials, populate the server's Configuration secrets section (Docker Desktop > Docker MCP Toolkit > your server > Configuration > Secrets) with the necessary key/value pairs so they are mounted for API and gateway containers.

## Running Locally (without Docker Compose)
1. Ensure Python 3.11+ (tested with 3.13) and install dependencies: `pip install -r requirements.txt`.
2. Configure environment variables (e.g., `DMR_MCP_URL`, `LLM_MODEL_URL`, `LLM_MODEL_NAME`) via `.env`:
   ```bash
   DMR_MCP_URL=http://localhost:8080/mcp
   API_BASE_URL=http://localhost:8000
   LLM_MODEL_URL=http://localhost:12434/engines/llama.cpp/v1
   LLM_MODEL_NAME=
   ```
3. **Important:** before starting the API, launch the MCP gateway using the command:
   ```bash
   docker mcp gateway run --port 8080 --transport streaming
   ```
   Leave this process running; the API will connect on startup.
4. Start the FastAPI server:
   ```bash
   uvicorn api.main:app --host 0.0.0.0 --port 8000
   ```
5. In a separate terminal, run the Streamlit UI (optional):
   ```bash
   streamlit run ui/app.py
   ```
   It expects `API_BASE_URL` (default `http://localhost:8000`).

## Running with Docker Compose
1. Populate `.env.docker` with the required values (provided defaults target the compose network):
   ```bash
   DMR_MCP_URL=http://mcp_gateway:8080/mcp
   API_BASE_URL=http://api:8000
   ```
2. From the project root, start the stack:
   ```bash
   docker compose up --build
   ```
   This launches:
   - `mcp_gateway` on port 8080
   - `api` on port 8000 (health check at `/healthz`)
   - `ui` on port 8501 for the Streamlit interface
3. Visit `http://localhost:8501` to interact with the assistant.

Docker Compose automatically injects the model endpoint and name into the API container when you use the long syntax models block:
```yaml
models:
  llm:
    endpoint_var: LLM_MODEL_URL
    model_var: LLM_MODEL_NAME
```
See the Docker documentation for details: https://docs.docker.com/ai/compose/models-and-compose/

## Using the LLM Client
The `LLMClient` abstraction (in `api/services/llm_client.py`) wraps an OpenAI-compatible chat endpoint while managing conversation history and tool execution. Typical workflow:

1. **Instantiate** the client with a base URL, model name, a `ConversationStore` implementation, and optional system instructions.
2. **Register tools** with `register_tool`, providing a callable (sync or async) and a JSON schema describing its parameters.
3. **Generate responses** via `await generate(...)`; the client sends accumulated history, invokes tools as needed, and can enforce structured responses when you pass `response_schema`.
4. **Close the client** with `await close()` when finished so the underlying HTTPX session is released.

Example usage in an async context:
```python
from api.services.in_memory_store import InMemoryStore
from api.services.llm_client import LLMClient

store = InMemoryStore()
client = LLMClient(
    base_url='http://localhost:1234/',
    model_name='ai/granite-4.0-h-micro',
    store=store,
    instructions='You are a helpful assistant.',
)

def echo_tool(message: str) -> str:
    return message

client.register_tool(
    func=echo_tool,
    description='Echo the provided message.',
    parameters_schema={
        'type': 'object',
        'properties': {'message': {'type': 'string'}},
        'required': ['message'],
    },
)

response = await client.generate('Hello there!', thread_id='demo-thread')
print(response)

await client.close()
```

## Roadmap
- **Persistent conversation store:** replace the in-memory store with Redis (or equivalent) to support multi-instance scaling and durable histories.
- **Thread isolation:** implement proper thread identifiers per user/session to prevent shared histories and enable concurrent conversations.
- **Enhanced UI:** iterate on the Streamlit front-end (or migrate to a richer framework) for features like conversation lists, tool call inspection, and error feedback.
- **Observability:** add logging, metrics, and tracing around LLM/tool calls for debugging and monitoring.
- **Secrets management:** integrate secure secret storage for API keys instead of relying on plain `.env` files.

## Contributing
Issues and pull requests are welcome. Please run formatting and linting checks before submitting changes and ensure new features include adequate tests.
