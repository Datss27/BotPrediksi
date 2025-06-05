import requests
import pytz
import time
import os
from dotenv import load_dotenv
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

# 🔐 Ganti token & API key Anda
#TELEGRAM_TOKEN = "7466985733:AAEklNiGSFAKSk0rD5HKfH4Gw-i3iYbObYk"
#API_KEY = "d963595ca57821e552144e6b333e51b5"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("API_FOOTBALL_KEY")
headers = {
    "x-apisports-key": API_KEY
}

# 🔄 Ambil fixture hari ini dengan status NS
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

# ✅ Ambil semua fixture_id tanpa filter timezone
def get_all_fixture_ids(fixtures):
    return [fixture["fixture"]["id"] for fixture in fixtures]

# 📊 Ambil prediksi untuk 1 fixture
def get_prediction(fixture_id):
    fixture_id = fixture["fixture"]["id"]
    home_team = fixture["teams"]["home"]["name"]
    away_team = fixture["teams"]["away"]["name"]

    # Waktu lokal Asia/Jakarta
    utc_time = datetime.strptime(fixture["fixture"]["date"], "%Y-%m-%dT%H:%M:%S%z")
    jakarta_time = utc_time.astimezone(pytz.timezone("Asia/Jakarta"))
    waktu_main = jakarta_time.strftime("%H:%M %d-%m-%Y")

    # Ambil prediksi
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
async def prediksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Mengambil prediksi semua pertandingan hari ini...")
    fixtures = get_fixtures_today()
    fixture_ids = get_all_fixture_ids(fixtures)

    if not fixture_ids:
        await update.message.reply_text("❌ Tidak ada pertandingan hari ini.")
        return

    for fid in fixture_ids:
        prediksi = get_prediction(fid)
        await update.message.reply_text(prediksi)
        time.sleep(1.2)
# 🚀 Jalankan Bot
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("prediksi", prediksi))
    print("✅ Bot berjalan... kirim /prediksi di Telegram")
    app.run_polling()
