from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, Application
from datetime import datetime, timedelta
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
        [InlineKeyboardButton("Mingguan", callback_data="7days")],
    ])
    await update.message.reply_text("Pilih tanggal prediksi Boskuuu:", reply_markup=kb)

async def prediksi_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    choice = update.callback_query.data
    await update.callback_query.answer()

    if choice in ("today", "tomorrow"):
        target = datetime.now(TZ) + timedelta(days=1 if choice == "tomorrow" else 0)
        date_str = target.strftime("%Y-%m-%d")
        await update.callback_query.edit_message_text(f"Eksekusi prediksi {date_str} Boskuuu")
        fixtures = await api_client.get_fixtures(date_str)

    elif choice == "7days":
        await update.callback_query.edit_message_text("Eksekusi 1 Minggu Boskuuu")

        now = datetime.now(TZ)
        dates = [(now + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

        # Jalankan semua request dengan kontrol semaphore
        tasks = [limited_get_fixture(date) for date in dates]
        results = await asyncio.gather(*tasks)

        # Gabungkan semua hasil
        fixtures = [item for sublist in results for item in sublist]

    # Buat file Excel dan kirim
    file_path, total = create_workbook(fixtures)
    caption = f"Total prediksi: {total} pertandingan"
    await ctx.bot.send_document(chat_id=update.effective_chat.id, document=file_path, filename="prediksi.xlsx", caption=caption)

def register_handlers(app: Application):
    app.add_handler(CommandHandler("prediksi", prediksi_command))
    app.add_handler(CallbackQueryHandler(prediksi_callback, pattern="^(today|tomorrow|7days)$"))
