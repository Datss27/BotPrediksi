from pydantic import BaseSettings

class Settings(BaseSettings):
    timezone: str = "Asia/Makassar"
    api_key: str
    telegram_token: str
    webhook_url: str
    port: int = 8080

    class Config:
        env_file = ".env"

settings = Settings()
