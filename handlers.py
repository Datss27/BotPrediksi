from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, Application
from datetime import datetime, timedelta
from excel_utils import create_workbook
import os

api_client = None
TZ = None

def init(client, tz):
    global api_client, TZ
    api_client = client
    TZ = tz

async def prediksi_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Hari Ini", callback_data="today")],
        [InlineKeyboardButton("Besok", callback_data="tomorrow")],
    ])
    await update.message.reply_text("Pilih tanggal prediksi:", reply_markup=kb)

async def prediksi_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    choice = update.callback_query.data
    await update.callback_query.answer()
    target = datetime.now(TZ) + timedelta(days=1 if choice == "tomorrow" else 0)
    date_str = target.strftime("%Y-%m-%d")
    await update.callback_query.edit_message_text(f"Memproses prediksi {date_str}...")

    fixtures = await api_client.get_fixtures(date_str)
    file_path, total = create_workbook(fixtures)
    caption = f"Total prediksi: {total} pertandingan"
    with open(file_path, "rb") as file:
        await ctx.bot.send_document(chat_id=update.effective_chat.id, document=file, caption=caption)
    os.remove(file_path)

def register_handlers(app: Application):
    app.add_handler(CommandHandler("prediksi", prediksi_command))
    app.add_handler(CallbackQueryHandler(prediksi_callback, pattern="^(today|tomorrow)$"))
