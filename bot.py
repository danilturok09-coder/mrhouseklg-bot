import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ========= ENV =========
BOT_TOKEN = os.environ["BOT_TOKEN"]
BASE_URL  = os.environ.get("BASE_URL", "").rstrip("/")  # например: https://mrhouseklg-bot.onrender.com

# ========= LOGGING =========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
try:
    import telegram
    logger.info(f"PTB version={getattr(telegram,'__version__','unknown')} | module={telegram.__file__}")
except Exception:
    pass

# ========= PTB APP =========
application = Application.builder().token(BOT_TOKEN).build()
_initialized = False

def ensure_initialized() -> None:
    """Инициализируем PTB один раз (важно для вебхуков на Flask)."""
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

# ========= UI DATA =========
MAIN_MENU = [
    ["📍 Локации домов", "🏗️ Проекты"],
    ["🧮 Расчёт стоимости", "🤖 Задать вопрос ИИ"],
    ["👨‍💼 Связаться с менеджером"]
]

LOCATIONS = [
    "Шопино", "Чижовка", "Сивково",
    "Некрасово", "Груздово", "ВеснаЛэнд (Черносвитино)",
    "р-н магазина METRO", "г.Рязань", "Еловка", "КП Московский",
]

def kb(rows):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False, selective=True)

# Карточки локаций: фото + описание + ссылка на презентацию
LOCATIONS_DATA = {
    "Шопино": {
        "photo": f"{BASE_URL}/static/locations/shopino/cover.jpg" if BASE_URL else None,
        "caption": (
            "<b>Шопино</b>\n"
            "Посёлок с развитой инфраструктурой.\n"
            "В презентации: фото, видеообзор, планировки и описание."
        ),
        "presentation": f"{BASE_URL}/static/locations/shopino/presentation.pdf" if BASE_URL else "https://example.com/presentation-shopino.pdf",
    },
    # Добавляй остальные локации по образцу:
    # "Чижовка": { "photo": f"{BASE_URL}/static/locations/chizhovka/cover.jpg", ... },
}

# ========= HELPERS =========
async def send_welcome_with_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие с баннером и главной клавиатурой."""
    banner_url = f"{BASE_URL}/static/welcome.jpg" if BASE_URL else None
    caption = (
        "👋 Привет! Я бот <b>MR.House</b>.\n"
        "Помогу выбрать локацию и проект, посчитать стоимость и связать с менеджером."
    )

    chat_id = update.effective_chat.id
    if banner_url:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=banner_url, caption=caption, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не смог отправить фото-баннер: {e}")
            await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")

    await context.bot.send_message(chat_id=chat_id, text="Выберите раздел 👇", reply_markup=kb(MAIN_MENU))
    context.user_data["state"] = "MAIN"

def make_locations_inline() -> InlineKeyboardMarkup:
    """Строит inline-клавиатуру со списком локаций."""
    rows = [[InlineKeyboardButton(name, callback_data=f"loc:{name}")] for name in LOCATIONS]
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

async def show_locations_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список локаций как inline-кнопки (полупрозрачные под сообщением)."""
    context.user_data["state"] = "LOC_LIST"
    text = "-----Вы в разделе локации домов-----\nВыберите локацию:"
    markup = make_locations_inline()

    # Уберём нижнюю reply-клавиатуру, чтобы не дублировалась с inline
    if update.message:
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Локации:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup)

async def send_location_card(chat, location_name: str, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет фото + подпись + кнопки."""
    data = LOCATIONS_DATA.get(location_name)
    if not data:
        await context.bot.send_message(chat_id=chat.id, text=f"Скоро добавим карточку для «{location_name}».")
        return

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Смотреть презентацию", url=data["presentation"])],
        [InlineKeyboardButton("📋 К списку локаций", callback_data="back_to_locs")],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])

    try:
        if data.get("photo"):
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=data["photo"],
                caption=data["caption"],
                parse_mode="HTML",
                reply_markup=markup
            )
        else:
            raise RuntimeError("no photo url")
    except Exception:
        await context.bot.send_message(
            chat_id=chat.id,
            text=data["caption"],
            parse_mode="HTML",
            reply_markup=markup
        )

# ========= HANDLERS =========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await send_welcome_with_photo(update, context)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "MAIN"
    await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Бот работает ✅")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    state = context.user_data.get("state", "MAIN")

    # Глобальная кнопка из главного меню
    if text == "📍 Локации домов":
        return await show_locations_inline(update, context)

    if state == "MAIN":
        if text == "🏗️ Проекты":
            return await update.message.reply_text("Каталог проектов скоро добавим 🔧", reply_markup=kb(MAIN_MENU))
        if text == "🧮 Расчёт стоимости":
            return await update.message.reply_text("Введите желаемую площадь и бюджет (пока заглушка).", reply_markup=kb(MAIN_MENU))
        if text == "🤖 Задать вопрос ИИ":
            return await update.message.reply_text("Напишите вопрос, я постараюсь помочь (пока заглушка).", reply_markup=kb(MAIN_MENU))
        if text == "👨‍💼 Связаться с менеджером":
            return await update.message.reply_text("Наш менеджер свяжется с вами: +7 (910) 864-07-37", reply_markup=kb(MAIN_MENU))
        return await update.message.reply_text("Выберите кнопку ниже 👇", reply_markup=kb(MAIN_MENU))

    # Для LOC_LIST теперь клики идут через inline-кнопки — текст тут не обрабатываем.
    return

async def handle_callback(query_update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инлайн-кнопки (список локаций, карточки и возвраты)."""
    query = query_update.callback_query
    data = query.data or ""
    await query.answer()

    # клик по локации
    if data.startswith("loc:"):
        loc = data[4:]
        # скрываем сообщение со списком
        try:
            await query.edit_message_text(f"Локация {loc}:")
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
        # отправляем карточку
        return await send_location_card(query.message.chat, loc, context)

    # вернуться к списку локаций
    if data == "back_to_locs":
        try:
            await query.edit_message_text("Выберите локацию:")
            await query.edit_message_reply_markup(reply_markup=make_locations_inline())
        except Exception:
            await context.bot.send_message(query.message.chat_id, "Выберите локацию:", reply_markup=make_locations_inline())
        context.user_data["state"] = "LOC_LIST"
        return

    # вернуться в меню
    if data == "back_to_menu":
        context.user_data.clear()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await send_welcome_with_photo(query_update, context)

# Регистрация хэндлеров
application.add_handler(CommandHandler(["start", "star"], cmd_start))
application.add_handler(CommandHandler("menu", cmd_menu))
application.add_handler(CommandHandler("ping", cmd_ping))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# ========= FLASK (webhook) =========
web_app = Flask(__name__)

@web_app.get("/")
def index():
    return jsonify({"ok": True, "service": "MR.House bot"})

@web_app.get("/set_webhook")
def set_webhook_route():
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
    ensure_initialized()
    data = request.get_json(force=True, silent=False)
    update = Update.de_json(data, application.bot)

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

if __name__ == "__main__":
    # локальный запуск (или форс-установка вебхука при старте)
    if BASE_URL:
        url = f"{BASE_URL}/webhook"
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.bot.set_webhook(url))
        loop.close()
        asyncio.set_event_loop(None)
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)