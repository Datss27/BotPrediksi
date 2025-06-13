import os
import json
import logging
import tempfile
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any

import aiohttp
import asyncio
from dateutil import parser
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from fastapi import FastAPI
from fastapi import Request
import uvicorn

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Environment variables
API_SPORTS_KEY = os.getenv("API_FOOTBALL_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # contoh: https://your-project.up.railway.app
PORT = int(os.getenv("PORT", 8080))

LIGA_FILE = "liga.json"
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_SPORTS_KEY}
TIMEZONE = os.getenv("TIMEZONE", "Asia/Jakarta")


if not API_SPORTS_KEY or not TELEGRAM_TOKEN or not WEBHOOK_URL:
    logger.error("Missing required environment variables")
    raise RuntimeError("Missing API key, Telegram token, or Webhook URL")

# Load liga filter
def load_ligas(path: str = LIGA_FILE) -> Dict[int, str]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {item["id"]: item["nama"] for item in data}

LIGA_FILTER = load_ligas()

# Create FastAPI app
app_web = FastAPI()

# Create Telegram bot app globally
bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

def create_workbook(
    fixtures: List[Dict[str, Any]],
    filter_liga: bool = True,
) -> Tuple[str, int]:
    wb = Workbook()
    ws = wb.active
    date_str = datetime.now().strftime("%Y-%m-%d")
    ws.title = f"Prediksi {date_str}"
    headers = [
        "Liga", "Home", "Away", "Waktu", "Prediksi", "Saran",
        "Prob Home", "Prob Draw", "Prob Away",
        "Form Home", "Form Away",
    ]
    ws.append(headers)
    header_fill = PatternFill("solid", fgColor="FFD966")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        cell.fill = header_fill
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    count = 0
    for f in fixtures:
        liga_id = f["league"]["id"]
        # Hanya proses liga yang diinginkan (jika filter_liga=True)
        if filter_liga and liga_id not in LIGA_FILTER:
            continue

        # Ambil data prediksi, jika ada
        pred_data = f.get("prediction")
        if pred_data:
            p = pred_data[0]["predictions"]
            winner = p.get("winner", {}).get("name", "-")
            advice = p.get("advice", "-")
            percent = p.get("percent", {})
            home_prob = percent.get("home")
            draw_prob = percent.get("draw")
            away_prob = percent.get("away")
            home_form = pred_data[0]["teams"]["home"]["last_5"]["form"]
            away_form = pred_data[0]["teams"]["away"]["last_5"]["form"]
        else:
            # Jika prediksi tidak tersedia, isi dengan default "-"
            winner = "-"
            advice = "-"
            home_prob = "-"
            draw_prob = "-"
            away_prob = "-"
            home_form = "-"
            away_form = "-"

        league_name = LIGA_FILTER.get(liga_id, f["league"]["name"]) if filter_liga else f["league"]["name"]
        fixture_date = parser.isoparse(f["fixture"]["date"]).astimezone(tz=None)
        waktu = fixture_date.strftime("%d-%m-%Y %H:%M %Z")

        ws.append([
            league_name,
            f["teams"]["home"]["name"],
            f["teams"]["away"]["name"],
            waktu,
            winner,
            advice,
            home_prob,
            draw_prob,
            away_prob,
            home_form,
            away_form,
        ])
        count += 1

    # Sesuaikan lebar kolom
    for col in ws.columns:
        max_length = max(len(str(cell.value)) for cell in col if cell.value is not None)
        ws.column_dimensions[col[0].column_letter].width = max_length + 2

    tmp = tempfile.NamedTemporaryFile(prefix="prediksi_", suffix=".xlsx", delete=False)
    wb.save(tmp.name)
    logger.info("Workbook saved: %s with %d entries", tmp.name, count)
    return tmp.name, count


async def fetch_fixtures(date_str: str) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}/fixtures"
    params = {"date": date_str, "status": "NS", "timezone": TIMEZONE}

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                fixtures = data.get("response", [])
                logger.info(f"Total semua pertandingan: {len(fixtures)}")
        except Exception as e:
            logger.error(f"Gagal mengambil daftar fixtures: {e}")
            return []

        # ✅ Filter hanya liga yang ada di LIGA_FILTER
        filtered_fixtures = [
            f for f in fixtures if f["league"]["id"] in LIGA_FILTER
        ]
        logger.info(f"Total pertandingan dari liga yang difilter: {len(filtered_fixtures)}")

        # ✅ Fungsi async untuk ambil prediksi dengan penanganan error
        async def attach_prediction(fixture: Dict[str, Any]) -> Dict[str, Any]:
            fid = fixture["fixture"]["id"]
            pred_url = f"{BASE_URL}/predictions"
            try:
                async with session.get(pred_url, params={"fixture": fid}) as presp:
                    pdata = await presp.json()
                    fixture["prediction"] = pdata.get("response", [])
            except Exception as e:
                logger.warning(f"Gagal ambil prediksi untuk fixture {fid}: {e}")
                fixture["prediction"] = []
            return fixture

        # ✅ Buat semua permintaan prediksi secara paralel
        tasks = [asyncio.create_task(attach_prediction(f)) for f in filtered_fixtures]
        return await asyncio.gather(*tasks)


# Telegram handlers
async def cmd_prediksi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Hari Ini", callback_data="pr_today")],
        [InlineKeyboardButton("Besok", callback_data="pr_tomorrow")],
    ])
    await update.message.reply_text("Pilih prediksi liga tertentu:", reply_markup=kb)

async def cmd_semua(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Hari Ini", callback_data="allpr_today")],
        [InlineKeyboardButton("Besok", callback_data="allpr_tomorrow")],
    ])
    await update.message.reply_text("Pilih prediksi untuk semua liga:", reply_markup=kb)

async def handle_prediksi(update: Update, ctx: ContextTypes.DEFAULT_TYPE, all_flag: bool):
    query = update.callback_query
    await query.answer()
    choice = query.data
    today = datetime.now()
    target = today if choice.endswith("today") else today + timedelta(days=1)
    date_str = target.strftime("%Y-%m-%d")
    await query.edit_message_text(text=f"Memproses prediksi untuk {date_str}...")
    fixtures = await fetch_fixtures(date_str)
    fn, count = create_workbook(fixtures, filter_liga=not all_flag)
    cap = f"Total prediksi: {count} pertandingan" if not all_flag else f"Total semua prediksi: {count} pertandingan"
    await ctx.bot.send_document(chat_id=query.message.chat_id, document=open(fn, "rb"), caption=cap)
    os.remove(fn)

bot_app.add_handler(CommandHandler("prediksi", cmd_prediksi))
bot_app.add_handler(CommandHandler("semua", cmd_semua))
bot_app.add_handler(CallbackQueryHandler(lambda u, c: handle_prediksi(u, c, False), pattern="^pr_"))
bot_app.add_handler(CallbackQueryHandler(lambda u, c: handle_prediksi(u, c, True), pattern="^allpr_"))
    
    # FastAPI endpoints
@app_web.get("/")
def root():
    return {"status": "running"}

@app_web.post("/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.update_queue.put(update)
    return {"ok": True}

# Startup event
@app_web.on_event("startup")
async def on_startup():
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.bot.set_webhook(f"{WEBHOOK_URL}/telegram")
    logger.info("Bot initialized and webhook set to %s/telegram", WEBHOOK_URL)

if __name__ == "__main__":
    uvicorn.run("main:app_web", host="0.0.0.0", port=PORT)
