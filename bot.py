# bot.py
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request
import asyncio

TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"  # ← ОБЯЗАТЕЛЬНО ЗАМЕНИТЬ!

def get_main_menu():
    from telegram import ReplyKeyboardMarkup
    return ReplyKeyboardMarkup([
        ["Посмотреть готовые дома", "Узнать стоимость строительства"],
        ["Посмотреть проекты и цены", "Задать вопросы"]
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Бот работает.", reply_markup=get_main_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Сообщение получено!", reply_markup=get_main_menu())

# Создаём Application
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Flask app
web_app = Flask(__name__)

@web_app.route('/webhook', methods=['POST'])
def webhook():
    json_data = request.get_json(force=True)
    update = Update.de_json(json_data, app.bot)
    asyncio.run(app.process_update(update))  # ← обрабатываем сразу
    return 'OK', 200

@web_app.route('/set_webhook')
def set_webhook():
    # ЗАМЕНИТЕ НА СВОЙ РЕАЛЬНЫЙ URL!
    WEBHOOK_URL = "https://mr-house-bot.onrender.com/webhook"
    asyncio.run(app.bot.set_webhook(url=WEBHOOK_URL))
    return f"Webhook установлен на {WEBHOOK_URL}"

@web_app.route('/')
def home():
    return "✅ Бот запущен!"