from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    notion_key: str
    notion_database_id: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

NOTION_KEY = settings.notion_key
NOTION_DATABASE_ID = settings.notion_database_id
