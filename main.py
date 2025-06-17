import os
import json
import logging
import tempfile
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

import aiohttp
from dateutil import parser
from zoneinfo import ZoneInfo
from fastapi import FastAPI, Request
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
import uvicorn
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Environment variables
tz_name = os.getenv("TIMEZONE", "Asia/Makassar")
API_SPORTS_KEY = os.getenv("API_FOOTBALL_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # contoh: https://your-project.up.railway.app
PORT = int(os.getenv("PORT", 8080))
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_SPORTS_KEY}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.bot.set_webhook(f"{WEBHOOK_URL}/telegram")
    logger.info("Bot initialized and webhook set to %s/telegram", WEBHOOK_URL)

    yield

    # Shutdown
    await bot_app.stop()
    logger.info("Bot stopped")
# Timezone object
try:
    TZ = ZoneInfo(tz_name)
except Exception:
    logger.warning(f"Timezone '{tz_name}' tidak valid, menggunakan UTC.")
    TZ = ZoneInfo("UTC")

if not API_SPORTS_KEY or not TELEGRAM_TOKEN or not WEBHOOK_URL:
    logger.error("Missing required environment variables")
    raise RuntimeError("Missing API key, Telegram token, or Webhook URL")

# Load liga filter
def load_ligas(path: str = "liga.json") -> Dict[int, str]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {item["id"]: item["nama"] for item in data}

LIGA_FILTER = load_ligas()

# Create FastAPI app
app_web = FastAPI(lifespan=lifespan)

# Create Telegram bot app globally
bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# Excel workbook creation
def create_workbook(fixtures: List[Dict[str, Any]]) -> Tuple[str, int]:
    wb = Workbook()
    ws = wb.active
    date_str = datetime.now(TZ).strftime("%Y-%m-%d")
    ws.title = f"Prediksi {date_str}"

    headers = [
        "Negara", "Liga", "Home", "Away", "Tanggal", "Jam", "Prediksi", "Saran",
        "Prob Home", "Prob Draw", "Prob Away",
        "Form", "ATT", "DEF",
        "Perbandingan",
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
        pred_list = f.get("prediction") or []
        if pred_list:
            pdata = pred_list[0]["predictions"]
            winner = pdata.get("winner", {}).get("name", "-")
            advice = pdata.get("advice", "-")
            percent = pdata.get("percent", {})
            home_prob = percent.get("home")
            draw_prob = percent.get("draw")
            away_prob = percent.get("away")
            home_team = pred_list[0].get("teams", {}).get("home", {}).get("last_5", {})
            away_team = pred_list[0].get("teams", {}).get("away", {}).get("last_5", {})
            home_form = home_team.get("form", "-")
            away_form = away_team.get("form", "-")
            home_att = home_team.get("att", "-")
            away_att = away_team.get("att", "-")
            home_def = home_team.get("def", "-")
            away_def = away_team.get("def", "-")
            comparison = pred_list[0].get("comparison", {}).get("total", {})
            comparison_home = comparison.get("home", "-")
            comparison_away = comparison.get("away", "-")
        else:
            winner = advice = home_prob = draw_prob = away_prob = home_form = away_form = home_att = away_att = home_def = away_def = comparison_home = comparison_away = "-"

        fixture_date = parser.isoparse(f["fixture"]["date"]).astimezone(TZ)
        tanggal = fixture_date.strftime("%d-%m-%Y")
        jam = fixture_date.strftime("%H:%M %Z")
        league_name = f["league"]["name"]

        ws.append([
            f["league"]["country"],
            league_name,
            f["teams"]["home"]["name"],
            f["teams"]["away"]["name"],
            tanggal,
            jam,
            winner,
            advice,
            home_prob,
            draw_prob,
            away_prob,
            f"{home_form} - {away_form}",
            f"{home_att} - {away_att}",
            f"{home_def} - {away_def}",
            f"{comparison_home} - {comparison_away}",
        ])
        count += 1

    # Adjust column widths
    for col in ws.columns:
        max_length = max(len(str(cell.value)) for cell in col if cell.value)
        ws.column_dimensions[col[0].column_letter].width = max_length + 2

    # Save to a temporary file
    tmp = tempfile.NamedTemporaryFile(prefix="prediksi_", suffix=".xlsx", delete=False)
    wb.save(tmp.name)
    logger.info("Workbook saved: %s with %d entries", tmp.name, count)
    return tmp.name, count

# Fetch fixtures with prediction and error handling
async def fetch_fixtures(date_str: str) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}/fixtures"
    params = {"date": date_str, "status": "NS", "timezone": tz_name}

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                fixtures = data.get("response", [])
                logger.info(f"Total fixtures fetched: {len(fixtures)}")
        except Exception as e:
            logger.error(f"Error fetching fixtures: {e}")
            return []

        # filter by league
        fixtures = [f for f in fixtures if f["league"]["id"] in LIGA_FILTER]
        logger.info(f"Fixtures after filter: {len(fixtures)}")

        sem = asyncio.Semaphore(10)  # limit parallel requests
        async def attach_prediction(fixture: Dict[str, Any]) -> Dict[str, Any]:
            async with sem:
                fid = fixture["fixture"]["id"]
                pred_url = f"{BASE_URL}/predictions"
                try:
                    async with session.get(pred_url, params={"fixture": fid}) as presp:
                        pdata = await presp.json()
                    fixture["prediction"] = pdata.get("response", [])
                except Exception as e:
                    logger.warning(f"Failed prediction for {fid}: {e}")
                    fixture["prediction"] = []
            return fixture

        tasks = [asyncio.create_task(attach_prediction(f)) for f in fixtures]
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
    today = datetime.now(TZ)
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

if __name__ == "__main__":
    uvicorn.run("main:app_web", host="0.0.0.0", port=PORT)
