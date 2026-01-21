import asyncio
import logging
import os
import sys
import json
import random
from datetime import datetime

# Aiogram
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Web Server (для Render)
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
    sys.exit("ОШИБКА: Не заданы переменные окружения BOT_TOKEN или GROQ_API_KEY")

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
    except Exception as e:
        logging.error(f"Ошибка чтения БД: {e}")
    return {}

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Ошибка записи БД: {e}")

def get_user_birthdate(user_id):
    db = load_db()
    return db.get(str(user_id), {}).get("birthdate")

def set_user_birthdate(user_id, birthdate):
    db = load_db()
    if str(user_id) not in db:
        db[str(user_id)] = {}
    db[str(user_id)]["birthdate"] = birthdate
    save_db(db)

# --- ДАННЫЕ ---
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
    "Ты — эзотерик. Астрология, нумерология, карты Рода. "
    "Стиль: глубокий, мистический."
)

class HoroscopeStates(StatesGroup):
    waiting_for_sign_day = State()
    waiting_for_sign_week = State()

class NumerologyStates(StatesGroup):
    waiting_for_birthdate = State()

class ProfileStates(StatesGroup):
    waiting_for_new_birthdate = State()

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

def parse_date(date_str):
    try:
        if '.' in date_str and len(date_str.split('.')) == 3:
            return datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        pass
    return None

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
            max_tokens=1200,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка API: {e}")
        return "⚠️ Связь с мирами прервана."

# --- ХЭНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    birthdate = get_user_birthdate(message.from_user.id)
    text = f"✨ С возвращением! Дата: *{birthdate}*" if birthdate else "✨ Введи дату рождения для точности."
    await message.answer(text, reply_markup=get_main_kb(), parse_mode="Markdown")

@dp.message(F.text == "🎂 Мой профиль / Дата рождения")
async def profile_handler(message: types.Message, state: FSMContext):
    bday = get_user_birthdate(message.from_user.id)
    await state.set_state(ProfileStates.waiting_for_new_birthdate)
    if bday:
        await message.answer(f"Дата: *{bday}*. Введи новую или 'Отмена'", reply_markup=get_cancel_kb(), parse_mode="Markdown")
    else:
        await message.answer("Введи дату (ДД.ММ.ГГГГ):", reply_markup=get_cancel_kb())

@dp.message(ProfileStates.waiting_for_new_birthdate)
async def set_birthdate(message: types.Message, state: FSMContext):
    if "отмена" in message.text.lower():
        await state.clear()
        return await message.answer("Ок.", reply_markup=get_main_kb())
    
    date_obj = parse_date(message.text)
    if date_obj:
        set_user_birthdate(message.from_user.id, date_obj.strftime("%d.%m.%Y"))
        await state.clear()
        await message.answer("✅ Дата сохранена!", reply_markup=get_main_kb())
    else:
        await message.answer("Неверный формат. ДД.ММ.ГГГГ")

@dp.message(F.text == "🔮 Комплексный прогноз на день")
async def complex_forecast_start(message: types.Message, state: FSMContext):
    await state.set_state(HoroscopeStates.waiting_for_sign_day)
    await message.answer("🌌 Выбери знак:", reply_markup=get_zodiac_kb())

@dp.message(HoroscopeStates.waiting_for_sign_day, F.text.in_(ZODIAC_SIGNS))
async def process_complex_forecast(message: types.Message, state: FSMContext):
    sign = message.text
    now = datetime.now()
    u_num = calculate_universal_day(now)
    random_card = random.choice(ROD_CARDS)
    
    bday_str = get_user_birthdate(message.from_user.id)
    p_text = ""
    if bday_str:
        bday_obj = parse_date(bday_str)
        if bday_obj:
            p_num = calculate_personal_day(now, bday_obj)
            p_text = f"Твое Личное число: {p_num}."

    prompt = f"Сегодня {now.strftime('%d %B %Y')}. Знак: {sign}. Ун. число: {u_num}. {p_text} Карта: '{random_card}'. Сделай 3 блока: Астро, Нумеро, РОД."
    
    status = await message.answer("🔮 Гадаю...")
    response = await ask_mystic(prompt)
    await status.delete()
    await message.answer(response, reply_markup=get_main_kb(), parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "🌟 Гороскоп на неделю")
async def horoscope_week(message: types.Message, state: FSMContext):
    await state.set_state(HoroscopeStates.waiting_for_sign_week)
    await message.answer("🌌 Выбери знак:", reply_markup=get_zodiac_kb())

@dp.message(HoroscopeStates.waiting_for_sign_week, F.text.in_(ZODIAC_SIGNS))
async def process_sign_week(message: types.Message, state: FSMContext):
    status = await message.answer("🔮...")
    response = await ask_mystic(f"Прогноз на неделю для {message.text}.")
    await status.delete()
    await message.answer(response, reply_markup=get_main_kb())
    await state.clear()

@dp.message(F.text == "🔢 Моя нумерология")
async def numerology_start(message: types.Message, state: FSMContext):
    bday = get_user_birthdate(message.from_user.id)
    await state.set_state(NumerologyStates.waiting_for_birthdate)
    if bday:
        await message.answer(f"Дата: {bday}. Отправь 'ОК' или новую дату:", reply_markup=get_cancel_kb())
    else:
        await message.answer("Введи дату (ДД.ММ.ГГГГ):", reply_markup=get_cancel_kb())

@dp.message(NumerologyStates.waiting_for_birthdate)
async def numerology_process(message: types.Message, state: FSMContext):
    if "отмена" in message.text.lower():
        await state.clear()
        return await message.answer("Ок.", reply_markup=get_main_kb())
    
    date_obj = parse_date(message.text)
    if message.text.lower() in ['ок', 'окей', 'yes']:
        bday_str = get_user_birthdate(message.from_user.id)
        date_obj = parse_date(bday_str) if bday_str else None

    if date_obj:
        status = await message.answer("🔢...")
        response = await ask_mystic(f"Разбор даты: {date_obj.strftime('%d.%m.%Y')}.")
        await status.delete()
        await message.answer(response, reply_markup=get_main_kb())
        await state.clear()
    else:
        await message.answer("Неверная дата.")

@dp.message(F.text == "🙏 Вопрос Оракулу")
async def oracle_mode(message: types.Message):
    await message.answer("Спроси...", reply_markup=get_cancel_kb())

@dp.message()
async def general_text_handler(message: types.Message):
    if "отмена" in message.text.lower():
        return await message.answer("Ок", reply_markup=get_main_kb())
    status = await message.answer("🧘‍♂️...")
    response = await ask_mystic(f"Вопрос: {message.text}")
    await status.delete()
    await message.answer(response, reply_markup=get_main_kb())

# --- ЗАПУСК WEB СЕРВЕРА + БОТА ---

async def handle(request):
    return web.Response(text="Bot is alive")

async def start_bot():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

async def main():
    app = web.Application()
    app.router.add_get('/', handle)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"Web server started on port {PORT}")
    
    await start_bot()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
