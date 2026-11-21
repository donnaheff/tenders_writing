from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Bid Studio"
    app_env: str = "development"
    database_url: str = "sqlite:///./bid_studio.db"
    default_workspace_slug: str = "primus-demo"
    digest_sender_email: str = "digest@bidstudio.example"
    delivery_sender_email: str = "delivery@bidstudio.example"
    seed_on_startup: bool = True
    contact_notify_email: str = "team@bidstudio.example"
    cron_secret: str = ""
    # Comma-separated feed sources to refresh on each scheduled run: grants_gov, eu_funding
    feed_sources: str = ""
    feed_sync_limit: int = 50
    auto_process_grants: bool = False
    reminder_window_days: int = 14
    # AI assistant: with a key it calls Claude, otherwise a rule-based offline helper is used
    anthropic_api_key: str = ""
    assistant_model: str = "claude-sonnet-5-5"
    assistant_timeout: float = 60.0
    # Licensing: "off" (default), "warn" (banner only) or "on" (block until a valid key is installed)
    license_enforcement: str = "off"
    license_key: str = ""
    license_public_key: str = ""
    license_grace_days: int = 14
    license_revoked_ids: str = ""
    # Writers marketplace
    marketplace_admin_emails: str = ""
    marketplace_fee_pct: float = 10.0
    session_days: int = 14
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
