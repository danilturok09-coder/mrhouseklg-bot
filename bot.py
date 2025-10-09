import os
import asyncio
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"  # вставь сюда свой токен
WEBHOOK_URL = "https://mrhouseklg-bot.onrender.com/webhook"  # замени на свой URL на Render

# --- Создаём Flask приложение ---
web_app = Flask(__name__)

# --- Создаём Telegram Application ---
application = Application.builder().token(TOKEN).build()

# --- Главное меню ---
def get_main_menu():
    keyboard = [
        ["Посмотреть готовые дома", "Узнать стоимость строительства"],
        ["Посмотреть проекты и цены", "Задать вопросы"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "Добро пожаловать в бот Mr. House 👷‍♂️\n"
        "Здесь Вы можете ознакомиться с нашими проектами, посмотреть готовые дома, "
        "узнать стоимость строительства домов и задать вопросы нашему помощнику."
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu())

# --- Обработка сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "Посмотреть готовые дома":
        await update.message.reply_text("🏡 Готовые дома:\n\nРаздел в разработке...")
    elif text == "Узнать стоимость строительства":
        await update.message.reply_text("💰 Стоимость строительства:\n\nРаздел в разработке...")
    elif text == "Посмотреть проекты и цены":
        await update.message.reply_text("📐 Проекты и цены:\n\nРаздел в разработке...")
    elif text == "Задать вопросы":
        await update.message.reply_text(
            "❓ Задать вопросы:\n\nНапишите свой вопрос — менеджер ответит!\nИли звоните: +7 (999) 123-45-67"
        )
    else:
        await update.message.reply_text(
            "Извините, я вас не понял. Используйте кнопки ниже:",
            reply_markup=get_main_menu()
        )

# --- Регистрируем обработчики ---
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --- Flask webhook маршруты ---
@web_app.route('/webhook', methods=['POST'])
async def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return "OK", 200

@web_app.route('/set_webhook')
def set_webhook():
    asyncio.run(application.bot.set_webhook(url=WEBHOOK_URL))
    return f"✅ Webhook установлен на {WEBHOOK_URL}"


@web_app.route('/')
def home():
    return "✅ Mr. House Bot работает!"

# --- Точка входа ---
if __name__ == '__main__':
    async def main():
        # Инициализация и запуск приложения (важно для PTB v20+)
        await application.initialize()
        await application.bot.set_webhook(url=WEBHOOK_URL)
        await application.start()
        print("✅ Bot initialized and running via webhook")

    asyncio.run(main())
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
