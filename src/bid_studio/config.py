from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bid Studio"
    app_env: str = "development"
    database_url: str = "sqlite:///./bid_studio.db"
    default_workspace_slug: str = "primus-demo"
    digest_sender_email: str = "digest@bidstudio.example"
    delivery_sender_email: str = "delivery@bidstudio.example"
    seed_on_startup: bool = True
    # Shared secret for the /mcp endpoint. Empty = open (development only).
    mcp_api_key: str = ""
    # When set, MCP tools call this remote Bid Studio instead of the in-process app.
    api_base_url: str = ""
    # Public URL shown in the developer docs, e.g. https://bid-studio.example.com
    public_base_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
