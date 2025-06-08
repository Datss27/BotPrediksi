import os, sys, json, requests
from datetime import datetime, timedelta
from dateutil import parser
import pytz
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

API_SPORTS_KEY = os.getenv("API_FOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_SPORTS_KEY}
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Load league names

def load_ligas():
    with open("liga.json", "r", encoding="utf-8") as f:
        return {l["id"]: l["nama"] for l in json.load(f)}

liga_ids = load_ligas()

# Styling definitions
header_fill = PatternFill("solid", fgColor="4F81BD")  # darker blue
even_fill = PatternFill("solid", fgColor="DCE6F1")   # light blue for even rows
odd_fill = PatternFill("solid", fgColor="FFFFFF")    # white for odd rows
thin_border = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)
align_center = Alignment(horizontal="center", vertical="center")

# Core function to fetch data and write to Excel

def fetch_and_create(date_str):
    params = {"date": date_str, "status": "NS"}
    res = requests.get(f"{BASE_URL}/fixtures", headers=HEADERS, params=params)
    fixtures = res.json().get("response", [])
    filtered = [f for f in fixtures if f["league"]["id"] in liga_ids]

    wb = Workbook()
    ws = wb.active
    ws.title = f"Prediksi {date_str}"

    headers_excel = [
        "Liga", "Home", "Away", "Waktu", "Prediksi", "Saran",
        "Prob Home", "Prob Draw", "Prob Away",
        "Form Home", "Form Away"
    ]
    ws.append(headers_excel)

    # Style header row
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = align_center
        cell.border = thin_border

    # Freeze header
    ws.freeze_panes = 'A2'

    # Populate rows
    for idx, f in enumerate(filtered, start=2):
        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]
        utc_dt = parser.isoparse(f["fixture"]["date"])
        waktu = utc_dt.astimezone(pytz.timezone("Asia/Jakarta")).strftime("%d-%m-%Y %H:%M WIB")
        p_resp = requests.get(f"{BASE_URL}/predictions", headers=HEADERS, params={"fixture": f["fixture"]["id"]}).json().get("response", [])
        if not p_resp:
            continue
        p = p_resp[0]["predictions"]
        winner = p.get("winner", {}).get("name", "-")
        advice = p.get("advice", "-")
        perc = p.get("percent", {})
        home_form = p_resp[0]["teams"]["home"]["last_5"]["form"]
        away_form = p_resp[0]["teams"]["away"]["last_5"]["form"]

        row = [
            liga_ids[f["league"]["id"]], home, away, waktu,
            winner, advice,
            perc.get("home", 0)/100, perc.get("draw", 0)/100, perc.get("away", 0)/100,
            home_form, away_form
        ]
        ws.append(row)

        # Apply styles
        fill = even_fill if idx % 2 == 0 else odd_fill
        for col_idx in range(1, len(headers_excel) + 1):
            cell = ws.cell(row=idx, column=col_idx)
            cell.fill = fill
            cell.border = thin_border
            # Align probabilities and center
            if col_idx in [7, 8, 9]:
                cell.number_format = '0%'
            cell.alignment = align_center

    # Auto-adjust column widths
    for col in ws.columns:
        max_length = max(len(str(cell.value)) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_length + 2

    filename = f"prediksi_{date_str}_{datetime.now().strftime('%H%M%S')}.xlsx"
    wb.save(filename)
    return filename, len(filtered)

# Telegram handlers

async def cmd_prediksi(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Hari Ini", callback_data="pr_today")],
        [InlineKeyboardButton("Besok", callback_data="pr_tomorrow")]
    ])
    await update.message.reply_text("Pilih prediksi:", reply_markup=kb)

async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    date_str = (datetime.utcnow() + (timedelta(days=0 if query.data == "pr_today" else 1))).strftime("%Y-%m-%d")
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
