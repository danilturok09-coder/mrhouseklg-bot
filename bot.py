import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# === Переменные окружения ===
BOT_TOKEN = os.environ["BOT_TOKEN"]                          # токен бота от @BotFather
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")        # https://mrhouseklg-bot.onrender.com

# === Логи (и диагностика версии PTB) ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
try:
    import telegram
    logger.info(f"PTB version={getattr(telegram, '__version__', 'unknown')} | module={telegram.__file__}")
except Exception:
    pass

# === Telegram Application (PTB v20, async) ===
application = Application.builder().token(BOT_TOKEN).build()
_initialized = False

def ensure_initialized() -> None:
    """Инициализировать PTB один раз (синхронно через отдельный event loop)."""
    global _initialized
    if _initialized:
        return
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.initialize())
        _initialized = True
        logger.info("✅ Telegram Application initialized")
    finally:
        loop.close()
        asyncio.set_event_loop(None)

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("Узнать стоимость строительства", callback_data="price"),
            InlineKeyboardButton("Наши проекты", callback_data="projects"),
        ],
        [
            InlineKeyboardButton("Контакты", callback_data="contacts"),
            InlineKeyboardButton("О компании", callback_data="about"),
        ],
    ]
    await update.message.reply_text(
        "👋 Привет! Я бот MR.House. Чем могу помочь?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Бот работает ✅")

# Регистрация команд и опечатки /star
application.add_handler(CommandHandler(["start", "star"], start))
application.add_handler(CommandHandler("ping", ping))
application.add_handler(MessageHandler(filters.Regex(r"^/?star$"), start))

# === Flask (все эндпоинты синхронные) ===
web_app = Flask(__name__)

@web_app.get("/")
def index():
    return jsonify({"ok": True, "service": "MR.House bot"})

@web_app.get("/set_webhook")
def set_webhook_route():
    """Ставит вебхук БЕЗ секретов."""
    if not BASE_URL:
        return "BASE_URL не задан", 400
    url = f"{BASE_URL}/webhook"
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.bot.set_webhook(url))
        return f"Webhook установлен на {url}"
    except Exception as e:
        logger.exception("Ошибка при установке вебхука")
        return f"Ошибка при установке вебхука: {e}", 500
    finally:
        loop.close()
        asyncio.set_event_loop(None)

@web_app.post("/webhook")
def webhook():
    """Приём апдейтов от Telegram. Без проверок секрета."""
    ensure_initialized()
    data = request.get_json(force=True, silent=False)
    update = Update.de_json(data, application.bot)

    # Обрабатываем апдейт синхронно через отдельный loop,
    # чтобы избежать конфликтов с уже закрытой петлёй.
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.process_update(update))
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Ошибка обработки апдейта")
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        loop.close()
        asyncio.set_event_loop(None)

# Локальный запуск (на Render не используется)
if __name__ == "__main__":
    if BASE_URL:
        url = f"{BASE_URL}/webhook"
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.bot.set_webhook(url))
        loop.close()
        asyncio.set_event_loop(None)

    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)