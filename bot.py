import os
import asyncio
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# === Конфигурация ===
TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"  # вставь свой токен
WEBHOOK_URL = "https://mrhouseklg-bot.onrender.com/webhook"

# Flask приложение
web_app = Flask(__name__)

# Telegram Application
application = Application.builder().token(TOKEN).build()


# === Главное меню ===
def get_main_menu():
    keyboard = [
        ["Посмотреть готовые дома", "Узнать стоимость строительства"],
        ["Посмотреть проекты и цены", "Задать вопросы"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"📩 Пользователь {update.effective_user.id} запустил /start")
    welcome_text = (
        "Добро пожаловать в бот Mr. House 👷‍♂️\n"
        "Здесь Вы можете ознакомиться с нашими проектами, посмотреть готовые дома, "
        "узнать стоимость строительства и задать вопросы нашему помощнику."
    )
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu())


# === Команда /debug ===
async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot = context.bot
    me = await bot.get_me()
    await update.message.reply_text(
        f"✅ Бот активен!\n\nИмя: {me.first_name}\nUsername: @{me.username}\nID: {me.id}"
    )


# === Обработка сообщений ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    print(f"💬 Получено сообщение: {text}")

    if text == "Посмотреть готовые дома":
        await update.message.reply_text("🏡 Готовые дома:\n\nРаздел в разработке...")
    elif text == "Узнать стоимость строительства":
        await update.message.reply_text("💰 Стоимость строительства:\n\nРаздел в разработке...")
    elif text == "Посмотреть проекты и цены":
        await update.message.reply_text("📐 Проекты и цены:\n\nРаздел в разработке...")
    elif text == "Задать вопросы":
        await update.message.reply_text("❓ Напишите свой вопрос — менеджер ответит!")
    else:
        await update.message.reply_text("Используйте кнопки ниже:", reply_markup=get_main_menu())


# === Регистрация обработчиков ===
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("debug", debug))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


# === Flask маршруты ===
@web_app.route('/')
def home():
    return "✅ Mr. House Bot работает!"


@web_app.route('/set_webhook')
async def set_webhook():
    await application.bot.set_webhook(url=WEBHOOK_URL)
    return f"✅ Webhook установлен на {WEBHOOK_URL}"


@web_app.route('/webhook', methods=['POST'])
async def webhook():
    data = request.get_json(force=True)
    print(f"📨 Получен апдейт от Telegram: {data}")
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return "OK", 200


# === Инициализация бота при запуске сервера ===
async def start_bot():
    print("🚀 Инициализация Telegram Application...")
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(url=WEBHOOK_URL)
    print("✅ Бот инициализирован и webhook установлен.")


# === Запуск через отдельный event loop ===
def run_bot_background():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_bot())
    loop.run_forever()


if __name__ == "__main__":
    import threading

    # Запускаем Telegram Application в отдельном потоке
    threading.Thread(target=run_bot_background, daemon=True).start()

    # Запускаем Flask
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
