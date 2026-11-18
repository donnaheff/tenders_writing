from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bid Studio"
    app_env: str = "development"
    database_url: str = "sqlite:///./bid_studio.db"
    default_workspace_slug: str = "primus-demo"
    digest_sender_email: str = "digest@bidstudio.example"
    delivery_sender_email: str = "delivery@bidstudio.example"
    seed_on_startup: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
