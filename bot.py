import os
import time
import logging
import asyncio
from urllib.parse import unquote

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
import httpx  # ⬅️ для запросов к Groq

# ========= ENV =========
BOT_TOKEN = os.environ["BOT_TOKEN"]
BASE_URL  = os.environ.get("BASE_URL", "").rstrip("/")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")  # ⬅️ ключ Groq

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
    pool_timeout=20.0,
)
application = Application.builder().token(BOT_TOKEN).request(tg_request).build()
_initialized = False

def ensure_initialized() -> None:
    """Инициализируем PTB-Application ровно один раз в процессе."""
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

# ========= ЛОКАЦИИ (список, слаги, данные) =========
LOCATIONS = [
    "Шопино",
    "Чижовка",
    "р-н магазина METRO",
    "КП Южный",
    "Еловка",
    "ВеснаЛэнд (Черносвитино)",
    "Сивково",
    "Некрасово",
    "Груздово",
    "КП Московский",
]

# человекочитаемое название → slug (для путей к файлам)
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

def _loc_data(name: str, body: str, *, has_video: bool=False) -> dict:
    slug = LOC_SLUG[name]
    photo = f"{BASE_URL}/static/locations/{slug}/{slug}.jpg?v={CACHE_VER}" if BASE_URL else None
    pres  = f"{BASE_URL}/static/locations/{slug}/{slug}.pdf" if BASE_URL else None
    video = f"{BASE_URL}/static/locations/{slug}/video.mp4" if (BASE_URL and has_video) else None
    caption = f"<b>{name}</b>\n{body}"
    return {"photo": photo, "presentation": pres, "video": video, "caption": caption}

# === ОПИСАНИЯ ЛОКАЦИЙ ===
LOCATIONS_DATA = {
    "Шопино": _loc_data(
        "Шопино",
        "Современный посёлок в шаге от города: школы и детские сады в 5–7 минутах, "
        "крупные ТЦ — около 10 минут на автомобиле. Спортивные площадки и прогулочные зоны рядом, "
        "а до центра города — примерно 15–20 минут. Очень развитая система общественного транспорта."
    ),
    "Чижовка": _loc_data(
        "Чижовка",
        "Локация с развитой инфраструктурой: детские учреждения и школы в пешей доступности в мкр. Веснушки, "
        "торговые точки и фитнес-клубы — 8–10 минут до ТЦ. До центра на машине — около 15–20 минут. "
        "Отличный выбор для активных родителей: спорт, учёба и комфорт рядом."
    ),
    "р-н магазина METRO": _loc_data(
        "р-н магазина METRO",
        "Район около крупного гипермаркета METRO: торговые и бытовые услуги — в шаговой доступности. "
        "Детские сады и школы — 5–10 минут, спортивные объекты — 10–12 минут. "
        "До центра города — около 15–20 минут. Удобен для семей и тех, кто ценит быстрый доступ к сервисам."
    ),
    "КП Южный": _loc_data(
        "КП Южный",
        "Современный посёлок окруженный лесом на 23 домовладения в шаге от города: школы и детские сады в 10–15 минутах, "
        "крупные ТЦ — около 10 минут на автомобиле, а до центра города — примерно 10–15 минут.",
        has_video=True  # есть отдельное видео по локации
    ),
    "Еловка": _loc_data(
        "Еловка",
        "Спокойный посёлок для тех, кто хочет уединения, но оставаться в пределах города: "
        "школы и детсады есть, инфраструктура более пригородная. До центра — ~25–30 минут. "
        "Подойдёт для удалённой работы и более размеренного темпа жизни: рядом природа и меньше суеты."
    ),
    "ВеснаЛэнд (Черносвитино)": _loc_data(
        "ВеснаЛэнд (Черносвитино)",
        "Новая жилая зона с акцентом на семейный комфорт: дворовые площадки, зелёные зоны и удобные связи с городом. "
        "Детские учреждения и спорт — в близком окружении; до центра — около 10–15 минут. "
        "Одна из немногих локаций со всеми центральными коммуникациями."
    ),
    "Сивково": _loc_data(
        "Сивково",
        "Пригородная локация: дальше от центра (~30 минут), но плюсы — тишина, свежий воздух, больше пространства. "
        "Подходит тем, кто ценит размеренный стиль жизни, в том числе пенсионерам и удалённым специалистам."
    ),
    "Некрасово": _loc_data(
        "Некрасово",
        "Баланс близости и спокойствия: до центра — ~15–20 минут, школы и сады — 10–15 минут, "
        "торговля и спорт — чуть дальше. Комфорт загородной жизни без значительного удаления от города."
    ),
    "Груздово": _loc_data(
        "Груздово",
        "Спокойная локация с акцентом на проживание: до центра — ~30 минут, инфраструктура есть, "
        "но не ориентирована на интенсивный городской ритм. Хорошо для семей и тех, кто ценит тишину и пространство."
    ),
    "КП Московский": _loc_data(
        "КП Московский",
        "Коттеджный посёлок за городом: школы и сады — в пределах 10–15 минут на авто, до центра — ~20–25 минут. "
        "Подходит тем, кто хочет дом-«отдушину»: тишина, зелень, комфорт загородной жизни при гибком графике."
    ),
}

def make_locations_inline() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"loc:{name}")] for name in LOCATIONS]
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

# ========= ПРОЕКТЫ =========
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

# ========= ИИ-СТРОИТЕЛЬ (Groq) =========

BUILDER_SYSTEM_PROMPT = (
    "Ты — дружелюбный и аккуратный строитель-консультант. "
    "Объясняешь простым понятным языком, без снобизма и агрессии. "
    "Говоришь о плюсах и минусах разных решений, но ничего не 'разносишь' и не высмеиваешь. "
    "Если не уверен, честно говоришь об этом и предлагаешь несколько вариантов. "
    "Отвечай по делу, по возможности коротко и структурировано."
)

async def ask_builder_ai(user_message: str, history: list) -> str:
    """
    Вызов Groq Chat Completions.
    history — список dict'ов формата {"role": "user"/"assistant", "content": "..."}.
    """
    if not GROQ_API_KEY:
        return "ИИ-консультант сейчас временно недоступен. Попробуйте позже, пожалуйста."

    # Собираем историю (берем последние несколько сообщений)
    messages = [{"role": "system", "content": BUILDER_SYSTEM_PROMPT}]
    # ограничим историю, чтобы не раздувать запрос
    if history:
        messages.extend(history[-8:])
    messages.append({"role": "user", "content": user_message})

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.1-70b-versatile",
                    "messages": messages,
                },
            )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return content.strip()
    except Exception as e:
        logger.warning(f"Groq API error: {e}")
        return "Не получилось получить ответ от ИИ-консультанта. Попробуйте ещё раз чуть позже."

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

# ========= ЛОКАЦИИ (UI) =========
async def show_locations_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "LOC_LIST"
    text = "-----Вы в разделе локации домов-----\nВыберите локацию:"
    markup = make_locations_inline()

    if update.message:
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Локации:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup)

# Локация: сначала локальный файл → затем URL → затем fallback
async def send_location_card(chat, location_name: str, context: ContextTypes.DEFAULT_TYPE):
    data = LOCATIONS_DATA.get(location_name)
    if not data:
        await context.bot.send_message(chat_id=chat.id, text=f"Скоро добавим карточку для «{location_name}».")
        return

    photo_url = data.get("photo")
    presentation = data.get("presentation")
    video = data.get("video")

    # Кнопки без дублей: сначала презентация, потом видео
    buttons = []
    if presentation:
        buttons.append([InlineKeyboardButton("📘 Смотреть презентацию", url=presentation)])
    if video:
        buttons.append([InlineKeyboardButton("🎬 Смотреть видео", url=video)])
    buttons.append([InlineKeyboardButton("📋 К списку локаций", callback_data="back_to_locs")])
    buttons.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    markup = InlineKeyboardMarkup(buttons)

    sent = False
    try:
        local_path = None
        if photo_url and BASE_URL and photo_url.startswith(f"{BASE_URL}/"):
            rel_url = photo_url[len(BASE_URL):].lstrip("/")
            rel_path = unquote(rel_url.split("?", 1)[0])
            if rel_path.startswith("static/"):
                local_path = rel_path

        if local_path and os.path.isfile(local_path) and os.path.getsize(local_path) > 0:
            with open(local_path, "rb") as f:
                await context.bot.send_photo(
                    chat_id=chat.id,
                    photo=InputFile(f, filename=os.path.basename(local_path)),
                    caption=data["caption"],
                    parse_mode="HTML",
                    reply_markup=markup
                )
                sent = True
    except Exception as e:
        logger.warning(f"send_photo(local) failed for {location_name}: {e}")

    if not sent and photo_url:
        try:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=photo_url,
                caption=data["caption"],
                parse_mode="HTML",
                reply_markup=markup
            )
            sent = True
        except Exception as e:
            logger.warning(f"send_photo(url) failed for {location_name}: {e}")

    if not sent:
        # Последний резерв: только текст + кнопки
        await context.bot.send_message(
            chat_id=chat.id,
            text=data["caption"],
            parse_mode="HTML",
            reply_markup=markup
        )

# ========= ПРОЕКТЫ (UI) =========
async def show_projects_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "PROJ_LIST"
    text = "-----Вы в разделе проекты-----\nВыберите проект:"
    markup = make_projects_inline()

    if update.message:
        await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text("Проекты:", reply_markup=markup)
    else:
        await context.bot.send_message(update.effective_chat.id, text, reply_markup=markup)

# Проект: локальный файл → URL → fallback
async def send_project_card(chat, project_name: str, context: ContextTypes.DEFAULT_TYPE):
    data = PROJECTS_DATA.get(project_name)
    if not data:
        await context.bot.send_message(chat_id=chat.id, text=f"Скоро добавим карточку для «{project_name}».")
        return

    photo_url = data.get("photo")
    presentation = data["presentation"]

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📘 Смотреть презентацию", url=presentation)],
        [InlineKeyboardButton("📋 К списку проектов", callback_data="back_to_projects")],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])

    sent = False

    try:
        local_path = None
        if photo_url and BASE_URL and photo_url.startswith(f"{BASE_URL}/"):
            rel_url = photo_url[len(BASE_URL):].lstrip("/")
            rel_path = unquote(rel_url.split("?", 1)[0])
            if rel_path.startswith("static/"):
                local_path = rel_path

        if local_path and os.path.isfile(local_path) and os.path.getsize(local_path) > 0:
            with open(local_path, "rb") as f:
                await context.bot.send_photo(
                    chat_id=chat.id,
                    photo=InputFile(f, filename=os.path.basename(local_path)),
                    caption=data["caption"],
                    parse_mode="HTML",
                    reply_markup=markup
                )
                sent = True
    except Exception as e:
        logger.warning(f"send_photo(local) failed for {project_name}: {e}")

    if not sent and photo_url:
        try:
            await context.bot.send_photo(
                chat_id=chat.id,
                photo=photo_url,
                caption=data["caption"],
                parse_mode="HTML",
                reply_markup=markup
            )
            sent = True
        except Exception as e:
            logger.warning(f"send_photo(url) failed for {project_name}: {e}")

    if not sent:
        await context.bot.send_message(
            chat_id=chat.id,
            text=data["caption"],
            parse_mode="HTML",
            reply_markup=markup
        )

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

    # --- запуск ИИ-строителя ---
    if text == "🤖 Задать вопрос ИИ":
        context.user_data["state"] = "AI_CHAT"
        # очищаем/инициализируем историю диалога с ИИ
        context.user_data["ai_history"] = []
        await update.message.reply_text(
            "Я — ИИ-строитель MR.House.\n\n"
            "Задайте любой вопрос по строительству, материалам, фундаменту, планировкам и т.п. "
            "Я отвечу как аккуратный профессиональный консультант.\n\n"
            "Чтобы вернуться в главное меню — используйте команду /menu.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    # --- обработка сообщений, когда пользователь уже в чате с ИИ ---
    if state == "AI_CHAT":
        user_q = text
        history = context.user_data.get("ai_history") or []

        # добавляем вопрос в историю
        history.append({"role": "user", "content": user_q})
        context.user_data["ai_history"] = history

        # покажем "печатает..."
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        answer = await ask_builder_ai(user_q, history)

        # добавляем ответ в историю
        history.append({"role": "assistant", "content": answer})
        context.user_data["ai_history"] = history

        await update.message.reply_text(answer)
        return

    # --- обычные разделы ---
    if text == "📍 Локации домов":
        return await show_locations_inline(update, context)

    if text == "🏗️ Проекты":
        return await show_projects_inline(update, context)

    if state == "MAIN":
        mapping = {
            "🧮 Расчёт стоимости": "Введите желаемую площадь и бюджет (пока заглушка).",
            "👨‍💼 Связаться с менеджером": "Наш менеджер свяжется с вами: +7 (910) 864-07-37",
        }
        if text in mapping:
            return await update.message.reply_text(mapping[text], reply_markup=kb(MAIN_MENU))
        return await update.message.reply_text("Выберите кнопку ниже 👇", reply_markup=kb(MAIN_MENU))

    return  # остальное — кликами по inline

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

# ========= FLASK (экспортируем 'web_app') =========
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
    data = flask_request.get_json(force=True, silent=False)
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