from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_key: str
    telegram_token: str
    webhook_url: str
    timezone: str = "Asia/Makassar"
    base_url: str = "https://v3.football.api-sports.io"
    port: int = 8080

    class Config:
        env_file = ".env"

settings = Settings()
