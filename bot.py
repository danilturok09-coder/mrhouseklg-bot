# bot.py
import asyncio
import os
import signal
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"
WEBHOOK_URL = "https://mrhouseklg-bot.onrender.com/webhook"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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

async def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("debug", debug))

    # Инициализация
    await application.initialize()
    logger.info("✅ Application initialized")

    # Установка вебхука
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🔗 Webhook установлен на {WEBHOOK_URL}")

    # Запуск сервера
    port = int(os.environ.get("PORT", 8443))
    logger.info(f"🚀 Запуск вебхук-сервера на порту {port}...")

    # Запускаем сервер в фоне
    await application.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=WEBHOOK_URL
    )
    # Сервер будет работать, пока его не остановят

# === Обработка завершения работы ===
def handle_shutdown():
    """Корректное завершение при получении SIGTERM/SIGINT"""
    logger.info("🛑 Получен сигнал завершения. Останавливаем бота...")
    # Мы не можем напрямую вызвать shutdown здесь (нет loop),
    # но asyncio.run() сам обработает исключение и завершит всё.

if __name__ == "__main__":
    # Регистрируем обработчик сигналов
    signal.signal(signal.SIGTERM, lambda s, f: handle_shutdown())
    signal.signal(signal.SIGINT, lambda s, f: handle_shutdown())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен вручную")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise