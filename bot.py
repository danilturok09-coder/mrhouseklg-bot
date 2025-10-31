import os
import time
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
BASE_URL  = os.environ.get("BASE_URL", "").rstrip("/")

# ========= LOGGING =========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")
try:
    import telegram
    logger.info(f"PTB version={getattr(telegram,'__version__','unknown')} | module={telegram.__file__}")
except Exception:
    pass

# ========= GLOBAL LOOP (один на весь процесс) =========
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)

# ========= PTB APP =========
application = Application.builder().token(BOT_TOKEN).build()
_initialized = False

def ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    LOOP.run_until_complete(application.initialize())
    _initialized = True
    logger.info("✅ Telegram Application initialized")

# ========= UI =========
MAIN_MENU = [
    ["📍 Локации домов", "🏗️ Проекты"],
    ["🧮 Расчёт стоимости", "🤖 Задать вопрос ИИ"],
    ["👨‍💼 Связаться с менеджером"]
]

def kb(rows):
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# ---- ЛОКАЦИИ (inline-список + карточки) ----
LOCATIONS = [
    "Шопино", "Чижовка", "Сивково",
    "Некрасово", "Груздово", "ВеснаЛэнд (Черносвитино)",
    "р-н магазина METRO", "г.Рязань", "Еловка", "КП Московский",
]

LOCATIONS_DATA = {
    "Шопино": {
        "photo": f"{BASE_URL}/static/locations/shopino/cover.jpg" if BASE_URL else None,
        "caption": (
            "<b>Шопино</b>\n"
            "Посёлок с развитой инфраструктурой.\n"
            "В презентации: фото, видеообзор, планировки и описание."
        ),
        "presentation": f"{BASE_URL}/static/locations/shopino/presentation.pdf"
        if BASE_URL else "https://example.com/presentation-shopino.pdf",
    },
    # добавь остальные по образцу при необходимости
}

def make_locations_inline() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"loc:{name}")] for name in LOCATIONS]
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

# ---- ПРОЕКТЫ (inline-список + карточки) ----
PROJECTS = ["Весна 90", "Весна 98", "Весна 105", "Весна 112"]

PROJECTS_DATA = {
    "Весна 90": {
        "photo": f"{BASE_URL}/static/projects/vesna90/vesna90.jpg" if BASE_URL else None,
        "caption": (
            "<b>Весна 90</b>\n"
            "Чудесный дом 90 м² с большими окнами в пол, которые наполняют кухню-гостиную солнечным светом.\n\n"
            "• Кухня-гостиная: 24,4 м²\n"
            "• Спальня: 16,9 м²\n"
            "• Кабинет: 14,4 м²\n"
            "• Детская: 14,4 м²\n"
            "• Санузел: 5,9 м²\n"
            "• Прихожая: 12,2 м²\n"
            "• Крыльцо: 3,9 м²"
        ),
        "presentation": f"{BASE_URL}/static/projects/vesna90/vesna90.pdf",
    },
    "Весна 98": {
        "photo": f"{BASE_URL}/static/projects/vesna98/vesna98.jpg" if BASE_URL else None,
        "caption": (
            "<b>Весна 98</b>\n"
            "Удобный и комфортный проект 98 м² с потолком 4,5 м и панорамным остеклением в обеденной зоне.\n\n"
            "• Кухня-гостиная: 27,3 м²\n"
            "• Спальня: 17,1 м²\n"
            "• Детская: 14 м²\n"
            "• Кабинет: 14 м²\n"
            "• Санузел: 6 м²\n"
            "• Санузел гостевой: 2,5 м²\n"
            "• Прихожая: 13,3 м²\n"
            "• Крыльцо: 3,5 м²"
        ),
        "presentation": f"{BASE_URL}/static/projects/vesna98/vesna98.pdf",
    },
    "Весна 105": {
        "photo": f"{BASE_URL}/static/projects/vesna105/vesna105.jpg" if BASE_URL else None,
        "caption": (
            "<b>Весна 105</b>\n"
            "Увеличенная версия Весна-98 — ещё больше света и пространства.\n\n"
            "• Кухня-гостиная: 27,5 м²\n"
            "• Спальня: 18,6 м²\n"
            "• Детская: 16 м²\n"
            "• Кабинет: 16 м²\n"
            "• Санузел: 5,9 м²\n"
            "• Санузел гостевой: 2,7 м²\n"
            "• Прихожая: 14,1 м²\n"
            "• Крыльцо: 3,5 м²"
        ),
        "presentation": f"{BASE_URL}/static/projects/vesna105/vesna105.pdf",
    },
    "Весна 112": {
        "photo": f"{BASE_URL}/static/projects/vesna112/vesna112.jpg" if BASE_URL else None,
        "caption": (
            "<b>Весна 112</b>\n"
            "Те же большие окна в пол, что нравятся в Весна-90, плюс 3 спальни и 2 санузла.\n\n"
            "• Кухня-гостиная: 28,9 м²\n"
            "• Детская: 14,9 м²\n"
            "• Кабинет: 14,9 м²\n"
            "• Спальня: 19,2 м²\n"
            "• Санузел: 5,7 м²\n"
            "• Санузел 2: 1,6 м²\n"
            "• Гардероб: 6,7 м²\n"
            "• Прихожая: 15,2 м²\n"
            "• Крыльцо: 4,9 м²"
        ),
        "presentation": f"{BASE_URL}/static/projects/vesna112/vesna112.pdf",
    },
}

def make_projects_inline() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"🏡 {name}", callback_data=f"proj:{name}")] for name in PROJECTS]
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

# ========= HELPERS =========
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("❗ Unhandled error", exc_info=context.error)

async def send_welcome_with_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие + баннер + главное меню (антидубль 10с)."""
    now = time.time()
    last = context.user_data.get("_last_welcome_ts", 0)
    if now - last < 10:
        return
    context.user_data["_last_welcome_ts"] = now

    banner_url = f"{BASE_URL}/static/welcome.jpg" if BASE_URL else None
    caption = (
        "👋 Привет! Я бот <b>MR.House</b>.\n"
        "Помогу выбрать локацию и проект, посчитать стоимость и связать с менеджером."
    )

    chat_id = update.effective_chat.id
    sent_banner = False
    if banner_url:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=banner_url, caption=caption, parse_mode="HTML")
            sent_banner = True
        except Exception as e:
            logger.warning(f"Не смог отправить фото-баннер: {e}")

    if not sent_banner:
        await context.bot.send_message(chat_id=chat_id,
                                       text="👋 Привет! Я бот MR.House. Готов помочь.",
                                       parse_mode="HTML")
    await context.bot.send_message(chat_id=chat_id, text="Выберите раздел 👇", reply_markup=kb(MAIN_MENU))
    context.user_data["state"] = "MAIN"

# ---- Локации: список (inline) и карточка ----
async def show_locations_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "LOC_LIST"
    text = "-----Вы в разделе локации домов-----\nВыберите локацию:"
    markup = make_locations_inline()

    if update.message:
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Локации:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup)

async def send_location_card(chat, location_name: str, context: ContextTypes.DEFAULT_TYPE):
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
            await context.bot.send_photo(chat_id=chat.id, photo=data["photo"],
                                         caption=data["caption"], parse_mode="HTML", reply_markup=markup)
        else:
            raise RuntimeError("no photo")
    except Exception:
        await context.bot.send_message(chat_id=chat.id, text=data["caption"], parse_mode="HTML", reply_markup=markup)

# ---- Проекты: список (inline) и карточка ----
async def show_projects_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "PROJ_LIST"
    text = "-----Вы в разделе проекты-----\nВыберите проект:"
    markup = make_projects_inline()

    if update.message:
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Проекты:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup)

# >>>>>>> ОБНОВЛЁННАЯ ФУНКЦИЯ <<<<<<<<
async def send_project_card(chat, project_name: str, context: ContextTypes.DEFAULT_TYPE):
    data = PROJECTS_DATA.get(project_name)
    if not data:
        await context.bot.send_message(chat_id=chat.id, text=f"Скоро добавим карточку для «{project_name}».")
        return

    # cache-buster: заставляем Telegram заново скачать картинку
    photo_url = None
    if data.get("photo"):
        ts = int(time.time())
        sep = "&" if "?" in data["photo"] else "?"
        photo_url = f'{data["photo"]}{sep}v={ts}'

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Смотреть презентацию", url=data["presentation"])],
        [InlineKeyboardButton("📋 К списку проектов", callback_data="back_to_projects")],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])

    # 1) Пытаемся как фото
    if photo_url:
        try:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=photo_url,
                caption=data["caption"],
                parse_mode="HTML",
                reply_markup=markup
            )
            return
        except Exception as e:
            logger.warning(f"send_photo failed for {project_name}: {e}")

    # 2) Резерв: отправим как документ
    if data.get("photo"):
        try:
            await context.bot.send_document(
                chat_id=chat.id,
                document=photo_url or data["photo"],
                caption=data["caption"],
                parse_mode="HTML",
                reply_markup=markup
            )
            return
        except Exception as e:
            logger.warning(f"send_document failed for {project_name}: {e}")

    # 3) Последний резерв: текст + кнопка на изображение
    fallback_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Открыть изображение", url=data.get("photo") or "")],
        [InlineKeyboardButton("📘 Смотреть презентацию", url=data["presentation"])],
        [InlineKeyboardButton("📋 К списку проектов", callback_data="back_to_projects")],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])
    await context.bot.send_message(chat_id=chat.id, text=data["caption"], parse_mode="HTML", reply_markup=fallback_markup)

# ========= COMMANDS & ROUTING =========
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

    if text == "📍 Локации домов":
        return await show_locations_inline(update, context)

    if text == "🏗️ Проекты":
        return await show_projects_inline(update, context)

    if state == "MAIN":
        mapping = {
            "🧮 Расчёт стоимости": "Введите желаемую площадь и бюджет (пока заглушка).",
            "🤖 Задать вопрос ИИ": "Напишите вопрос, я постараюсь помочь (пока заглушка).",
            "👨‍💼 Связаться с менеджером": "Наш менеджер свяжется с вами: +7 (910) 864-07-37",
        }
        if text in mapping:
            return await update.message.reply_text(mapping[text], reply_markup=kb(MAIN_MENU))
        return await update.message.reply_text("Выберите кнопку ниже 👇", reply_markup=kb(MAIN_MENU))

    # Для списков LOC/PROJ клики идут через inline-кнопки — тут текст не обрабатываем.
    return

async def handle_callback(query_update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = query_update.callback_query
    data = query.data or ""
    await query.answer()

    # Локации
    if data.startswith("loc:"):
        loc = data[4:]
        try:
            await query.edit_message_text(f"Локация {loc}:")
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
        return await send_location_card(query.message.chat, loc, context)

    if data == "back_to_locs":
        try:
            await query.edit_message_text("Выберите локацию:")
            await query.edit_message_reply_markup(reply_markup=make_locations_inline())
        except Exception:
            await context.bot.send_message(query.message.chat_id, "Выберите локацию:", reply_markup=make_locations_inline())
        context.user_data["state"] = "LOC_LIST"
        return

    # Проекты
    if data.startswith("proj:"):
        proj = data[5:]
        try:
            await query.edit_message_text(f"Проект {proj}:")
        except Exception:
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
        return await send_project_card(query.message.chat, proj, context)

    if data == "back_to_projects":
        try:
            await query.edit_message_text("Выберите проект:")
            await query.edit_message_reply_markup(reply_markup=make_projects_inline())
        except Exception:
            await context.bot.send_message(query.message.chat_id, "Выберите проект:", reply_markup=make_projects_inline())
        context.user_data["state"] = "PROJ_LIST"
        return

    # В меню
    if data == "back_to_menu":
        context.user_data.clear()
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return await send_welcome_with_photo(query_update, context)

# Регистрация
application.add_handler(CommandHandler(["start", "star"], cmd_start))
application.add_handler(CommandHandler("menu", cmd_menu))
application.add_handler(CommandHandler("ping", cmd_ping))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_error_handler(error_handler)

# ========= FLASK =========
web_app = Flask(__name__)

@web_app.get("/")
def index():
    return jsonify({"ok": True, "service": "MR.House bot"})

@web_app.get("/set_webhook")
def set_webhook_route():
    if not BASE_URL:
        return "BASE_URL не задан", 400
    ensure_initialized()
    url = f"{BASE_URL}/webhook"
    try:
        LOOP.run_until_complete(application.bot.set_webhook(url))
        return f"Webhook установлен на {url}"
    except Exception as e:
        logger.exception("Ошибка при установке вебхука")
        return f"Ошибка при установке вебхука: {e}", 500

@web_app.post("/webhook")
def webhook():
    ensure_initialized()
    data = request.get_json(force=True, silent=False)
    update = Update.de_json(data, application.bot)
    try:
        LOOP.run_until_complete(application.process_update(update))
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Ошибка обработки апдейта")
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    if BASE_URL:
        ensure_initialized()
        LOOP.run_until_complete(application.bot.set_webhook(f"{BASE_URL}/webhook"))
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)