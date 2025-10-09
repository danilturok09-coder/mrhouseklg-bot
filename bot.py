# bot.py
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
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

def start(update: Update, context: CallbackContext):
    welcome_text = (
        "Добро пожаловать в бот Mr. House 👷‍♂️\n"
        "Здесь Вы можете ознакомиться с нашими проектами, посмотреть готовые дома, "
        "узнать стоимость строительства домов и задать вопросы нашему помощнику"
    )
    update.message.reply_text(welcome_text, reply_markup=get_main_menu())

def handle_message(update: Update, context: CallbackContext):
    text = update.message.text
    if text == "Посмотреть готовые дома":
        update.message.reply_text("🏡 Готовые дома:\n\nРаздел в разработке...")
    elif text == "Узнать стоимость строительства":
        update.message.reply_text("💰 Стоимость строительства:\n\nРаздел в разработке...")
    elif text == "Посмотреть проекты и цены":
        update.message.reply_text("📐 Проекты и цены:\n\nРаздел в разработке...")
    elif text == "Задать вопросы":
        update.message.reply_text(
            "❓ Задать вопросы:\n\nНапишите свой вопрос — менеджер ответит!\nИли звоните: +7 (999) 123-45-67"
        )
    else:
        update.message.reply_text(
            "Извините, я вас не понял. Используйте кнопки ниже:",
            reply_markup=get_main_menu()
        )

# Создаём Updater (старый стиль)
updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher

# Добавляем обработчики
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# Flask app
web_app = Flask(__name__)

@web_app.route('/webhook', methods=['POST'])
def webhook():
    json_data = request.get_json(force=True)
    update = Update.de_json(json_data, updater.bot)
    # Обрабатываем обновление сразу
    asyncio.run(dispatcher.process_update(update))
    return 'OK', 200

@web_app.route('/set_webhook')
def set_webhook():
    WEBHOOK_URL = "https://mrhouseklg-bot.onrender.com/webhook"
    # Устанавливаем вебхук
    updater.bot.set_webhook(url=WEBHOOK_URL)
    return f"✅ Webhook установлен на {WEBHOOK_URL}"

@web_app.route('/')

def home():
    return "✅ Mr. House Bot работает!"
