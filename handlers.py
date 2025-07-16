from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, Application
from datetime import datetime, timedelta, date
from excel_utils import create_workbook
import os
import asyncio

semaphore = asyncio.Semaphore(3)
api_client = None
TZ = None

def init(client, tz):
    global api_client, TZ
    api_client = client
    TZ = tz

async def limited_get_fixture(date):
    async with semaphore:
        await asyncio.sleep(1)  # tambahkan delay 1 detik untuk aman
        return await api_client.get_fixtures(date)

async def prediksi_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Hari Ini", callback_data="today")],
        [InlineKeyboardButton("Besok", callback_data="tomorrow")],
    ])
    await update.message.reply_text("Pilih tanggal prediksi Boskuuu:", reply_markup=kb)

async def prediksi_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    choice = update.callback_query.data
    await update.callback_query.answer()

    today = datetime.now(TZ).date()

    if choice in ("today", "tomorrow"):
        target_date = today + timedelta(days=1 if choice == "tomorrow" else 0)
        await update.callback_query.edit_message_text(f"Eksekusi prediksi {target_date} Boskuuu")

        try:
            fixtures = await api_client.get_fixtures(target_date)
        except Exception as e:
            await update.callback_query.edit_message_text(f"❌ Gagal ambil prediksi: {e}")
            return

    # Buat file Excel dan kirim
    try:
        file_path, total = create_workbook(fixtures)
        caption = f"Total prediksi: {total} pertandingan"
        await ctx.bot.send_document(chat_id=update.effective_chat.id, document=file_path, filename="prediksi.xlsx", caption=caption)
    except Exception as e:
        await ctx.bot.send_message(chat_id=update.effective_chat.id, text=f"❌ Gagal membuat atau mengirim file: {e}")

def register_handlers(app: Application):
    app.add_handler(CommandHandler("prediksi", prediksi_command))
    app.add_handler(CallbackQueryHandler(prediksi_callback, pattern="^(today|tomorrow)$"))
