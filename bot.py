# bot.py
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, request
import asyncio

# 🔑 ЗАМЕНИ ЭТОТ ТОКЕН НА СВОЙ ОТ BOTFATHER!
TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"

# Главное меню с кнопками
def get_main_menu():
    from telegram import ReplyKeyboardMarkup
    keyboard = [
        ["Посмотреть готовые дома", "Узнать стоимость строительства"],
        ["Посмотреть проекты и цены", "Задать вопросы"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "Добро пожаловать в бот Mr. House 👷‍♂️\n"
        "Здесь Вы можете ознакомиться с нашими проектами, посмотреть готовые дома, "
        "узнать стоимость строительства домов и задать вопросы нашему помощнику"
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu())

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "Посмотреть готовые дома":
        await update.message.reply_text(
            "🏡 Готовые дома:\n\n"
            "Раздел в разработке. Скоро здесь будут фото и описание готовых домов!"
        )
    elif text == "Узнать стоимость строительства":
        await update.message.reply_text(
            "💰 Стоимость строительства:\n\n"
            "Раздел в разработке. Скоро вы сможете рассчитать стоимость дома под ключ!"
        )
    elif text == "Посмотреть проекты и цены":
        await update.message.reply_text(
            "📐 Проекты и цены:\n\n"
            "Раздел в разработке. Скоро здесь будут каталог проектов с ценами!"
        )
    elif text == "Задать вопросы":
        await update.message.reply_text(
            "❓ Задать вопросы:\n\n"
            "Напишите свой вопрос прямо здесь — наш менеджер ответит вам в ближайшее время!\n"
            "Или позвоните нам: +7 (999) 123-45-67"
        )
    else:
        await update.message.reply_text(
            "Извините, я вас не понял. Пожалуйста, используйте кнопки ниже:",
            reply_markup=get_main_menu()
        )

# === НАСТРОЙКА FLASK И WEBHOOK ===

# Создаём Telegram-приложение
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Создаём Flask-приложение (это то, что ожидает PythonAnywhere)
application = Flask(__name__)

@application.route('/webhook', methods=['POST'])
def webhook():
    # Получаем обновление от Telegram и передаём боту
    asyncio.run(app.update_queue.put(Update.de_json(request.get_json(force=True), app.bot)))
    return 'OK', 200

@application.route('/')
def home():
    return '✅ Mr. House Bot работает! Не удаляй этот сайт — он нужен для Telegram.'