import asyncio
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# === 🔧 НАСТРОЙКИ ===
TOKEN = "8497588100:AAFYuucn9j8teDlWZ6htv_N7IbaXLp1TQB8"
WEBHOOK_URL = "https://mrhouseklg-bot.onrender.com/webhook"

# === ЛОГИ ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === ОБРАБОТЧИКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Узнать стоимость строительства", callback_data="price"),
         InlineKeyboardButton("Наши проекты", callback_data="projects")],
        [InlineKeyboardButton("Контакты", callback_data="contacts"),
         InlineKeyboardButton("О компании", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Привет! Я бот MR.House. Чем могу помочь?",
        reply_markup=reply_markup
    )

async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот активен и получает апдейты!")

# === ОСНОВНАЯ ФУНКЦИЯ ===
async def main():
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()

    # Регистрируем хендлеры
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("debug", debug))

    # Инициализация (один раз!)
    await application.initialize()
    logger.info("✅ Application initialized")

    # Устанавливаем вебхук
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🔗 Webhook установлен на {WEBHOOK_URL}")

    # Запускаем вебхук-сервер
    port = int(os.environ.get("PORT", 8443))
    logger.info(f"🚀 Запуск вебхук-сервера на порту {port}...")
    
    await application.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=WEBHOOK_URL,
        secret_token=None  # можно добавить для безопасности
    )

# === ТОЧКА ВХОДА ===
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен вручную")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise