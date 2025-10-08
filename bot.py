# bot.py
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request, jsonify
import asyncio
import os

# 🔑 ЗАМЕНИ ЭТОТ ТОКЕН НА СВОЙ ОТ BOTFATHER!
TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"

# URL вашего вебхука (например, https://your-app.onrender.com/webhook)
# На Render/PythonAnywhere он будет таким: https://<ваш-сайт>.onrender.com/webhook
WEBHOOK_URL = "https://mr-house-bot.onrender.com/webhook"  # ← ЗАМЕНИТЕ НА СВОЙ!

# Главное меню с кнопками
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

# === ИНИЦИАЛИЗАЦИЯ TELEGRAM APPLICATION ===
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ВАЖНО: инициализируем Application вручную, чтобы создать update_queue
asyncio.run(app.initialize())

# === FLASK ПРИЛОЖЕНИЕ ===
application = Flask(__name__)

@application.route('/webhook', methods=['POST'])
def webhook():
    # Получаем JSON от Telegram
    json_data = request.get_json(force=True)
    # Преобразуем в объект Update
    update = Update.de_json(json_data, app.bot)
    # Помещаем в очередь обработки
    asyncio.run_coroutine_threadsafe(app.update_queue.put(update), app._update_loop)
    return 'OK', 200

@application.route('/')
def home():
    return '✅ Mr. House Bot работает!'

# === УСТАНОВКА WEBHOOK (опционально — можно сделать один раз вручную) ===
@application.route('/set_webhook')
def set_webhook():
    asyncio.run(app.bot.set_webhook(url=WEBHOOK_URL))
    return f'Webhook установлен на {WEBHOOK_URL}'

@application.route('/delete_webhook')
def delete_webhook():
    asyncio.run(app.bot.delete_webhook(drop_pending_updates=True))
    return 'Webhook удалён'