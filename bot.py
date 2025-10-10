import os
import threading
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
TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"  # вставь сюда токен
WEBHOOK_URL = "https://mrhouseklg-bot.onrender.com/webhook"

# === Flask ===
web_app = Flask(__name__)

# === Telegram Application ===
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
    await update.message.reply_text(
        "Добро пожаловать в бот Mr. House 👷‍♂️\n"
        "Здесь Вы можете ознакомиться с нашими проектами, посмотреть готовые дома, "
        "узнать стоимость строительства и задать вопросы нашему помощнику.",
        reply_markup=get_main_menu()
    )


# === Команда /debug ===
async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    me = await context.bot.get_me()
    await update.message.reply_text(
        f"✅ Бот активен!\nИмя: {me.first_name}\nUsername: @{me.username}\nID: {me.id}"
    )


# === Обработка обычных сообщений ===
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
        await update.message.reply_text(
            "❓ Напишите свой вопрос — менеджер ответит!\n"
            "Или звоните: +7 (999) 123-45-67"
        )
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
def set_webhook():
    loop = asyncio.get_event_loop()
    loop.create_task(application.bot.set_webhook(url=WEBHOOK_URL))
    return f"✅ Webhook установлен на {WEBHOOK_URL}"


@web_app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(force=True)
    print(f"📨 Получен апдейт от Telegram: {data}")
    update = Update.de_json(data, application.bot)

    # Отправляем обработку в event loop Telegram Application
    asyncio.run_coroutine_threadsafe(application.process_update(update), application.loop)
    return "OK", 200


# === Фоновый запуск бота ===
def run_bot():
    async def start():
        print("🚀 Инициализация Telegram Application...")
        await application.initialize()
        await application.start()
        await application.bot.set_webhook(url=WEBHOOK_URL)
        print("✅ Бот запущен и готов обрабатывать обновления.")

    asyncio.run(start())


if __name__ == "__main__":
    # Telegram Application запускаем в отдельном потоке
    threading.Thread(target=run_bot, daemon=True).start()

    # Flask — основной веб-сервер
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
