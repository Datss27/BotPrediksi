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
from openpyxl.formatting.rule import FormulaRule

# --- Konfigurasi Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Load Environment & Konfigurasi ---
class Config:
    TZ_NAME: str = os.getenv("TIMEZONE", "Asia/Makassar")
    API_KEY: str = os.getenv("API_FOOTBALL_KEY")
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL")
    PORT: int = int(os.getenv("PORT", 8080))
    BASE_URL: str = "https://v3.football.api-sports.io"

# Validasi env
if not (Config.API_KEY and Config.TELEGRAM_TOKEN and Config.WEBHOOK_URL):
    logger.error("Missing required environment variables")
    raise RuntimeError("Missing API key, Telegram token, or Webhook URL")

# Timezone
try:
    TZ = ZoneInfo(Config.TZ_NAME)
except Exception:
    logger.warning(f"Timezone '{Config.TZ_NAME}' tidak valid, menggunakan UTC.")
    TZ = ZoneInfo("UTC")

# Load liga filter
def load_ligas(path: str = "liga.json") -> Dict[int, str]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {item["id"]: item["nama"] for item in data}

LIGA_FILTER = load_ligas()
HEADERS = {"x-apisports-key": Config.API_KEY}

# --- FastAPI & Telegram Lifespan ---
app = FastAPI()
bot = ApplicationBuilder().token(Config.TELEGRAM_TOKEN).build()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.initialize()
    await bot.start()
    await bot.bot.set_webhook(f"{Config.WEBHOOK_URL}/telegram")
    logger.info("Bot initialized and webhook set to %s/telegram", Config.WEBHOOK_URL)
    yield
    await bot.stop()
    logger.info("Bot stopped")

app.router.lifespan_context = lifespan

# --- API Sports Service ---
class ApiSportsClient:
    def __init__(self, base_url: str, headers: Dict[str, str]):
        self.base_url = base_url
        self.headers = headers
        self.sem = asyncio.Semaphore(3)

    async def fetch_json(self, session: aiohttp.ClientSession, path: str, params: Dict[str, Any]) -> Any:
        url = f"{self.base_url}/{path}"
        async with session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_fixtures(self, date: str) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            resp = await self.fetch_json(session, 'fixtures', {'date': date, 'status': 'NS', 'timezone': Config.TZ_NAME})
            fixtures = resp.get('response', [])
        filtered = [f for f in fixtures if f['league']['id'] in LIGA_FILTER]
        logger.info("Fixtures fetched %d, after filter %d", len(fixtures), len(filtered))
        return await self._attach_predictions(filtered)

    async def _attach_predictions(self, fixtures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.headers) as session:
            tasks = [self._attach(session, f) for f in fixtures]
            return await asyncio.gather(*tasks)

    async def _attach(self, session: aiohttp.ClientSession, fixture: Dict[str, Any]) -> Dict[str, Any]:
        async with self.sem:
            fid = fixture['fixture']['id']
            try:
                data = await self.fetch_json(session, 'predictions', {'fixture': fid})
                fixture['prediction'] = data.get('response', [])
            except Exception as e:
                logger.warning("Failed prediction for %s: %s", fid, e)
                fixture['prediction'] = []
        return fixture

api_client = ApiSportsClient(Config.BASE_URL, HEADERS)

# --- Excel Generator ---
def _extract_row(f: Dict[str, Any]) -> List[Any]:
    # parse prediction data
    pred = f.get('prediction') or []
    if pred:
        p = pred[0]
        pr = p.get('predictions', {})
        win     = pr.get('winner', {}).get('name', '-')
        advice  = pr.get('advice', '-')
        pct     = pr.get('percent', {})
        hp      = pct.get('home') or 0
        dp      = pct.get('draw') or 0
        ap      = pct.get('away') or 0

        teams   = p.get('teams', {})
        home    = teams.get('home', {})
        away    = teams.get('away', {})

        form_home = home.get('last_5', {}).get('form', '-')
        form_away = away.get('last_5', {}).get('form', '-')
        att_home  = home.get('last_5', {}).get('att', '-')
        att_away  = away.get('last_5', {}).get('att', '-')
        def_home  = home.get('last_5', {}).get('def', '-')
        def_away  = away.get('last_5', {}).get('def', '-')

        comp = pr.get('comparison', {}).get('total', {})
        comp_home = comp.get('home') or 0
        comp_away = comp.get('away') or 0

    else:
        win = advice = '-'
        hp = dp = ap = 0
        form_home = form_away = att_home = att_away = def_home = def_away = '-'
        comp_home = comp_away = 0

    # parse date & time
    dt = parser.isoparse(f['fixture']['date']).astimezone(TZ)
    date = dt.strftime("%d-%m-%Y")
    time = dt.strftime("%H:%M %Z")

    return [
        f['league']['country'],
        f['league']['name'],
        f['teams']['home']['name'],
        f['teams']['away']['name'],
        date,
        time,
        win,
        advice,
        hp, dp, ap,
        form_home, form_away,
        att_home,  att_away,
        def_home,  def_away,
        comp_home, comp_away
    ]


def create_workbook(fixtures: List[Dict[str, Any]]) -> Tuple[str, int]:
    wb = Workbook()
    ws = wb.active
    date_str = datetime.now(TZ).strftime("%Y-%m-%d")
    ws.title = f"Prediksi {date_str}"

    flat = ["Negara", "Liga", "Home", "Away", "Tanggal", "Jam",
            "Prediksi", "Saran", "Prob Home", "Prob Draw", "Prob Away"]
    groups = [
        ("Form",        ["Home", "Away"]),
        ("ATT",         ["Home", "Away"]),
        ("DEF",         ["Home", "Away"]),
        ("Perbandingan",["Home", "Away"]),
    ]

    # — Header baris 1 & 2 —
    col = 1
    for h in flat:
        ws.cell(row=1, column=col, value=h)
        col += 1
    for grp, _ in groups:
        ws.cell(row=1, column=col,   value=grp)
        ws.cell(row=1, column=col+1, value=None)
        col += 2

    for i in range(1, len(flat)+1):
        ws.cell(row=2, column=i, value=None)
    col = len(flat) + 1
    for _, subs in groups:
        for sub in subs:
            ws.cell(row=2, column=col, value=sub)
            col += 1

    # — Merge cells untuk flat & grup headers —
    for c in range(1, len(flat)+1):
        ws.merge_cells(start_row=1, start_column=c, end_row=2,   end_column=c)
    start = len(flat) + 1
    for _ in groups:
        ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=start+1)
        start += 2

    # — Style header —
    header_fill = PatternFill("solid", fgColor="FFD966")
    for row in (1, 2):
        for cell in ws[row]:
            cell.font      = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.fill      = header_fill

    # — Auto‐filter dua baris header —
    last_col = get_column_letter(len(flat) + 2*len(groups))
    ws.auto_filter.ref = f"A1:{last_col}2"

    # — Tulis data baris 3 dst. —
    count = 0
    for f in fixtures:
        ws.append(_extract_row(f))
        count += 1

    # — Conditional formatting untuk Perbandingan —
    start_row = 3
    end_row   = 2 + count
    comp_home_idx = len(flat) + 1 + 2*3
    comp_away_idx = comp_home_idx + 1
    col_home = get_column_letter(comp_home_idx)
    col_away = get_column_letter(comp_away_idx)

    # Home > Away → Home biru
    ws.conditional_formatting.add(
        f"{col_home}{start_row}:{col_home}{end_row}",
        FormulaRule(
            formula=[f"{col_home}{start_row}>{col_away}{start_row}"],
            stopIfTrue=True,
            fill=PatternFill("solid", fgColor="BDD7EE")
        )
    )
    # Home = Away → kedua kolom kuning
    ws.conditional_formatting.add(
        f"{col_home}{start_row}:{col_away}{end_row}",
        FormulaRule(
            formula=[f"{col_home}{start_row}={col_away}{start_row}"],
            stopIfTrue=True,
            fill=PatternFill("solid", fgColor="FFF2CC")
        )
    )

    # — Auto‐adjust width (perbaikan) —
    for col_cells in ws.columns:
        # ambil index kolom dari sel pertama, lalu ubah jadi huruf
        idx        = col_cells[0].col_idx
        col_letter = get_column_letter(idx)
        max_len    = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
        ws.column_dimensions[col_letter].width = max_len + 2

    # — Simpan ke file sementara —
    tmp = tempfile.NamedTemporaryFile(prefix="prediksi_", suffix=".xlsx", delete=False)
    wb.save(tmp.name)
    logger.info("Workbook saved: %s with %d entries", tmp.name, count)
    return tmp.name, count

# --- Handlers Bot Telegram ---
async def prediksi_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Hari Ini", callback_data="today")],
        [InlineKeyboardButton("Besok", callback_data="tomorrow")],
    ])
    await update.message.reply_text("Pilih tanggal prediksi:", reply_markup=kb)

async def prediksi_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    choice = update.callback_query.data
    await update.callback_query.answer()
    target = datetime.now(TZ) + (timedelta(days=1) if choice == 'tomorrow' else timedelta(0))
    date_str = target.strftime("%Y-%m-%d")
    await update.callback_query.edit_message_text(f"Memproses prediksi {date_str}...")

    fixtures = await api_client.get_fixtures(date_str)
    file_path, total = create_workbook(fixtures)
    caption = f"Total prediksi: {total} pertandingan"
    with open(file_path,"rb") as file:
        await ctx.bot.send_document(chat_id=update.effective_chat.id, document=file, caption=caption)
    os.remove(file_path)

bot.add_handler(CommandHandler("prediksi", prediksi_command))
bot.add_handler(CallbackQueryHandler(prediksi_callback, pattern="^(today|tomorrow)$"))

# --- Endpoint Webhook ---
@app.get("/")
def health():
    return {"status": "running"}

@app.post("/telegram")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, bot.bot)
    await bot.update_queue.put(update)
    return {"ok": True}

# --- Jalankan ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=Config.PORT)
