import logging
import uvicorn
from fastapi import FastAPI, Request
from telegram.ext import ApplicationBuilder
from contextlib import asynccontextmanager
from settings import settings
from handlers import router, api_client

# logging minimal
logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI()
bot_app = ApplicationBuilder().token(settings.telegram_token).build()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.initialize()
    await bot.start()
    await api_client.init_session()  # ✅ Inisialisasi session setelah loop aktif
    await bot.bot.set_webhook(f"{Config.WEBHOOK_URL}/telegram")
    yield
    await bot.stop()
    await api_client.close()

app.router.lifespan_context = lifespan

app.include_router(router)

@app.get("/")
def health():
    return {"status": "running"}

@app.post("/telegram")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.update_queue.put(update)
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False
    )
