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

# ===== ENV =====
BOT_TOKEN = os.environ["BOT_TOKEN"]
BASE_URL  = os.environ.get("BASE_URL", "").rstrip("/")  # https://mrhouseklg-bot.onrender.com

# ===== LOGS =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
try:
    import telegram
    logger.info(f"PTB version={getattr(telegram,'__version__','unknown')} | module={telegram.__file__}")
except Exception:
    pass

# ===== PTB Application =====
application = Application.builder().token(BOT_TOKEN).build()
_initialized = False

def ensure_initialized() -> None:
    """Инициализируем PTB один раз, синхронно через отдельный event loop."""
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

# ===== UI DATA =====
MAIN_MENU = [
    ["📍 Локации домов", "🏗️ Проекты"],
    ["🧮 Расчёт стоимости", "🤖 Задать вопрос ИИ"],
    ["👨‍💼 Связаться с менеджером"]
]

LOCATIONS = [
    "Шопино", "Чижовка", "Сивково",
    "Некрасово", "Груздово", "ВеснаЛэнд (Черносвитино)",
    "р-н магазина METRO", "г.Рязань", "Еловка", "КП Московский",
    "↩️ Назад", "🏠 Вернуться в меню",
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
    # Пример заготовок для следующих (заменишь пути/тексты и добавишь файлы):
    # "Чижовка": {...}, "Сивково": {...}, ...
}

# ===== HELPERS =====
async def send_welcome_with_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие с баннером и главной клавиатурой."""
    banner_url = f"{BASE_URL}/static/welcome.jpg" if BASE_URL else None
    caption = (
        "👋 Привет! Я бот <b>MR.House</b>.\n"
        "Помогу выбрать локацию и проект, посчитать стоимость и связать с менеджером."
    )
    if update.message:
        chat_id = update.message.chat_id
    else:
        chat_id = update.effective_chat.id

    if banner_url:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=banner_url, caption=caption, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не смог отправить фото-баннер: {e}")
            await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")
    else:
        await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")

    if update.message:
        await update.message.reply_text("Выберите раздел 👇", reply_markup=kb(MAIN_MENU))
    else:
        await context.bot.send_message(chat_id=chat_id, text="Выберите раздел 👇", reply_markup=kb(MAIN_MENU))
    context.user_data["state"] = "MAIN"

async def show_locations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [[n] for n in LOCATIONS]
    await update.message.reply_text(
        "-----Вы в разделе локации домов-----\nВыберите локацию:",
        reply_markup=kb(rows)
    )

def inline_back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")]
    ])

async def send_location_card(chat, location_name: str, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет фото + подпись + кнопку 'Смотреть презентацию'."""
    data = LOCATIONS_DATA.get(location_name)
    if not data:
        await context.bot.send_message(chat_id=chat.id, text=f"Скоро добавим карточку для «{location_name}».")
        return

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Смотреть презентацию", url=data["presentation"])],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")]
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

# ===== HANDLERS =====
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

    # Глобальные кнопки возврата
    if text == "🏠 Вернуться в меню":
        context.user_data["state"] = "MAIN"
        return await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))

    if text == "↩️ Назад":
        prev = context.user_data.get("prev_state", "MAIN")
        if prev == "LOC_LIST":
            context.user_data["state"] = "LOC_LIST"
            return await show_locations(update, context)
        context.user_data["state"] = "MAIN"
        return await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))

    # === MAIN ===
    if state == "MAIN":
        if text == "📍 Локации домов":
            context.user_data["state"] = "LOC_LIST"
            return await show_locations(update, context)

        if text == "🏗️ Проекты":
            return await update.message.reply_text("Каталог проектов скоро добавим 🔧", reply_markup=kb(MAIN_MENU))

        if text == "🧮 Расчёт стоимости":
            return await update.message.reply_text("Введите желаемую площадь и бюджет (пока заглушка).", reply_markup=kb(MAIN_MENU))

        if text == "🤖 Задать вопрос ИИ":
            return await update.message.reply_text("Напишите вопрос, я постараюсь помочь (пока заглушка).", reply_markup=kb(MAIN_MENU))

        if text == "👨‍💼 Связаться с менеджером":
            return await update.message.reply_text("Наш менеджер свяжется с вами: +7 (910) 864-07-37", reply_markup=kb(MAIN_MENU))

        return await update.message.reply_text("Выберите кнопку ниже 👇", reply_markup=kb(MAIN_MENU))

    # === LOCATIONS LIST ===
    if state == "LOC_LIST":
        if text in LOCATIONS and text not in ["↩️ Назад", "🏠 Вернуться в меню"]:
            # Оставляемся в режиме списка локаций (можно открывать другие карточки подряд)
            context.user_data["prev_state"] = "LOC_LIST"
            await send_location_card(update.effective_chat, text, context)
            # Под сообщение добавим короткую подсказку с возвратом
            return await update.message.reply_text(
                "Выберите другую локацию или вернитесь в меню:",
                reply_markup=kb([["↩️ Назад"], ["🏠 Вернуться в меню"]])
            )
        else:
            return await show_locations(update, context)

    # Если что-то ещё — вернём в главное меню
    context.user_data["state"] = "MAIN"
    return await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))

async def handle_callback(query_update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инлайн-кнопки (например, 'Вернуться в меню')."""
    query = query_update.callback_query
    data = query.data or ""
    await query.answer()

    if data == "back_to_menu":
        context.user_data.clear()
        # обновим сообщение сверху и отправим меню
        await query.edit_message_reply_markup(reply_markup=None)
        await send_welcome_with_photo(query_update, context)
        return

# Регистрация
application.add_handler(CommandHandler(["start", "star"], cmd_start))
application.add_handler(CommandHandler("menu", cmd_menu))
application.add_handler(CommandHandler("ping", cmd_ping))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# ===== Flask (вебхуки) =====
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
    if BASE_URL:
        url = f"{BASE_URL}/webhook"
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.bot.set_webhook(url))
        loop.close()
        asyncio.set_event_loop(None)
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)