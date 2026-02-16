from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    notion_key: str
    notion_database_id: str
    database_url: str = "sqlite:///quotes.db"

    # Image Formatting
    default_width: int = 800
    default_height: int = 480
    padding_width: float = 0.0250  # 2.5% width
    padding_height: float = 0.0250  # 2.5% height * 4 = 10% total

    quote_height: float = 0.775  # 77.5% height
    quote_color: str = "white"
    quote_font: str = "resources/fonts/Charter.ttc"
    quote_font_index: int = 3

    title_height: float = 0.075  # 7.5% height
    title_color: str = "white"
    title_font: str = "resources/fonts/Charter.ttc"
    title_font_index: int = 0

    author_height: float = 0.05  # 5% height
    author_color: str = "white"
    author_font: str = "resources/fonts/Charter.ttc"
    author_font_index: int = 0

    # App
    output_dir: str = "data"
    cache_enabled: bool = False
    use_static_bg: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
