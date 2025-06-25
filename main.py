import os
import json
import logging
from datetime import datetime
from fastapi import FastAPI, Request
from telegram.ext import ApplicationBuilder
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager
import uvicorn
from telegram import Update
from settings import settings
from api_client import ApiSportsClient
from handlers import init as init_handlers, register_handlers

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global config
TZ = ZoneInfo(settings.timezone)

# Load liga.json
def load_ligas(path: str = "liga.json") -> dict[int, dict[str, str]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {item["id"]: {"nama": item["nama"], "negara": item["negara"], "kode": item["kode"]} for item in data}

LIGA_FILTER = load_ligas()

# Bot & FastAPI
bot = ApplicationBuilder().token(settings.telegram_token).build()
api_client = ApiSportsClient(settings.base_url, {"x-apisports-key": settings.api_key})
init_handlers(api_client, TZ)
register_handlers(bot)

app = FastAPI()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.initialize()
    await bot.start()
    await api_client.init_session()
    await bot.bot.set_webhook(f"{settings.webhook_url}/telegram")
    yield
    await bot.stop()
    await api_client.close()

app.router.lifespan_context = lifespan

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/telegram")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, bot.bot)
    await bot.update_queue.put(update)
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
