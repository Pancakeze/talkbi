from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_SECRET_KEY = "talkbi-dev-secret-key"
PRODUCTION_ENVIRONMENTS = {"staging", "production"}


class Settings(BaseSettings):
    app_name: str = "TalkBI API"
    api_version: str = "0.1.0"
    environment: str = "development"  # development | staging | production
    api_prefix: str = "/api"
    secret_key: str = DEFAULT_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    # 本地默认 SQLite；Docker / 生产通过环境变量 DATABASE_URL 覆盖为 PostgreSQL
    database_url: str = "sqlite+pysqlite:///./talkbi.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    llm_mock_mode: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:14b"
    sql_echo: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @model_validator(mode="after")
    def reject_production_defaults(self) -> "Settings":
        if self.environment.lower() in PRODUCTION_ENVIRONMENTS:
            if not self.secret_key.strip() or self.secret_key == DEFAULT_SECRET_KEY:
                raise ValueError("SECRET_KEY must be set to a strong non-default value.")
        return self


settings = Settings()
