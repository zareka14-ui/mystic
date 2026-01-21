import asyncio
import logging
import os
import sys
import json
import random
import urllib.parse
from datetime import datetime

# Aiogram
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Web Server (для Render/Keep-alive)
from aiohttp import web

# AI и конфиг
from dotenv import load_dotenv
from groq import AsyncGroq

# --- КОНФИГУРАЦИЯ ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PORT = int(os.getenv("PORT", 8080))

if not TOKEN or not GROQ_API_KEY:
    sys.exit("ОШИБКА: Не заданы BOT_TOKEN или GROQ_API_KEY в .env")

bot = Bot(token=TOKEN)
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- БАЗА ДАННЫХ (JSON) ---
DB_FILE = "users_data.json"

def load_db():
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception: return {}
    return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_user_birthdate(user_id):
    return load_db().get(str(user_id), {}).get("birthdate")

def set_user_birthdate(user_id, birthdate):
    db = load_db()
    if str(user_id) not in db: db[str(user_id)] = {}
    db[str(user_id)]["birthdate"] = birthdate
    save_db(db)

# --- ДАННЫЕ И ПЕРСОНА ---
ZODIAC_SIGNS = [
    "♈ Овен", "♉ Телец", "♊ Близнецы", "♋ Рак",
    "♌ Лев", "♍ Дева", "♎ Весы", "♏ Скорпион",
    "♐ Стрелец", "♑ Козерог", "♒ Водолей", "♓ Рыбы"
]

ROD_CARDS = [
    "Алтарь Предков", "Родовой Дуб", "Прадед", "Праматерь", "Семейный Очаг",
    "Печать Рода", "Нить Судьбы", "Защитник", "Материнское Благословение",
    "Отцовский Щит", "Древо Жизни", "Кострище", "Дом Духа", "Зов Крови",
    "Путь Воина", "Мудрость Старца", "Хранитель Порога", "Ключ от Тайны",
    "Семейный Сундук", "Связь Поколений", "Дар Земли", "Сила Стихий",
    "Зеркало Рода", "Подарок Вселенной", "Кармический Узел", "Свет"
]

MYSTIC_PERSONA = (
    "Ты — Хранитель Звездных Архивов, мудрый эзотерик. Твой стиль общения: мистический, "
    "глубокий, но вдохновляющий. Используй метафоры. \n\n"
    "ПРАВИЛА ОТВЕТА:\n"
    "1. Структурируй ответ через Markdown: используй **жирный текст** для акцентов.\n"
    "2. Дели текст на абзацы. \n"
    "3. В прогнозе обязательно сочетай влияние знака зодиака, чисел и карты Рода.\n"
    "4. В САМОМ КОНЦЕ ответа всегда добавляй строку: 'IMAGE_PROMPT: [краткое описание карты на английском языке для генерации картинки]'. "
    "Описание должно быть в стиле фэнтези, мистики, таро."
)

class HoroscopeStates(StatesGroup):
    waiting_for_sign_day = State()
    waiting_for_sign_week = State()

class NumerologyStates(StatesGroup):
    waiting_for_birthdate = State()

class ProfileStates(StatesGroup):
    waiting_for_new_birthdate = State()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def generate_image_url(prompt_text):
    clean_prompt = prompt_text.replace("IMAGE_PROMPT:", "").strip()
    full_prompt = f"mystical tarot card, esoteric symbol, {clean_prompt}, digital art, highly detailed, magical glow"
    encoded = urllib.parse.quote(full_prompt)
    seed = random.randint(1, 99999)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&seed={seed}&nologo=true"

def parse_date(date_str):
    try: return datetime.strptime(date_str, "%d.%m.%Y")
    except: return None

def reduce_number(num):
    while num > 9 and num not in [11, 22, 33]:
        num = sum(int(d) for d in str(num))
    return num

def calculate_universal_day(date_obj):
    return reduce_number(date_obj.day + date_obj.month + date_obj.year)

def calculate_personal_day(today_date, birth_date):
    u_day = calculate_universal_day(today_date)
    p_day = u_day + birth_date.month + birth_date.day
    return reduce_number(p_day)

async def ask_mystic(user_prompt: str) -> str:
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": MYSTIC_PERSONA},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.8,
            max_tokens=1500,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Groq Error: {e}")
        return "⚠️ Вибрации мироздания нарушены. Попробуй позже."

# --- КЛАВИАТУРЫ ---
def get_main_kb():
    buttons = [
        [KeyboardButton(text="🔮 Комплексный прогноз на день")],
        [KeyboardButton(text="🌟 Гороскоп на неделю")],
        [KeyboardButton(text="🔢 Моя нумерология")],
        [KeyboardButton(text="🎂 Мой профиль / Дата рождения")],
        [KeyboardButton(text="🙏 Вопрос Оракулу")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_zodiac_kb():
    keyboard = []
    row = []
    for sign in ZODIAC_SIGNS:
        row.append(KeyboardButton(text=sign))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    keyboard.append([KeyboardButton(text="🚫 Отмена")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚫 Отмена")]], resize_keyboard=True)

# --- ХЭНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✨ Приветствую, Искатель. Я — Оракул Рода.\n\n"
        "Для точных предсказаний укажи дату рождения в Профиле.",
        reply_markup=get_main_kb()
    )

@dp.message(F.text == "🚫 Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Возвращаемся к истокам.", reply_markup=get_main_kb())

@dp.message(F.text == "🎂 Мой профиль / Дата рождения")
async def profile_handler(message: types.Message, state: FSMContext):
    bday = get_user_birthdate(message.from_user.id)
    await state.set_state(ProfileStates.waiting_for_new_birthdate)
    text = f"Твоя дата в свитках: **{bday}**\nХочешь изменить? Введи ДД.ММ.ГГГГ" if bday else "Введи дату своего рождения (ДД.ММ.ГГГГ):"
    await message.answer(text, reply_markup=get_cancel_kb(), parse_mode="Markdown")

@dp.message(ProfileStates.waiting_for_new_birthdate)
async def set_birthdate(message: types.Message, state: FSMContext):
    date_obj = parse_date(message.text)
    if date_obj:
        set_user_birthdate(message.from_user.id, date_obj.strftime("%d.%m.%Y"))
        await state.clear()
        await message.answer("✅ Твоя судьба зафиксирована в звездах.", reply_markup=get_main_kb())
    else:
        await message.answer("Неверный формат. Попробуй еще раз: ДД.ММ.ГГГГ")

@dp.message(F.text == "🔮 Комплексный прогноз на день")
async def complex_forecast_start(message: types.Message, state: FSMContext):
    await state.set_state(HoroscopeStates.waiting_for_sign_day)
    await message.answer("🌌 Выбери свой знак зодиака:", reply_markup=get_zodiac_kb())

@dp.message(HoroscopeStates.waiting_for_sign_day, F.text.in_(ZODIAC_SIGNS))
async def process_complex_forecast(message: types.Message, state: FSMContext):
    sign = message.text
    now = datetime.now()
    card = random.choice(ROD_CARDS)
    bday_str = get_user_birthdate(message.from_user.id)
    
    status_msg = await message.answer("🧘 Соединяюсь с информационным полем...")
    
    p_info = ""
    if bday_str:
        bday_obj = parse_date(bday_str)
        if bday_obj:
            p_num = calculate_personal_day(now, bday_obj)
            p_info = f"Личное число дня пользователя: {p_num}."

    prompt = (
        f"Прогноз на сегодня {now.strftime('%d.%m.%Y')}. Знак пользователя: {sign}. "
        f"Выпавшая карта Рода: {card}. {p_info} \n"
        "Дай развернутый прогноз и опиши значение карты."
    )
    
    response = await ask_mystic(prompt)
    
    # Извлекаем промпт для картинки и чистим основной текст
    final_text = response
    img_url = generate_image_url(card) # Фолбэк на название карты
    
    if "IMAGE_PROMPT:" in response:
        parts = response.split("IMAGE_PROMPT:")
        final_text = parts[0].strip()
        img_url = generate_image_url(parts[1].strip())

    await status_msg.delete()
    
    try:
        await message.answer_photo(photo=img_url, caption=f"🎴 Карта дня: **{card}**", parse_mode="Markdown")
    except:
        await message.answer(f"🎴 Карта дня: **{card}**", parse_mode="Markdown")

    await message.answer(final_text, reply_markup=get_main_kb(), parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "🌟 Гороскоп на неделю")
async def horoscope_week(message: types.Message, state: FSMContext):
    await state.set_state(HoroscopeStates.waiting_for_sign_week)
    await message.answer("🌌 Выбери знак для недельного прогноза:", reply_markup=get_zodiac_kb())

@dp.message(HoroscopeStates.waiting_for_sign_week, F.text.in_(ZODIAC_SIGNS))
async def process_sign_week(message: types.Message, state: FSMContext):
    status = await message.answer("🌙 Считываю ритмы планет...")
    response = await ask_mystic(f"Прогноз на неделю для знака {message.text}.")
    # Очистка от технического промпта для картинки, если он там есть
    clean_text = response.split("IMAGE_PROMPT:")[0]
    await status.delete()
    await message.answer(clean_text, reply_markup=get_main_kb(), parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "🔢 Моя нумерология")
async def numerology_start(message: types.Message, state: FSMContext):
    bday = get_user_birthdate(message.from_user.id)
    if not bday:
        await state.set_state(NumerologyStates.waiting_for_birthdate)
        await message.answer("Для этого ритуала нужна твоя дата рождения (ДД.ММ.ГГГГ):", reply_markup=get_cancel_kb())
    else:
        status = await message.answer("🔢 Раскладываю числа судьбы...")
        response = await ask_mystic(f"Сделай нумерологический разбор даты рождения {bday}.")
        await status.delete()
        await message.answer(response.split("IMAGE_PROMPT:")[0], parse_mode="Markdown")

@dp.message(NumerologyStates.waiting_for_birthdate)
async def numerology_process(message: types.Message, state: FSMContext):
    date_obj = parse_date(message.text)
    if date_obj:
        set_user_birthdate(message.from_user.id, date_obj.strftime("%d.%m.%Y"))
        status = await message.answer("🔢 Раскладываю числа...")
        response = await ask_mystic(f"Сделай нумерологический разбор даты рождения {message.text}.")
        await state.clear()
        await status.delete()
        await message.answer(response.split("IMAGE_PROMPT:")[0], reply_markup=get_main_kb(), parse_mode="Markdown")
    else:
        await message.answer("Неверная дата.")

@dp.message(F.text == "🙏 Вопрос Оракулу")
async def oracle_mode(message: types.Message):
    await message.answer("Сформулируй свой вопрос к Вселенной и отправь его мне...", reply_markup=get_cancel_kb())

@dp.message()
async def general_text_handler(message: types.Message):
    status = await message.answer("🔮 Хранитель слушает...")
    response = await ask_mystic(f"Ответь на вопрос: {message.text}")
    await status.delete()
    await message.answer(response.split("IMAGE_PROMPT:")[0], parse_mode="Markdown")

# --- ЗАПУСК ---
async def handle(request):
    return web.Response(text="Oracle is active")

async def main():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
