import logging
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
import pytz

# Load environment variables (optional jika pakai Railway Env)
load_dotenv()

# Logging untuk Railway log viewer
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Token dan API Key dari ENV
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("API_FOOTBALL_KEY")
HEADERS = {"x-apisports-key": API_KEY}

# Liga yang ingin difilter
LEAGUE_IDS = [
    39, 40, 41, 61, 71, 72, 78, 88, 89, 94, 98, 103,
    128, 129, 135, 140, 141, 144, 169, 197, 203, 239,
    253, 262, 265, 290, 292, 296, 301, 305, 308, 345
]

def convert_form(form):
    return form.replace("W", "✅").replace("L", "❌").replace("D", "🔘") if form else ""

async def prediksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Today", callback_data="today"),
         InlineKeyboardButton("📅 Tomorrow", callback_data="tomorrow")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Pilih tanggal prediksi:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date = datetime.now(pytz.timezone("Asia/Jakarta"))
    if query.data == "tomorrow":
        date += timedelta(days=1)

    date_str = date.strftime("%Y-%m-%d")
    fixtures_url = f"https://v3.football.api-sports.io/fixtures?date={date_str}&status=NS"
    response = requests.get(fixtures_url, headers=HEADERS).json()

    rows = []
    for fixture in response.get("response", []):
        league_id = fixture["league"]["id"]
        fixture_id = fixture["fixture"]["id"]

        if league_id not in LEAGUE_IDS:
            continue

        prediction_url = f"https://v3.football.api-sports.io/predictions?fixture={fixture_id}"
        pred_res = requests.get(prediction_url, headers=HEADERS).json()

        if pred_res["results"] == 0:
            continue

        pred = pred_res["response"][0]["predictions"]
        teams = pred_res["response"][0]["teams"]

        home = teams["home"]["name"]
        away = teams["away"]["name"]
        form_home = convert_form(teams["home"].get("league", {}).get("form", ""))
        form_away = convert_form(teams["away"].get("league", {}).get("form", ""))

        winner = pred["winner"]["name"] if pred["winner"] else "-"
        advice = pred.get("advice", "-")
        percent = pred.get("percent", {})

        rows.append({
            "Tanggal": date_str,
            "Home": home,
            "Away": away,
            "Form Home": form_home,
            "Form Away": form_away,
            "Prediksi": winner,
            "Advice": advice,
            "Persen Home": percent.get("home", "-"),
            "Persen Draw": percent.get("draw", "-"),
            "Persen Away": percent.get("away", "-")
        })

    if not rows:
        await query.message.reply_text("Tidak ada prediksi tersedia untuk tanggal tersebut.")
        return

    df = pd.DataFrame(rows)
    file_path = "/tmp/prediksi.xlsx"
    df.to_excel(file_path, index=False)

    await query.message.reply_document(document=open(file_path, "rb"), filename=f"prediksi_{date_str}.xlsx")

# Jalankan bot polling
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("prediksi", prediksi))
    app.add_handler(CallbackQueryHandler(button_handler))

    logging.info("Bot dimulai 🚀")
    app.run_polling()
