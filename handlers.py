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
        [InlineKeyboardButton("Semua", callback_data="both")],
    ])
    await update.message.reply_text("Pilih tanggal prediksi Boskuuu:", reply_markup=kb)

async def prediksi_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    choice = update.callback_query.data
    await update.callback_query.answer()

    today = datetime.now(TZ).date()
    fixtures = []
    total = 0

    try:
        if choice == "today":
            target_date = today
            await update.callback_query.edit_message_text(f"Eksekusi prediksi {target_date} Boskuuu")
            fixtures = await limited_get_fixture(target_date)
        
        elif choice == "tomorrow":
            target_date = today + timedelta(days=1)
            await update.callback_query.edit_message_text(f"Eksekusi prediksi {target_date} Boskuuu")
            fixtures = await limited_get_fixture(target_date)
        
        elif choice == "both":
            await update.callback_query.edit_message_text("Eksekusi prediksi Hari Ini & Besok Boskuuu")
            fixtures_today = await limited_get_fixture(today)
            fixtures_tomorrow = await limited_get_fixture(today + timedelta(days=1))
            fixtures = fixtures_today + fixtures_tomorrow

        # Buat dan kirim file Excel
        file_path, total = create_workbook(fixtures)
        caption = f"Total prediksi: {total} pertandingan"
        await ctx.bot.send_document(chat_id=update.effective_chat.id, document=file_path, filename="prediksi.xlsx", caption=caption)

    except Exception as e:
        await ctx.bot.send_message(chat_id=update.effective_chat.id, text=f"❌ Gagal memproses prediksi: {e}")

def register_handlers(app: Application):
    app.add_handler(CommandHandler("prediksi", prediksi_command))
    app.add_handler(CallbackQueryHandler(prediksi_callback, pattern="^(today|tomorrow|both)$"))
