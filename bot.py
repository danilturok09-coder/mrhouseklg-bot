import os
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import logging
import asyncio

# === 🔧 НАСТРОЙКИ ===
TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"
WEBHOOK_URL = "https://mrhouseklg-bot.onrender.com/webhook"

# === ЛОГИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Telegram приложение ===
application = Application.builder().token(TOKEN).build()

# === 🏠 Приветствие ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🏗️ Узнать стоимость строительства", callback_data="price"),
         InlineKeyboardButton("📐 Наши проекты", callback_data="projects")],
        [InlineKeyboardButton("📞 Контакты", callback_data="contacts"),
         InlineKeyboardButton("ℹ️ О компании", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        "👋 Привет! Добро пожаловать в <b>MR.House</b> — эксперт по загородной недвижимости и строительству домов под ключ.\n\n"
        "🏡 Мы поможем вам:\n"
        "• Узнать стоимость строительства дома\n"
        "• Ознакомиться с нашими проектами\n"
        "• Получить консультацию и контакты\n\n"
        "Выберите нужный пункт ниже 👇"
    )

    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="HTML")


# === /debug — проверка связи ===
async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот активен и получает апдейты!")


# === 💬 Обработка нажатий на кнопки ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # подтверждаем нажатие

    if query.data == "price":
        await query.message.reply_text("💰 Стоимость строительства зависит от проекта. Мы можем рассчитать примерную цену — свяжитесь с нами для консультации!")
    elif query.data == "projects":
        await query.message.reply_text("📐 Наши проекты включают дома от 80 до 250 м². Скоро здесь появятся ссылки на галерею!")
    elif query.data == "contacts":
        await query.message.reply_text("📞 Наши контакты:\nТелефон: +7 (999) 123-45-67\nInstagram: @mr.house\nСайт: mrhouse.ru")
    elif query.data == "about":
        await query.message.reply_text("ℹ️ Мы — компания MR.House, специализирующаяся на загородной недвижимости и строительстве домов под ключ по Калининградской области.")
    else:
        await query.message.reply_text("❓ Неизвестная команда.")


# === Регистрируем обработчики ===
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("debug", debug))
application.add_handler(CallbackQueryHandler(button_handler))

# === Flask-приложение ===
web_app = Flask(__name__)

@web_app.route("/", methods=["GET"])
def index():
    return "✅ MR.House бот работает!"

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
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        logger.info(f"📨 Получен апдейт от Telegram: {update}")
        await application.initialize()
        await application.process_update(update)
    except Exception as e:
        logger.error(f"Ошибка обработки апдейта: {e}")
    return "OK"


# === Запуск локально или на Render ===
if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(application.bot.set_webhook(WEBHOOK_URL))
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
