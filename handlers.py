from datetime import datetime, timedelta
from fastapi import APIRouter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .api_client import ApiSportsClient
from .excel_utils import create_workbook
from settings import settings

router = APIRouter()
api_client = ApiSportsClient()

# muat filter liga dari file liga.json
import json
with open("liga.json", encoding="utf-8") as f:
    LIGA_FILTER = {item["id"] for item in json.load(f)}

@router.message_handler(commands=["prediksi"])
async def prediksi_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Hari Ini", callback_data="today")],
        [InlineKeyboardButton("Besok", callback_data="tomorrow")],
    ])
    await update.message.reply_text("Pilih tanggal prediksi:", reply_markup=kb)

@router.callback_query_handler(lambda c: c.data in ("today","tomorrow"))
async def prediksi_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    choice = update.callback_query.data
    await update.callback_query.answer()
    target = datetime.now() + (timedelta(days=1) if choice=="tomorrow" else timedelta(0))
    date_str = target.strftime("%Y-%m-%d")
    await update.callback_query.edit_message_text(f"Memproses prediksi {date_str}...")

    fixtures = await api_client.get_fixtures(date_str, list(LIGA_FILTER))
    bio, total = create_workbook(fixtures)

    await ctx.bot.send_document(
        chat_id=update.effective_chat.id,
        document=bio,
        filename=f"prediksi_{date_str}.xlsx",
        caption=f"Total prediksi: {total} pertandingan"
    )
