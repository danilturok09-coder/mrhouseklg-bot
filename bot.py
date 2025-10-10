import asyncio
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from aiohttp import web

# === НАСТРОЙКИ ===
TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://mrhouseklg-bot.onrender.com{WEBHOOK_PATH}"

# === ЛОГИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ХЕНДЛЕРЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Узнать стоимость строительства", callback_data="price"),
         InlineKeyboardButton("Наши проекты", callback_data="projects")],
        [InlineKeyboardButton("Контакты", callback_data="contacts"),
         InlineKeyboardButton("О компании", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👋 Привет! Я бот MR.House. Чем могу помочь?", reply_markup=reply_markup)

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот активен и получает апдейты!")

# === ВЕБХУК-ОБРАБОТЧИК ===
async def webhook_handler(request):
    """Обрабатывает POST-запросы от Telegram"""
    if request.method != "POST":
        return web.Response(status=405)  # Method Not Allowed

    try:
        update_data = await request.json()
        update = Update.de_json(update_data, bot_app.bot)
        await bot_app.process_update(update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Ошибка в вебхуке: {e}")
        return web.Response(status=500)

# === ГЛОБАЛЬНОЕ ПРИЛОЖЕНИЕ ===
bot_app = None

async def main():
    global bot_app
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("debug", debug))

    # Инициализация
    await bot_app.initialize()
    logger.info("✅ Application initialized")

    # Установка вебхука
    await bot_app.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🔗 Webhook установлен на {WEBHOOK_URL}")

    # Запуск aiohttp сервера
    port = int(os.environ.get("PORT", 8443))
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    app.router.add_get("/", lambda r: web.Response(text="✅ MR.House Bot is running!"))

    logger.info(f"🚀 Запуск aiohttp сервера на порту {port}...")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    # Держим сервер включённым
    try:
        await asyncio.Event().wait()  # бесконечное ожидание
    except KeyboardInterrupt:
        pass
    finally:
        await runner.cleanup()
        await bot_app.shutdown()
        logger.info("🛑 Бот остановлен")

if __name__ == "__main__":
    asyncio.run(main())