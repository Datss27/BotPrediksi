import os
import time
import requests
import pytz
from datetime import datetime
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ⬇️ Load .env untuk development lokal
load_dotenv()

# 🔐 Ambil token dan API key dari environment variable
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("API_FOOTBALL_KEY")
headers = {
    "x-apisports-key": API_KEY
}

# 🔄 Ambil semua fixture hari ini yang belum mulai (status: NS)
def get_fixtures_today():
    today = datetime.now().strftime("%Y-%m-%d")
    url = "https://v3.football.api-sports.io/fixtures"
    params = {
        "status": "NS",
        "date": today
    }
    response = requests.get(url, headers=headers, params=params)
    data = response.json()
    return data.get("response", [])

# 📊 Ambil prediksi berdasarkan 1 fixture lengkap (bukan hanya ID)
def get_prediction(fixture):
    fixture_id = fixture["fixture"]["id"]
    home_team = fixture["teams"]["home"]["name"]
    away_team = fixture["teams"]["away"]["name"]

    # Konversi waktu UTC ke Asia/Jakarta
    utc_time = datetime.strptime(fixture["fixture"]["date"], "%Y-%m-%dT%H:%M:%S%z")
    jakarta_time = utc_time.astimezone(pytz.timezone("Asia/Jakarta"))
    waktu_main = jakarta_time.strftime("%H:%M %d-%m-%Y")

    # Ambil prediksi dari API
    url = "https://v3.football.api-sports.io/predictions"
    params = {"fixture": fixture_id}
    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    if data.get("response"):
        p = data["response"][0]["predictions"]
        winner = p.get("winner", {})
        advice = p.get("advice", "-")
        win_name = winner.get("name", "Tidak ada prediksi")
        comment = winner.get("comment", "")
        
        return (
            f"⚽ *{home_team} vs {away_team}*\n"
            f"🕒 *Kickoff:* `{waktu_main}` WIB\n"
            f"🏆 *Prediksi Pemenang:* _{win_name}_ ({comment})\n"
            f"💡 *Saran:* _{advice}_"
        )
    else:
        return (
            f"⚽ *{home_team} vs {away_team}*\n"
            f"🕒 *Kickoff:* `{waktu_main}` WIB\n"
            f"❌ Prediksi tidak tersedia."
        )

# 🧠 Command /prediksi
async def prediksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Mengambil prediksi semua pertandingan hari ini...")
    fixtures = get_fixtures_today()

    if not fixtures:
        await update.message.reply_text("❌ Tidak ada pertandingan hari ini.")
        return

    for fixture in fixtures:
        prediksi_text = get_prediction(fixture)
        await update.message.reply_text(prediksi_text, parse_mode="Markdown")
        time.sleep(1.2)  # Jeda agar tidak spam API

# 🚀 Jalankan Bot
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("prediksi", prediksi))
    print("✅ Bot berjalan... kirim /prediksi di Telegram")
    app.run_polling()
