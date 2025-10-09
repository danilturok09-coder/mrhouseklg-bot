# bot.py
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request
import asyncio

TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"  # ← Обязательно замените!

def get_main_menu():
    from telegram import ReplyKeyboardMarkup
    keyboard = [
        ["Посмотреть готовые дома", "Узнать стоимость строительства"],
        ["Посмотреть проекты и цены", "Задать вопросы"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "Добро пожаловать в бот Mr. House 👷‍♂️\n"
        "Здесь Вы можете ознакомиться с нашими проектами, посмотреть готовые дома, "
        "узнать стоимость строительства домов и задать вопросы нашему помощнику"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu())

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
    asyncio.run(app.process_update(update))  # ← Обрабатываем сразу!
    return 'OK', 200

@web_app.route('/set_webhook')
def set_webhook():
    WEBHOOK_URL = "https://mrhouseklg-bot.onrender.com/webhook"
    asyncio.run(app.bot.set_webhook(url=WEBHOOK_URL))
    return f"✅ Webhook установлен на {WEBHOOK_URL}"

@web_app.route('/')

def home():
    return "✅ Mr. House Bot работает!"
