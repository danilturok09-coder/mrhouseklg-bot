import os
import time
import logging
import asyncio
from urllib.parse import unquote

import httpx
from flask import Flask, jsonify, request as flask_request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from telegram.request import HTTPXRequest

# ========= ENV =========
BOT_TOKEN = os.environ["BOT_TOKEN"]
BASE_URL  = os.environ.get("BASE_URL", "").rstrip("/")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

# Принудительное обновление кэша Telegram (увидел новые картинки — увеличь версию)
CACHE_VER = "2025-11-05-3"

# ========= LOGGING =========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")
try:
    import telegram
    logger.info(f"PTB version={getattr(telegram,'__version__','unknown')} | module={telegram.__file__}")
except Exception:
    pass

# ========= GLOBAL LOOP =========
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)

# ========= PTB APP (увеличенные таймауты) =========
tg_request = HTTPXRequest(
    connect_timeout=20.0,
    read_timeout=60.0,
    write_timeout=60.0,
    pool_timeout=20.0
)
application = Application.builder().token(BOT_TOKEN).request(tg_request).build()
_initialized = False

def ensure_initialized() -> None:
    """Инициализируем PTB-Application ровно один раз."""
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

# ========= ЛОКАЦИИ =========
LOCATIONS = [
    "Шопино", "Чижовка", "р-н магазина METRO", "КП Южный",
    "Еловка", "ВеснаЛэнд (Черносвитино)", "Сивково",
    "Некрасово", "Груздово", "КП Московский"
]

LOC_SLUG = {
    "Шопино": "shopino",
    "Чижовка": "chizhovka",
    "р-н магазина METRO": "metro",
    "КП Южный": "kp_yuzhniy",
    "Еловка": "elovka",
    "ВеснаЛэнд (Черносвитино)": "vesnaland",
    "Сивково": "sivkovo",
    "Некрасово": "nekrasovo",
    "Груздово": "gruzdovo",
    "КП Московский": "kp_moskovskiy",
}

def _loc_data(name: str, body: str, *, has_video: bool = False):
    slug = LOC_SLUG[name]
    photo = f"{BASE_URL}/static/locations/{slug}/{slug}.jpg?v={CACHE_VER}" if BASE_URL else None
    pres = f"{BASE_URL}/static/locations/{slug}/{slug}.pdf" if BASE_URL else None
    video = f"{BASE_URL}/static/locations/{slug}/video.mp4" if (BASE_URL and has_video) else None
    caption = f"<b>{name}</b>\n{body}"
    return {"photo": photo, "presentation": pres, "video": video, "caption": caption}

# === твои описания ===
LOCATIONS_DATA = {
    "Шопино": _loc_data(
        "Шопино",
        "Современный посёлок в шаге от города: школы и детские сады в 5–7 минутах, "
        "крупные ТЦ — около 10 минут на авто. До центра 15–20 минут."
    ),
    "Чижовка": _loc_data(
        "Чижовка",
        "Инфраструктура: школы и детсады в пешей доступности, ТЦ в 8–10 минутах, "
        "до центра 15–20 минут."
    ),
    "р-н магазина METRO": _loc_data(
        "р-н магазина METRO",
        "Район рядом с гипермаркетом METRO: магазины, услуги, школы 5–10 минут, "
        "до центра 15–20 минут."
    ),
    "КП Южный": _loc_data(
        "КП Южный",
        "Посёлок окружён лесом, 23 участка. Школы 10–15 минут, ТЦ 10 минут. До центра 10–15 минут.",
        has_video=True
    ),
    "Еловка": _loc_data(
        "Еловка",
        "Спокойный посёлок, пригородная инфраструктура. До центра 25–30 минут."
    ),
    "ВеснаЛэнд (Черносвитино)": _loc_data(
        "ВеснаЛэнд (Черносвитино)",
        "Новая зона с упором на семейный комфорт. До центра 10–15 минут."
    ),
    "Сивково": _loc_data(
        "Сивково",
        "Пригород: тишина, воздух, пространство. До центра ~30 минут."
    ),
    "Некрасово": _loc_data(
        "Некрасово",
        "Баланс города и уединения: центр 15–20 минут, школы 10–15 минут."
    ),
    "Груздово": _loc_data(
        "Груздово",
        "До центра 30 минут, спокойная среда, подойдёт семьям."
    ),
    "КП Московский": _loc_data(
        "КП Московский",
        "Школы и сады 10–15 минут. До центра 20–25 минут."
    ),
}

def make_locations_inline():
    rows = [[InlineKeyboardButton(name, callback_data=f"loc:{name}")] for name in LOCATIONS]
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

# ========= ПРОЕКТЫ =========
PROJECTS = ["Весна 90", "Весна 98", "Весна 105", "Весна 112"]

PROJECTS_DATA = {
    name: {
        "photo": f"{BASE_URL}/static/projects/{LOC_SLUG.get(name,'x')}/{LOC_SLUG.get(name,'x')}.jpg"
        if BASE_URL else None,
        "presentation": f"{BASE_URL}/static/projects/{LOC_SLUG.get(name,'x')}/{LOC_SLUG.get(name,'x')}.pdf",
        "caption": name
    }
    for name in PROJECTS
}

def make_projects_inline():
    rows = [[InlineKeyboardButton(f"🏡 {name}", callback_data=f"proj:{name}")] for name in PROJECTS]
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

# ============================================================
#              ИИ-СТРОИТЕЛЬ — ПРОКАЧАННАЯ ВЕРСИЯ
# ============================================================

BUILDER_SYSTEM_PROMPT = """
Ты — профессиональный строительный инженер-консультант с опытом 25 лет,
эксперт по фундаментам, инженерным системам и частному домостроению в России.

Твой стиль:
- спокойный, уверенный, экспертный;
- объясняешь простым языком, но очень умно;
- не критикуешь, а корректно направляешь;
- даёшь точные рекомендации;
- умеешь помнить контекст и учитывать предыдущие сообщения.

Упор на фундамент:
- свайно-ростверковый (ЖБ) — твоя ключевая область экспертизы;
- знаешь когда можно, когда нельзя, какие ошибки типичные;
- объясняешь работу ростверка, армирование, пучинистые грунты, песчаные основания.

Структура ответа (обязательная):
1) Краткий вердикт (2–4 предложения)
2) Технический разбор по пунктам:
   - фундамент
   - несущие стены / материалы
   - крыша
   - теплотехника
   - инженерка
3) На что обратить внимание — bullets
4) Что уточнить у пользователя — bullets

Очень важно:  
Если данных мало — ты не придумываешь, а говоришь, что не хватает информации, и какие данные нужны.
"""

async def ask_builder_ai(user_message: str, history: list) -> str:
    """Вызов Groq (улучшенная версия)."""
    if not GROQ_API_KEY:
        return "ИИ-консультант временно недоступен. Попробуйте позже."

    messages = [{"role": "system", "content": BUILDER_SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-14:])
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": messages,
        "temperature": 0.35,
        "max_tokens": 1100,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if resp.status_code != 200:
            logger.warning(f"Groq error {resp.status_code}: {resp.text}")
            return "Извините, ИИ сейчас перегружен. Попробуйте чуть позже."

        return resp.json()["choices"][0]["message"]["content"]

    except Exception as e:
        logger.warning(f"Groq API exception: {e}")
        return "Сервис ИИ временно недоступен."
        
        # ========= HELPERS =========
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("❗ Unhandled error", exc_info=context.error)

async def send_welcome_with_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    last = context.user_data.get("_last_welcome_ts", 0)
    if now - last < 10:
        return
    context.user_data["_last_welcome_ts"] = now

    banner_url = f"{BASE_URL}/static/welcome.jpg" if BASE_URL else None
    caption = (
        "👋 Привет! Я бот <b>MR.House</b>.\n"
        "Помогу выбрать локацию и проект, посчитать стоимость и задать вопросы строителю."
    )

    chat_id = update.effective_chat.id
    sent = False

    if banner_url:
        try:
            await context.bot.send_photo(chat_id, banner_url, caption=caption, parse_mode="HTML")
            sent = True
        except Exception as e:
            logger.warning(f"Banner failed: {e}")

    if not sent:
        await context.bot.send_message(chat_id, "👋 Привет! Я бот MR.House.", parse_mode="HTML")

    await context.bot.send_message(chat_id, "Выберите раздел 👇", reply_markup=kb(MAIN_MENU))
    context.user_data["state"] = "MAIN"

# ========= ЛОКАЦИИ UI =========
async def show_locations_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "LOC_LIST"
    markup = make_locations_inline()

    if update.message:
        await update.message.reply_text("-----Вы в разделе локации домов-----", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Локации:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, "Локации:", reply_markup=markup)

async def send_location_card(chat, loc_name: str, context: ContextTypes.DEFAULT_TYPE):
    data = LOCATIONS_DATA.get(loc_name)
    if not data:
        await context.bot.send_message(chat.id, f"Скоро добавим карточку {loc_name}")
        return

    photo_url = data["photo"]
    presentation = data["presentation"]
    video = data["video"]

    buttons = []
    if presentation:
        buttons.append([InlineKeyboardButton("📘 Смотреть презентацию", url=presentation)])
    if video:
        buttons.append([InlineKeyboardButton("🎬 Смотреть видео", url=video)])

    buttons.append([InlineKeyboardButton("📋 К списку локаций", callback_data="back_to_locs")])
    buttons.append([InlineKeyboardButton("🏠 В меню", callback_data="back_to_menu")])

    markup = InlineKeyboardMarkup(buttons)

    sent = False
    if photo_url:
        try:
            await context.bot.send_photo(
                chat.id,
                photo_url,
                caption=data["caption"],
                parse_mode="HTML",
                reply_markup=markup
            )
            sent = True
        except Exception as e:
            logger.warning(f"Location photo error: {e}")

    if not sent:
        await context.bot.send_message(chat.id, data["caption"], parse_mode="HTML", reply_markup=markup)

# ========= ПРОЕКТЫ UI =========
async def show_projects_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "PROJ_LIST"
    markup = make_projects_inline()

    if update.message:
        await update.message.reply_text("-----Вы в разделе проекты-----", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Проекты:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, "Проекты:", reply_markup=markup)

async def send_project_card(chat, proj_name: str, context: ContextTypes.DEFAULT_TYPE):
    data = PROJECTS_DATA.get(proj_name)
    if not data:
        await context.bot.send_message(chat.id, f"Скоро добавим проект {proj_name}")
        return

    photo_url = data["photo"]
    pres = data["presentation"]

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Смотреть презентацию", url=pres)],
        [InlineKeyboardButton("📋 К списку проектов", callback_data="back_to_projects")],
        [InlineKeyboardButton("🏠 В меню", callback_data="back_to_menu")],
    ])

    if photo_url:
        try:
            await context.bot.send_photo(
                chat.id, photo_url,
                caption=data["caption"], parse_mode="HTML", reply_markup=markup
            )
            return
        except:
            pass

    await context.bot.send_message(chat.id, data["caption"], parse_mode="HTML", reply_markup=markup)

# ========= ТЕКСТОВЫЕ КОМАНДЫ =========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await send_welcome_with_photo(update, context)

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "MAIN"
    await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

# ========= ОБРАБОТКА ТЕКСТА =========
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    state = context.user_data.get("state", "MAIN")
    chat_id = update.effective_chat.id

    # Вход в ИИ
    if text == "🤖 Задать вопрос ИИ":
        context.user_data["state"] = "ASK_AI"
        await update.message.reply_text(
            "🧱 Задайте вопрос по фундаменту, материалам, инженерке, проектированию.",
            reply_markup=kb(MAIN_MENU)
        )
        return

    # Вопрос к ИИ
    if state == "ASK_AI" and text not in MAIN_MENU[0] + MAIN_MENU[1] + MAIN_MENU[2]:
        await context.bot.send_chat_action(chat_id, "typing")

        history = context.user_data.get("builder_history", [])
        answer = await ask_builder_ai(text, history)

        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": answer})
        context.user_data["builder_history"] = history[-20:]

        await update.message.reply_text(
            f"🧱 <b>Ответ ИИ-строителя</b>\n\n{answer}",
            parse_mode="HTML"
        )
        return

    # Другие разделы
    if text == "📍 Локации домов":
        return await show_locations_inline(update, context)

    if text == "🏗️ Проекты":
        return await show_projects_inline(update, context)

    if text == "👨‍💼 Связаться с менеджером":
        return await update.message.reply_text(
            "Менеджер на связи: +7 (910) 864-07-37",
            reply_markup=kb(MAIN_MENU)
        )

    if text == "🧮 Расчёт стоимости":
        return await update.message.reply_text(
            "Модуль расчёта стоимости скоро будет подключён.",
            reply_markup=kb(MAIN_MENU)
        )

    await update.message.reply_text("Выберите пункт меню 👇", reply_markup=kb(MAIN_MENU))

# ========= INLINE CALLBACKS =========
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    await q.answer()

    if data.startswith("loc:"):
        loc = data[4:]
        try:
            await q.edit_message_text(f"Локация {loc}:")
        except:
            pass
        return await send_location_card(q.message.chat, loc, context)

    if data == "back_to_locs":
        try:
            await q.edit_message_text("Выберите локацию:")
            await q.edit_message_reply_markup(make_locations_inline())
        except:
            await context.bot.send_message(q.message.chat_id, "Выберите локацию:", reply_markup=make_locations_inline())
        return

    if data.startswith("proj:"):
        proj = data[5:]
        try:
            await q.edit_message_text(f"Проект {proj}:")
        except:
            pass
        return await send_project_card(q.message.chat, proj, context)

    if data == "back_to_projects":
        try:
            await q.edit_message_text("Выберите проект:")
            await q.edit_message_reply_markup(make_projects_inline())
        except:
            await context.bot.send_message(q.message.chat_id, "Выберите проект:", reply_markup=make_projects_inline())
        return

    if data == "back_to_menu":
        context.user_data.clear()
        try:
            await q.edit_message_reply_markup(None)
        except:
            pass
        return await send_welcome_with_photo(update, context)

# ========= РЕГИСТРАЦИЯ ХЕНДЛЕРОВ =========
application.add_handler(CommandHandler(["start", "star"], cmd_start))
application.add_handler(CommandHandler("menu", cmd_menu))
application.add_handler(CommandHandler("ping", cmd_ping))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_error_handler(error_handler)

# ========= FLASK API =========
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
        return f"Webhook установлен: {url}"
    except Exception as e:
        logger.exception("Ошибка вебхука")
        return f"Ошибка: {e}", 500

@web_app.post("/webhook")
def webhook():
    ensure_initialized()
    data = flask_request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    try:
        LOOP.run_until_complete(application.process_update(update))
        return jsonify({"ok": True})
    except Exception as e:
        logger.exception("Ошибка обработки")
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    if BASE_URL:
        ensure_initialized()
        LOOP.run_until_complete(application.bot.set_webhook(f"{BASE_URL}/webhook"))
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)