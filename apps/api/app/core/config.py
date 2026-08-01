from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_SECRET_KEY = "talkbi-dev-secret-key"
DEMO_SEED_ENVIRONMENTS = {"development", "test"}
PROTECTED_ENVIRONMENTS = {"staging", "production"}


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

    @property
    def normalized_environment(self) -> str:
        return (self.environment or "").strip().lower()

    def should_seed_demo_users(self) -> bool:
        return self.normalized_environment in DEMO_SEED_ENVIRONMENTS

    def validate_production_safety(self) -> None:
        if (
            self.normalized_environment in PROTECTED_ENVIRONMENTS
            and self.secret_key == DEFAULT_SECRET_KEY
        ):
            raise RuntimeError(
                "SECRET_KEY must be set to a non-default value in staging/production."
            )


settings = Settings()
