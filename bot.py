import os
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging
import asyncio

# === ?? НАСТРОЙКИ ===
TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"  # ?? ВСТАВЬ СВОЙ ТОКЕН СЮДА!
WEBHOOK_URL = "https://mrhouseklg-bot.onrender.com/webhook"

# === ЛОГИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === СОЗДАЁМ ПРИЛОЖЕНИЕ Telegram ===
application = Application.builder().token(TOKEN).build()

# === ОБРАБОТЧИКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Узнать стоимость строительства", callback_data="price"),
         InlineKeyboardButton("Наши проекты", callback_data="projects")],
        [InlineKeyboardButton("Контакты", callback_data="contacts"),
         InlineKeyboardButton("О компании", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("?? Привет! Я бот MR.House. Чем могу помочь?", reply_markup=reply_markup)

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("? Бот активен и получает апдейты!")

# Регистрируем команды
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("debug", debug))

# === Flask приложение ===
web_app = Flask(__name__)

@web_app.route("/", methods=["GET"])
def index():
    return "? MR.House бот работает!"

@web_app.route("/set_webhook", methods=["GET"])
def set_webhook():
    try:
        asyncio.get_event_loop().run_until_complete(
            application.bot.set_webhook(WEBHOOK_URL)
        )
        return f"Webhook установлен на {WEBHOOK_URL}"
    except Exception as e:
        return f"Ошибка при установке вебхука: {e}"

@web_app.route("/webhook", methods=["POST"])
async def webhook():
    """Получаем апдейты от Telegram"""
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        logger.info(f"?? Получен апдейт от Telegram: {update}")
        await application.initialize()
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Ошибка обработки апдейта: {e}")
    return "OK"

if __name__ == "__main__":
    # Локальный запуск
    asyncio.get_event_loop().run_until_complete(application.bot.set_webhook(WEBHOOK_URL))
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
