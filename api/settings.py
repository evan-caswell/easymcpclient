from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the API service."""

    DMR_MCP_URL: str
    LLM_MODEL_URL: str
    LLM_MODEL_NAME: str

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def get_setttings() -> Settings:
    """Load configuration values from the environment."""
    return Settings()  # pyright: ignore[reportCallIssue]


settings = get_setttings()
