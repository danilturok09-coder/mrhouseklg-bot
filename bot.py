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

# id, куда отправлять лиды
MANAGER_CHAT_ID = 759463205

# Принудительное обновление кэша Telegram
CACHE_VER = "2025-11-05-3"

# ========= LOGGING =========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# ========= GLOBAL LOOP =========
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)

# ========= PTB APP =========
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

# ========= ЛОКАЦИИ =========
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

def _loc_data(name: str, body: str, *, has_video: bool = False) -> dict:
    slug = LOC_SLUG[name]
    photo = f"{BASE_URL}/static/locations/{slug}/{slug}.jpg?v={CACHE_VER}" if BASE_URL else None
    pres  = f"{BASE_URL}/static/locations/{slug}/{slug}.pdf" if BASE_URL else None
    video = f"{BASE_URL}/static/locations/{slug}/video.mp4" if (BASE_URL and has_video) else None
    caption = f"<b>{name}</b>\n{body}"
    return {"photo": photo, "presentation": pres, "video": video, "caption": caption}

# === ОПИСАНИЯ ЛОКАЦИЙ (твои тексты) ===
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
        "Современный посёлок окружённый лесом на 23 домовладения в шаге от города: школы и детские сады в 10–15 минутах, "
        "крупные ТЦ — около 10 минут на автомобиле, а до центра города — примерно 10–15 минут.",
        has_video=True  # хотим кнопку «Смотреть видео»
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

# ========= ПРОЕКТЫ (раздел «Проекты», как у тебя) =========
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
            "• Крыльцо: 3,5 м²\n\n"
            "💰 <b>Стоимость строительства:</b> 5 700 000 р."
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
            "• Крыльцо: 3,5 м²\n\n"
            "💰 <b>Стоимость строительства:</b> 6 000 000 р."
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
            "• Крыльцо: 3,5 м²\n\n"
            "💰 <b>Стоимость строительства:</b> 6 200 000 р."
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
            "• Крыльцо: 3,5 м²\n\n"
            "💰 <b>Стоимость строительства:</b> 6 700 000 р."
        ),
        "presentation": f"{BASE_URL}/static/projects/vesna112/vesna112.pdf",
    },
}

def make_projects_inline() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"🏡 {name}", callback_data=f"proj:{name}")] for name in PROJECTS]
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

# ========= КАЛЬКУЛЯТОР =========

# цены за "тёплый контур"
PROJECT_BASE_PRICES = {
    "Уют 90": 5_200_000,
    "Весна 90": 5_700_000,
    "Весна 98": 6_000_000,
    "Весна 105": 6_200_000,
    "Простор 110": 6_500_000,
    "Весна 112": 6_700_000,
    "Простор 114": 6_700_000,
    "Простор 120": 7_000_000,
    "Простор 130": 7_900_000,
}

PROJECT_AREAS = {
    "Уют 90": 90,
    "Весна 90": 90,
    "Весна 98": 98,
    "Весна 105": 105,
    "Простор 110": 110,
    "Весна 112": 112,
    "Простор 114": 114,
    "Простор 120": 120,
    "Простор 130": 130,
}

CALC_PROJECTS = [
    "Уют 90",
    "Весна 90",
    "Весна 98",
    "Весна 105",
    "Простор 110",
    "Весна 112",
    "Простор 114",
    "Простор 120",
    "Простор 130",
]

PRICE_PRE_FINISH_PER_SQM = 15_000
PRICE_COMMUNICATIONS = 500_000
CUSTOM_PRICE_PER_SQM_1F = 63_300  # одноэтажный
CUSTOM_PRICE_PER_SQM_2F = 61_300  # двухэтажный

def format_rub(value: int) -> str:
    return f"{value:,.0f} ₽".replace(",", " ")

def build_project_calc_summary(name: str) -> str:
    base = PROJECT_BASE_PRICES[name]
    sqm = PROJECT_AREAS.get(name)
    pre = (sqm or 0) * PRICE_PRE_FINISH_PER_SQM
    comms = PRICE_COMMUNICATIONS
    rate = int(base / sqm) if sqm else None

    txt = "📐 <b>Предварительный расчёт</b>\n\n"
    txt += f"🏠 Дом: {name}"
    if sqm:
        txt += f" ({sqm} м²)"
    txt += "\n\n"

    if rate:
        txt += (
            f"1) Тёплый контур ({format_rub(rate)} за м²): <b>{format_rub(base)}</b>\n"
            f"2) Предчистовая отделка ({format_rub(PRICE_PRE_FINISH_PER_SQM)} за м²): "
            f"+{format_rub(pre)}\n"
            f"3) Коммуникации (газ, свет, вода, канализация): +{format_rub(comms)}\n\n"
            "Это предварительный расчёт, не публичная оферта.\n"
            "Точный просчёт сделает менеджер после уточнения деталей."
        )
    else:
        txt += (
            f"1) Тёплый контур: <b>{format_rub(base)}</b>\n"
            f"2) Предчистовая отделка: +{format_rub(pre)}\n"
            f"3) Коммуникации (газ, свет, вода, канализация): +{format_rub(comms)}\n\n"
            "Это предварительный расчёт, не публичная оферта.\n"
            "Точный просчёт сделает менеджер после уточнения деталей."
        )

    return txt

def build_custom_calc_summary(sqm: int, floors: int) -> str:
    rate = CUSTOM_PRICE_PER_SQM_1F if floors == 1 else CUSTOM_PRICE_PER_SQM_2F
    base = sqm * rate
    pre = sqm * PRICE_PRE_FINISH_PER_SQM
    comms = PRICE_COMMUNICATIONS
    total = base + pre + comms

    txt = "📐 <b>Предварительный расчёт</b>\n\n"
    txt += f"🏠 Площадь: <b>{sqm} м²</b>, этажность: <b>{floors}</b>\n\n"
    
    txt += (
    f"1) Тёплый контур ({format_rub(rate)} за м²): <b>{format_rub(base)}</b>\n"
    f"2) Предчистовая отделка ({format_rub(PRICE_PRE_FINISH_PER_SQM)} за м²): "
    f"+{format_rub(pre)}\n"
    f"3) Коммуникации (газ, свет, вода, канализация): +{format_rub(comms)}\n\n"
    "Это предварительный расчёт, не публичная оферта.\n"
    "Точный просчёт сделает менеджер после уточнения деталей."
)
    return txt

async def send_calc_or_request_contacts(chat_id: int, context: ContextTypes.DEFAULT_TYPE, summary_text: str):
    """Если контактов ещё нет — просим их, иначе сразу отправляем расчёт."""
    user_data = context.user_data
    if not user_data.get("has_contacts"):
        user_data["pending_calc_result"] = summary_text
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📲 Оставить контакты", callback_data="calc:leave_contacts")],
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
        ])
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Чтобы показать подробный расчёт, оставьте, пожалуйста, контакты.\n\n"
                "Например: «Антон, +7 9ХХ ХХХ-ХХ-ХХ».\n"
                "После этого менеджер свяжется с вами и уточнит детали."
            ),
            reply_markup=markup
        )
    else:
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")]
        ])
        await context.bot.send_message(
            chat_id=chat_id,
            text=summary_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        
async def start_calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск раздела расчёта стоимости."""
    chat_id = update.effective_chat.id
    context.user_data["state"] = "CALC_MENU"

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏡 Выбрать типовой проект", callback_data="calc:mode_proj")],
        [InlineKeyboardButton("📏 Указать свою площадь", callback_data="calc:mode_custom")],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])

    await update.message.reply_text(
        "📐 Давайте прикинем ориентировочную стоимость дома.\n\n"
        "Выберите, как удобнее считать:",
        reply_markup=markup
    )

# ========= ИИ-СТРОИТЕЛЬ (Groq) =========

BUILDER_SYSTEM_PROMPT = (
    "Ты — спокойный, вежливый и профессиональный строительный консультант.\n\n"
    "Контекст:\n"
    "- Частное домостроение в России.\n"
    "- Клиенты строят дома под постоянное проживание или как дачу.\n"
    "- Типовые решения: свайно-ростверковый фундамент (ключевой вариант), монолитная плита, лента; "
    "стены — газобетон, керамоблок, каркас; кровля — металлочерепица, мягкая кровля.\n\n"
    "Тон общения:\n"
    "- Объясняй простым, понятным разговорным языком.\n"
    "- Не используй жёсткую критику и не «таптывай» чужие решения.\n"
    "- Если решение спорное, мягко укажи на минусы и сразу предложи несколько альтернатив.\n"
    "- Не запугивай, но аккуратно отмечай риски.\n\n"
    "Структура ответа (очень важно соблюдать):\n"
    "1) Краткий вывод (2–4 предложения): суть ситуации и главное мнение.\n"
    "2) По пунктам — списком (если уместно):\n"
    "   - Фундамент (особое внимание свайно-ростверковым и их применимости на разных грунтах).\n"
    "   - Стены / перекрытия / крыша.\n"
    "   - Теплотехника: утепление, точки росы, вентиляция.\n"
    "   - Инженерка (если вопрос про коммуникации: вода, канализация, отопление, газ, электричество).\n"
    "3) На что обратить внимание: 3–7 коротких bullet-пунктов.\n"
    "4) Что лучше уточнить: 3–5 конкретных вопросов к пользователю.\n\n"
    "Если не хватает данных (нет геологии, непонятен тип грунта, этажность, климат региона и т.п.), "
    "обязательно скажи об этом отдельно и предложи, что именно нужно уточнить.\n\n"
    "Сначала мысленно разложи задачу на шаги и прикинь варианты решения, "
    "но в ответ выводи только итог, аккуратно структурированный, без описания своего внутреннего хода мыслей.\n\n"
    "Не давай юридически обязывающих обещаний. В важных местах (фундамент, несущие конструкции, газ, электрика) "
    "рекомендуй согласовать решение с местным конструктором или профильным инженером.\n"
)

async def ask_builder_ai(user_message: str, history: list) -> str:
    """Вызов Groq (llama-3.1-8b-instant) с контекстом диалога."""
    if not GROQ_API_KEY:
        return "ИИ-консультант временно недоступен. Пожалуйста, попробуйте позже."

    messages = [{"role": "system", "content": BUILDER_SYSTEM_PROMPT}]
    if history:
        messages.extend(history[-12:])
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": messages,
        "temperature": 0.35,
        "max_tokens": 900,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if resp.status_code != 200:
            logger.warning(f"Groq API returned {resp.status_code}: {resp.text}")
            return (
                "Не удалось получить ответ от ИИ-строителя. "
                "Возможно, сервер перегружен. Попробуйте позже."
            )

        data = resp.json()
        answer = data["choices"][0]["message"]["content"].strip()
        return answer

    except Exception as e:
        logger.warning(f"Groq API error: {e}")
        return "ИИ-консультант временно недоступен. Пожалуйста, попробуйте чуть позже."

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
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=banner_url,
                caption=caption,
                parse_mode="HTML"
            )
            sent_banner = True
        except Exception as e:
            logger.warning(f"Не смог отправить фото-баннер: {e}")

    if not sent_banner:
        await context.bot.send_message(
            chat_id=chat_id,
            text="👋 Привет! Я бот MR.House. Готов помочь.",
            parse_mode="HTML"
        )
    await context.bot.send_message(
        chat_id=chat_id,
        text="Выберите раздел 👇",
        reply_markup=kb(MAIN_MENU)
    )
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

async def send_location_card(chat, location_name: str, context: ContextTypes.DEFAULT_TYPE):
    """Локация: сначала локальный файл → затем URL → затем fallback."""
    data = LOCATIONS_DATA.get(location_name)
    if not data:
        await context.bot.send_message(chat_id=chat.id, text=f"Скоро добавим карточку для «{location_name}».")
        return

    photo_url = data.get("photo")
    presentation = data.get("presentation")
    video = data.get("video")

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

async def send_project_card(chat, project_name: str, context: ContextTypes.DEFAULT_TYPE):
    """Проект: локальный файл → URL → fallback."""
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
    has_contacts = context.user_data.get("has_contacts", False)
    builder_history = context.user_data.get("builder_history", [])

    context.user_data.clear()

    if has_contacts:
        context.user_data["has_contacts"] = True
    if builder_history:
        context.user_data["builder_history"] = builder_history

    await send_welcome_with_photo(update, context)
async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "MAIN"
    await update.message.reply_text("Главное меню 👇", reply_markup=kb(MAIN_MENU))

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Бот работает ✅")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    state = context.user_data.get("state", "MAIN")
    chat_id = update.effective_chat.id

    # ==== Общие кнопки (работают в любых состояниях) ====

    if text == "📍 Локации домов":
        return await show_locations_inline(update, context)

    if text == "🏗️ Проекты":
        return await show_projects_inline(update, context)

    if text == "🧮 Расчёт стоимости":
        return await start_calc(update, context)

    if text == "👨‍💼 Связаться с менеджером":
        await update.message.reply_text(
            "📞 <b>Связь с менеджером MR.House</b>\n\n"
            "Вы можете написать или позвонить лично:\n"
            "👤 Данил\n"
            "📱 +7 (910) 864-07-37\n\n"
            "Также менеджер свяжется с вами, если вы оставляли контакты в расчёте стоимости.",
            parse_mode="HTML",
            reply_markup=kb(MAIN_MENU)
        )
        return

    # ==== ИИ-строитель: вход в режим ====
    if text == "🤖 Задать вопрос ИИ":
        context.user_data["state"] = "ASK_AI"
        await update.message.reply_text(
            "🧱 <b>Вы открыли чат с ИИ-строителем MR.House</b>\n\n"
            "Здесь можно задавать вопросы про участок, фундамент (особенно свайно-ростверковый), коробку, "
            "утепление, инженерку и отделку.\n"
            "Я помню контекст нашей беседы в рамках этого чата и стараюсь подбирать советы под вашу ситуацию.\n\n"
            "Напишите первый вопрос, например:\n"
            "• «Какой фундамент выбрать на суглинке с высоким УГВ?»\n"
            "• «Газобетон или керамоблок для дома 120 м²?»\n"
            "• «Как лучше развести тёплый пол и радиаторы?»",
            parse_mode="HTML",
            reply_markup=kb(MAIN_MENU)
        )
        return

    # ==== ИИ-строитель: обработка вопросов ====
    if state == "ASK_AI" and text not in (
        "📍 Локации домов", "🏗️ Проекты",
        "🧮 Расчёт стоимости", "👨‍💼 Связаться с менеджером"
    ):
        # логируем вопросы
        try:
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            line = f"{ts} | chat_id={chat_id} | {text}\n"
            with open("builder_questions.log", "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            logger.warning(f"Не удалось записать вопрос ИИ в файл: {e}")

        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        except Exception:
            pass

        history = context.user_data.get("builder_history", [])
        answer = await ask_builder_ai(text, history)

        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": answer})
        context.user_data["builder_history"] = history[-40:]

        nice_answer = "🧱 <b>Ответ ИИ-строителя</b>\n\n" + answer
        await update.message.reply_text(nice_answer, parse_mode="HTML")
        return

    # ==== Калькулятор: ожидание площади ====
    if state == "CALC_WAIT_SQM":
        # ждём число — площадь дома
        cleaned = text.replace(",", ".").split()[0]
        try:
            sqm = int(float(cleaned))
        except ValueError:
            await update.message.reply_text(
                "Пожалуйста, введите число — площадь дома в м² (например, 120)."
            )
            return

        floors = context.user_data.get("calc_floors", 1)
        summary = build_custom_calc_summary(sqm, floors)
        await send_calc_or_request_contacts(chat_id, context, summary)
        # после расчёта можно вернуться в главное меню, но state не трогаем — он не мешает
        return

    # ==== Калькулятор: ожидание контактов ====
    if state == "CALC_WAIT_CONTACTS":
        contact_text = text.strip()
        pending = context.user_data.get("pending_calc_result")

        user = update.effective_user
        user_tag = f"@{user.username}" if user.username else f"id={user.id}"

        # отправляем лид менеджеру
        try:
            msg = (
                "📩 Новый запрос на расчёт из бота MR.House\n\n"
                f"{user_tag}\n"
                f"Имя/телефон: {contact_text}\n\n"
            )
            if pending:
                msg += "📐 Расчёт:\n" + pending
            await context.bot.send_message(MANAGER_CHAT_ID, msg, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не удалось отправить лид менеджеру: {e}")

        context.user_data["has_contacts"] = True
        await update.message.reply_text(
            "Спасибо! Контакты записал и отправил менеджеру. Ниже — ваш ориентировочный расчёт 👇"
        )

        if pending:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")]
            ])
            await update.message.reply_text(
                pending,
                parse_mode="HTML",
                reply_markup=markup
            )

        context.user_data["pending_calc_result"] = None
        context.user_data["state"] = "MAIN"
        return

    # ==== MAIN / дефолт ====
    if state == "MAIN":
        await update.message.reply_text("Выберите кнопку ниже 👇", reply_markup=kb(MAIN_MENU))
        return

    # Остальное — кликами по inline
    return
    
async def handle_callback(query_update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = query_update.callback_query
    data = query.data or ""
    await query.answer()
    user_data = context.user_data

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
            await context.bot.send_message(
                query.message.chat_id,
                "Выберите локацию:",
                reply_markup=make_locations_inline()
            )
        user_data["state"] = "LOC_LIST"
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
            await context.bot.send_message(
                query.message.chat_id,
                "Выберите проект:",
                reply_markup=make_projects_inline()
            )
        user_data["state"] = "PROJ_LIST"
        return

    # ===== КАЛЬКУЛЯТОР: inline-кнопки =====

    # режим выбора: проект / своя площадь
    if data == "calc:mode_proj":
        user_data["state"] = "CALC_MENU"
        rows = [
            [InlineKeyboardButton(name, callback_data=f"calc:p:{i}")]
            for i, name in enumerate(CALC_PROJECTS)
        ]
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="calc:back_menu")])
        markup = InlineKeyboardMarkup(rows)
        try:
            await query.edit_message_text("Выберите проект для расчёта:", reply_markup=markup)
        except Exception:
            await context.bot.send_message(
                query.message.chat_id,
                "Выберите проект для расчёта:",
                reply_markup=markup
            )
        return

    if data == "calc:mode_custom":
        user_data["state"] = "CALC_CHOOSE_FLOORS"
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("1 этаж", callback_data="calc:floor:1"),
                InlineKeyboardButton("2 этажа", callback_data="calc:floor:2"),
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="calc:back_menu")],
        ])
        try:
            await query.edit_message_text("Выберите количество этажей:", reply_markup=markup)
        except Exception:
            await context.bot.send_message(
                query.message.chat_id,
                "Выберите количество этажей:",
                reply_markup=markup
            )
        return

    if data.startswith("calc:floor:"):
        floors = int(data.split(":")[2])
        user_data["calc_floors"] = floors
        user_data["state"] = "CALC_WAIT_SQM"
        try:
            await query.edit_message_text("Введите желаемую площадь дома в м² (например, 120).")
        except Exception:
            await context.bot.send_message(
                query.message.chat_id,
                "Введите желаемую площадь дома в м² (например, 120)."
            )
        return

    if data.startswith("calc:p:"):
        idx = int(data.split(":")[2])
        proj_name = CALC_PROJECTS[idx]
        summary = build_project_calc_summary(proj_name)
        chat_id = query.message.chat.id
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await send_calc_or_request_contacts(chat_id, context, summary)
        return

    if data == "calc:back_menu":
        # возвращаем корневое меню калькулятора
        user_data["state"] = "CALC_MENU"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏡 Выбрать типовой проект", callback_data="calc:mode_proj")],
            [InlineKeyboardButton("📏 Указать свою площадь", callback_data="calc:mode_custom")],
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
        ])
        try:
            await query.edit_message_text(
                "📐 Давайте прикинем ориентировочную стоимость дома.\n\n"
                "Выберите, как удобнее считать:",
                reply_markup=markup
            )
        except Exception:
            await context.bot.send_message(
                query.message.chat_id,
                "📐 Давайте прикинем ориентировочную стоимость дома.\n\n"
                "Выберите, как удобнее считать:",
                reply_markup=markup
            )
        return

    if data == "calc:leave_contacts":
        user_data["state"] = "CALC_WAIT_CONTACTS"
        await context.bot.send_message(
            chat_id=query.message.chat.id,
            text=(
                "✍️ Напишите, пожалуйста, как вас зовут и телефон в одном сообщении.\n\n"
                "Например: «Антон, +7 9ХХ ХХХ-ХХ-ХХ»."
            )
        )
        return

    # В меню
    
if data == "back_to_menu":
    has_contacts = user_data.get("has_contacts", False)
    builder_history = user_data.get("builder_history", [])

    user_data.clear()

    if has_contacts:
        user_data["has_contacts"] = True
    if builder_history:
        user_data["builder_history"] = builder_history

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
