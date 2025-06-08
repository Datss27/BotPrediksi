import os, sys, json, requests
from datetime import datetime, timedelta
from dateutil import parser
import pytz
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

API_SPORTS_KEY = "d963595ca57821e552144e6b333e51b5"
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_SPORTS_KEY}

TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = None  # akan diambil secara dinamis dari update.message.chat_id

def load_ligas():
    with open("liga.json", "r", encoding="utf-8") as f:
        return {l["id"]: l["nama"] for l in json.load(f)}

liga_ids = load_ligas()

def fetch_and_create(date_str):
    params = {"date": date_str, "status": "NS"}
    res = requests.get(f"{BASE_URL}/fixtures", headers=HEADERS, params=params)
    fixtures = res.json().get("response", [])
    filtered = [f for f in fixtures if f["league"]["id"] in liga_ids]

    wb = Workbook()
    ws = wb.active
    ws.title = f"Prediksi {date_str}"
    headers_excel = [
        "Liga","Home","Away","Waktu","Prediksi","Saran",
        "Prob Home","Prob Draw","Prob Away",
        "Form Home","Form Away"
    ]
    ws.append(headers_excel)

    fill_header = PatternFill("solid", fgColor="FFD966")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        cell.fill = fill_header
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers_excel))}1"

    for f in filtered:
        fid = f["fixture"]["id"]
        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]
        utc_dt = parser.isoparse(f["fixture"]["date"])
        waktu = utc_dt.astimezone(pytz.timezone("Asia/Jakarta")).strftime("%d-%m-%Y %H:%M WIB")
        pred = requests.get(f"{BASE_URL}/predictions", headers=HEADERS, params={"fixture": fid}).json().get("response",[])
        if not pred: continue
        p = pred[0]["predictions"]
        winner = p.get("winner",{}).get("name","-")
        advice = p.get("advice","-")
        percent = p.get("percent", {})
        home_form = pred[0]["teams"]["home"]["last_5"]["form"]
        away_form = pred[0]["teams"]["away"]["last_5"]["form"]

        ws.append([
            liga_ids[f["league"]["id"]], home, away, waktu, winner, advice,
            percent.get("home"), percent.get("draw"), percent.get("away"),
            home_form, away_form
        ])

    # Autosize
    for col in ws.columns:
        width = max(len(str(c.value)) for c in col if c.value) + 2
        ws.column_dimensions[col[0].column_letter].width = width

    fn = f"prediksi_{date_str}_{datetime.now().strftime('%H%M%S')}.xlsx"
    wb.save(fn)
    return fn, len(filtered)

async def cmd_prediksi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Hari Ini", callback_data="pr_today")],
        [InlineKeyboardButton("Besok", callback_data="pr_tomorrow")]
    ])
    await update.message.reply_text("Pilih prediksi:", reply_markup=kb)

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cb = query.data
    date_str = datetime.today().strftime("%Y-%m-%d") if cb == "pr_today" else (datetime.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    fn, count = fetch_and_create(date_str)
    await ctx.bot.send_document(chat_id=query.message.chat_id, document=open(fn, "rb"),
                                caption=f"Prediksi {date_str} ({count} pertandingan)")
    os.remove(fn)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("prediksi", cmd_prediksi))
    app.add_handler(CallbackQueryHandler(on_button, pattern="^pr_"))
    app.run_polling()

if __name__ == "__main__":
    main()
