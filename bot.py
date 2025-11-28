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

# ID чата, куда слать заявки по расчёту
MANAGER_CHAT_ID = 759463205

# Принудительное обновление кэша Telegram (увидел новые картинки — увеличь версию)
CACHE_VER = "2025-11-05-3"

# ========= ЛОГИ =========
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
        has_video=True
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

# ========= ПРОЕКТЫ (витрина) =========
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

# ========= КАЛЬКУЛЯТОР СТОИМОСТИ =========

# цены за тёплый контур по проектам
COST_PROJECTS = {
    "uyut90":       {"name": "Уют 90",       "area": 90,  "price": 5_200_000},
    "vesna90":      {"name": "Весна 90",     "area": 90,  "price": 5_700_000},
    "vesna98":      {"name": "Весна 98",     "area": 98,  "price": 6_000_000},
    "vesna105":     {"name": "Весна 105",    "area": 105, "price": 6_200_000},
    "prostor110":   {"name": "Простор 110",  "area": 110, "price": 6_500_000},
    "vesna112":     {"name": "Весна 112",    "area": 112, "price": 6_700_000},
    "prostor114":   {"name": "Простор 114",  "area": 114, "price": 6_700_000},
    "prostor120":   {"name": "Простор 120",  "area": 120, "price": 7_000_000},
    "prostor130":   {"name": "Простор 130",  "area": 130, "price": 7_900_000},
}

COST_PER_M2_ONE_FLOOR = 63_300    # тёплый контур, 1 этаж
COST_PER_M2_TWO_FLOORS = 61_300   # тёплый контур, 2 этажа
COST_PRED_PER_M2 = 15_000         # предчистовая
COST_COMMUNICATIONS = 500_000     # газ, свет, вода, канализация

def fmt_rub(value: int) -> str:
    return f"{value:,.0f}".replace(",", " ") + " ₽"

def build_cost_result_text(cost: dict) -> str:
    mode = cost.get("mode")
    finish = cost.get("finish")
    comm = cost.get("comm", False)

    comm_price = COST_COMMUNICATIONS if comm else 0

    if mode == "project":
        name = cost["project_name"]
        area = cost["area"]
        base_warm = cost["base_warm_price"]

        if finish == "warm":
            warm_price = base_warm
            pred_extra = 0
        else:
            warm_price = base_warm
            pred_extra = area * COST_PRED_PER_M2

        house_price = warm_price + pred_extra
        total = house_price + comm_price

        text = (
            "📐 <b>Ориентировочный расчёт стоимости дома</b>\n\n"
            f"<b>Проект:</b> {name}\n"
            f"<b>Площадь:</b> {area} м²\n"
            f"<b>Комплектация:</b> {'тёплый контур' if finish == 'warm' else 'тёплый контур + предчистовая'}\n\n"
            f"🏠 Тёплый контур: <b>{fmt_rub(warm_price)}</b>\n"
        )
        if pred_extra:
            text += f"🎨 Предчистовая отделка: <b>+{fmt_rub(pred_extra)}</b>\n"
        if comm_price:
            text += f"🔌 Коммуникации (газ, свет, вода, канализация): <b>+{fmt_rub(comm_price)}</b>\n"

        text += f"\n<b>Итого ориентировочно:</b> {fmt_rub(total)}\n\n"
        text += "Это предварительный расчёт, не публичная оферта. Точный просчёт сделает менеджер после уточнения деталей."
        return text

    if mode == "custom":
        area = cost["area"]
        floors = cost["floors"]
        per_m2 = cost["per_m2"]

        warm_price = area * per_m2
        if finish == "warm":
            pred_extra = 0
        else:
            pred_extra = area * COST_PRED_PER_M2

        house_price = warm_price + pred_extra
        total = house_price + comm_price

        text = (
            "📐 <b>Ориентировочный расчёт стоимости дома</b>\n\n"
            f"<b>Площадь:</b> {area} м²\n"
            f"<b>Этажность:</b> {floors}\n"
            f"<b>Цена за м² (тёплый контур):</b> {fmt_rub(per_m2)}\n"
            f"<b>Комплектация:</b> {'тёплый контур' if finish == 'warm' else 'тёплый контур + предчистовая'}\n\n"
            f"🏠 Тёплый контур: <b>{fmt_rub(warm_price)}</b>\n"
        )
        if pred_extra:
            text += f"🎨 Предчистовая отделка: <b>+{fmt_rub(pred_extra)}</b>\n"
        if comm_price:
            text += f"🔌 Коммуникации (газ, свет, вода, канализация): <b>+{fmt_rub(comm_price)}</b>\n"

        text += f"\n<b>Итого ориентировочно:</b> {fmt_rub(total)}\n\n"
        text += "Это предварительный расчёт, не публичная оферта. Точный просчёт сделает менеджер после уточнения деталей."
        return text

    return "Не удалось собрать данные для расчёта. Попробуйте начать расчёт заново, пожалуйста."

async def notify_manager_about_cost(context: ContextTypes.DEFAULT_TYPE, chat_id: int, username: str | None,
                                    cost: dict, contact_info: str | None):
    try:
        mode = cost.get("mode")
        header = "🧮 Новая заявка на расчёт стоимости\n\n"

        if username:
            header += f"From: @{username}\n"
        header += f"Chat ID: {chat_id}\n"
        if contact_info:
            header += f"Контакты: {contact_info}\n\n"
        else:
            header += "Контакты: не указаны\n\n"

        if mode == "project":
            header += (
                f"Режим: готовый проект\n"
                f"Проект: {cost.get('project_name')}\n"
                f"Площадь: {cost.get('area')} м²\n"
            )
        elif mode == "custom":
            header += (
                f"Режим: своя площадь\n"
                f"Площадь: {cost.get('area')} м²\n"
                f"Этажность: {cost.get('floors')}\n"
            )

        header += f"Комплектация: {'тёплый контур' if cost.get('finish') == 'warm' else 'тёплый контур + предчистовая'}\n"
        header += f"Коммуникации: {'да' if cost.get('comm') else 'нет'}\n\n"

        result_text = build_cost_result_text(cost)
        msg = header + "----\n" + result_text

        await context.bot.send_message(chat_id=MANAGER_CHAT_ID, text=msg, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"Не удалось отправить расчёт менеджеру: {e}")

def make_cost_start_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏡 Выбрать готовый проект", callback_data="cost_mode:project")],
        [InlineKeyboardButton("📏 Указать свою площадь", callback_data="cost_mode:custom")],
        [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
    ])

def make_cost_projects_markup() -> InlineKeyboardMarkup:
    rows = []
    for slug, info in COST_PROJECTS.items():
        rows.append([InlineKeyboardButton(info["name"], callback_data=f"cost_proj:{slug}")])
    rows.append([InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(rows)

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
def _reset_user_data_keep_flags(context: ContextTypes.DEFAULT_TYPE):
    has_contacts = context.user_data.get("has_contacts")
    builder_history = context.user_data.get("builder_history")
    context.user_data.clear()
    if has_contacts:
        context.user_data["has_contacts"] = has_contacts
    if builder_history:
        context.user_data["builder_history"] = builder_history

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
    _reset_user_data_keep_flags(context)
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

    # ==== Вход в раздел ИИ ====
    if text == "🤖 Задать вопрос ИИ":
        context.user_data["state"] = "ASK_AI"
        await update.message.reply_text(
            "🧱 <b>Вы открыли чат с ИИ-строителем MR.House</b>\n\n"
            "Здесь можно задавать вопросы про участок, фундамент, коробку, утепление, инженерку и отделку.\n"
            "Я помню контекст нашего диалога в рамках этой переписки и стараюсь подбирать советы под вашу ситуацию.\n\n"
            "Напишите ваш первый вопрос, например:\n"
            "• «Какой фундамент выбрать на суглинке с высоким УГВ?»\n"
            "• «Газобетон или керамоблок для дома 120 м²?»\n"
            "• «Как лучше развести тёплый пол и радиаторы?»",
            parse_mode="HTML",
            reply_markup=kb(MAIN_MENU)
        )
        return

    # ==== Вопросы к ИИ ====
    if state == "ASK_AI" and text not in (
        "📍 Локации домов", "🏗️ Проекты",
        "🧮 Расчёт стоимости", "👨‍💼 Связаться с менеджером"
    ):
        # логируем вопрос
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

    # ==== КАЛЬКУЛЯТОР: старт ====
    if text == "🧮 Расчёт стоимости":
        context.user_data["state"] = "COST_MAIN"
        context.user_data["cost_ctx"] = {}
        await update.message.reply_text(
            "📐 Давайте прикинем стоимость дома.\n\n"
            "Выберите, как будем считать:",
            reply_markup=make_cost_start_markup()
        )
        return

    # ==== КАЛЬКУЛЯТОР: ввод площади ====
    if state == "COST_WAIT_AREA" and text not in (
        "📍 Локации домов", "🏗️ Проекты",
        "🧮 Расчёт стоимости", "👨‍💼 Связаться с менеджером"
    ):
        try:
            area = int(float(text.replace(",", ".").strip()))
        except Exception:
            await update.message.reply_text(
                "Не удалось распознать площадь. Введите число, например: 120"
            )
            return

        if area <= 0 or area > 1000:
            await update.message.reply_text(
                "Площадь выглядит странно. Введите реальное число от 20 до 1000 м²."
            )
            return

        cost = context.user_data.get("cost_ctx", {})
        cost["mode"] = "custom"
        cost["area"] = area
        context.user_data["cost_ctx"] = cost
        context.user_data["state"] = "COST_CHOOSE_FLOORS"

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("1 этаж", callback_data="cost_cf:1")],
            [InlineKeyboardButton("2 этажа", callback_data="cost_cf:2")],
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
        ])
        await update.message.reply_text(
            f"Принял площадь: {area} м².\nТеперь выберите этажность дома:",
            reply_markup=markup
        )
        return

    # ==== КАЛЬКУЛЯТОР: ввод контактов ====
    if state == "COST_WAIT_CONTACTS" and text not in (
        "📍 Локации домов", "🏗️ Проекты",
        "🧮 Расчёт стоимости", "👨‍💼 Связаться с менеджером"
    ):
        cost = context.user_data.get("cost_ctx")
        if not cost:
            await update.message.reply_text(
                "Похоже, расчёт сбился. Попробуйте начать расчёт заново через кнопку «🧮 Расчёт стоимости»."
            )
            context.user_data["state"] = "MAIN"
            return

        contact_info = text.strip()
        context.user_data["has_contacts"] = True
        context.user_data["contact_info"] = contact_info
        context.user_data["state"] = "MAIN"

        await update.message.reply_text(
            "Спасибо! Отправляю ориентировочный расчёт 👇",
            reply_markup=kb(MAIN_MENU)
        )

        result_text = build_cost_result_text(cost)
        await update.message.reply_text(result_text, parse_mode="HTML")

        await notify_manager_about_cost(
            context=context,
            chat_id=chat_id,
            username=update.effective_user.username if update.effective_user else None,
            cost=cost,
            contact_info=contact_info,
        )
        return

    # ==== Остальные разделы ====
    if text == "📍 Локации домов":
        return await show_locations_inline(update, context)

    if text == "🏗️ Проекты":
        return await show_projects_inline(update, context)

    if state == "MAIN":
        mapping = {
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
    chat = query.message.chat

    # ==== КАЛЬКУЛЯТОР: режим ====
    if data.startswith("cost_mode:"):
        mode = data.split(":", 1)[1]
        cost = {}
        cost["mode"] = mode
        context.user_data["cost_ctx"] = cost

        if mode == "project":
            context.user_data["state"] = "COST_PROJECT"
            await query.edit_message_text("Выберите проект для расчёта:")
            await query.edit_message_reply_markup(reply_markup=make_cost_projects_markup())
        elif mode == "custom":
            context.user_data["state"] = "COST_WAIT_AREA"
            try:
                await query.edit_message_text(
                    "Введите желаемую площадь дома в м² (например, 120)."
                )
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text="Введите желаемую площадь дома в м² (например, 120)."
                )
        return

    # ==== КАЛЬКУЛЯТОР: выбор проекта ====
    if data.startswith("cost_proj:"):
        slug = data.split(":", 1)[1]
        info = COST_PROJECTS.get(slug)
        if not info:
            await context.bot.send_message(chat.id, "Проект не найден. Попробуйте ещё раз.")
            return

        cost = context.user_data.get("cost_ctx", {})
        cost["mode"] = "project"
        cost["project_slug"] = slug
        cost["project_name"] = info["name"]
        cost["area"] = info["area"]
        cost["base_warm_price"] = info["price"]
        context.user_data["cost_ctx"] = cost

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 Тёплый контур", callback_data="cost_finish:warm")],
            [InlineKeyboardButton("🧱 Предчистовая отделка", callback_data="cost_finish:pred")],
            [InlineKeyboardButton("⬅️ К выбору проекта", callback_data="cost_mode:project")],
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
        ])

        try:
            await query.edit_message_text(
                f"Проект: {info['name']} ({info['area']} м²)\n\nВыберите комплектацию:"
            )
            await query.edit_message_reply_markup(reply_markup=markup)
        except Exception:
            await context.bot.send_message(
                chat.id,
                f"Проект: {info['name']} ({info['area']} м²)\n\nВыберите комплектацию:",
                reply_markup=markup
            )
        return

    # ==== КАЛЬКУЛЯТОР: этажность (для своей площади) ====
    if data.startswith("cost_cf:"):
        floors_str = data.split(":", 1)[1]
        floors = 1 if floors_str == "1" else 2

        cost = context.user_data.get("cost_ctx", {})
        cost["mode"] = "custom"
        cost["floors"] = floors
        cost["per_m2"] = COST_PER_M2_ONE_FLOOR if floors == 1 else COST_PER_M2_TWO_FLOORS
        context.user_data["cost_ctx"] = cost

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 Тёплый контур", callback_data="cost_finish:warm")],
            [InlineKeyboardButton("🧱 Предчистовая отделка", callback_data="cost_finish:pred")],
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
        ])

        try:
            await query.edit_message_text(
                f"Этажность: {floors}.\n\nВыберите комплектацию:"
            )
            await query.edit_message_reply_markup(reply_markup=markup)
        except Exception:
            await context.bot.send_message(
                chat.id,
                f"Этажность: {floors}.\n\nВыберите комплектацию:",
                reply_markup=markup
            )
        return

    # ==== КАЛЬКУЛЯТОР: комплектация ====
    if data.startswith("cost_finish:"):
        finish = data.split(":", 1)[1]
        cost = context.user_data.get("cost_ctx", {})
        cost["finish"] = finish
        context.user_data["cost_ctx"] = cost

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да, с коммуникациями (+500 000 ₽)", callback_data="cost_comm:yes")],
            [InlineKeyboardButton("❌ Нет, без коммуникаций", callback_data="cost_comm:no")],
            [InlineKeyboardButton("🏠 Вернуться в меню", callback_data="back_to_menu")],
        ])

        try:
            await query.edit_message_text(
                "Добавить коммуникации (газ, свет, вода, канализация) за 500 000 ₽?"
            )
            await query.edit_message_reply_markup(reply_markup=markup)
        except Exception:
            await context.bot.send_message(
                chat.id,
                "Добавить коммуникации (газ, свет, вода, канализация) за 500 000 ₽?",
                reply_markup=markup
            )
        return

    # ==== КАЛЬКУЛЯТОР: коммуникации + контакты / расчёт ====
    if data.startswith("cost_comm:"):
        choice = data.split(":", 1)[1]
        cost = context.user_data.get("cost_ctx", {})
        cost["comm"] = (choice == "yes")
        context.user_data["cost_ctx"] = cost

        has_contacts = context.user_data.get("has_contacts", False)

        if not has_contacts:
            context.user_data["state"] = "COST_WAIT_CONTACTS"
            try:
                await query.edit_message_text(
                    "Чтобы показать ориентировочный расчёт, напишите, пожалуйста, как к вам обращаться "
                    "и номер телефона одним сообщением (например: «Иван, +7 999 123-45-67»)."
                )
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                await context.bot.send_message(
                    chat.id,
                    "Чтобы показать ориентировочный расчёт, напишите, пожалуйста, как к вам обращаться "
                    "и номер телефона одним сообщением (например: «Иван, +7 999 123-45-67»)."
                )
            return

        # контакты уже есть — сразу показываем расчёт
        result_text = build_cost_result_text(cost)
        await context.bot.send_message(chat.id, result_text, parse_mode="HTML")

        await notify_manager_about_cost(
            context=context,
            chat_id=chat.id,
            username=query.from_user.username if query.from_user else None,
            cost=cost,
            contact_info=context.user_data.get("contact_info"),
        )
        context.user_data["state"] = "MAIN"
        return

    # ==== Локации ====
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
        context.user_data["state"] = "LOC_LIST"
        return

    # ==== Проекты ====
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
        context.user_data["state"] = "PROJ_LIST"
        return

    # ==== В меню ====
    if data == "back_to_menu":
        _reset_user_data_keep_flags(context)
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