import asyncio
import logging
import os
import sys
import json
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv
from groq import AsyncGroq

# --- КОНФИГУРАЦИЯ ---
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TOKEN or not GROQ_API_KEY:
    sys.exit("ОШИБКА: Не заданы переменные окружения BOT_TOKEN или GROQ_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- ФАЙЛОВАЯ БАЗА ДАННЫХ (JSON) ---
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

# --- ДАННЫЕ И КОНСТАНТЫ ---

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
    "Ты — эзотерик-профессионал. Ты владеешь астрологией, нумерологией и картами Рода. "
    "Ты различаешь Универсальное число дня и Личное число дня человека. "
    "Твой стиль — глубокий, утешительный и ведический."
)

class HoroscopeStates(StatesGroup):
    waiting_for_sign_day = State()
    waiting_for_sign_week = State()

class NumerologyStates(StatesGroup):
    waiting_for_birthdate = State()

class ProfileStates(StatesGroup):
    waiting_for_new_birthdate = State()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

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
    if row:
        keyboard.append(row)
    keyboard.append([KeyboardButton(text="🚫 Отмена")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚫 Отмена")]], 
        resize_keyboard=True
    )

def parse_date(date_str):
    """Пытается распарсить ДД.ММ.ГГГГ"""
    try:
        # Простая проверка формата
        parts = date_str.split('.')
        if len(parts) == 3:
            return datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        pass
    return None

def reduce_number(num):
    """Сворачивает число до однозначного (или 11, 22, 33)"""
    while num > 9 and num not in [11, 22, 33]:
        num = sum(int(d) for d in str(num))
    return num

def calculate_universal_day(date_obj):
    """Универсальное число дня (для всех)"""
    total = date_obj.day + date_obj.month + date_obj.year
    return reduce_number(total)

def calculate_personal_day(today_date, birth_date):
    """
    Личное число дня = Универсальный день + Месяц рождения + День рождения
    """
    u_day = calculate_universal_day(today_date)
    p_day = u_day + birth_date.month + birth_date.day
    return reduce_number(p_day)

# --- AI ---

async def ask_mystic(user_prompt: str) -> str:
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": MYSTIC_PERSONA},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.1-70b-versatile",
            temperature=0.8,
            max_tokens=1200,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка Groq API: {e}")
        return "⚠️ Связь с мирами прервана."

# --- ХЭНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    birthdate = get_user_birthdate(message.from_user.id)
    if birthdate:
        text = f"✨ **С возвращением!**\n\nЯ помню твою дату рождения: *{birthdate}*.\nГотов заглянуть в будущее?"
    else:
        text = (
            "✨ **Приветствую, путник...**\n\n"
            "Чтобы я мог составлять точные Личные гороскопы и нумерологические прогнозы, "
            "мне нужна твоя дата рождения.\n\n"
            "Нажми кнопку **🎂 Мой профиль**, чтобы её указать."
        )
    await message.answer(text, reply_markup=get_main_kb(), parse_mode="Markdown")

# --- ПРОФИЛЬ ---

@dp.message(F.text == "🎂 Мой профиль / Дата рождения")
async def profile_handler(message: types.Message, state: FSMContext):
    birthdate = get_user_birthdate(message.from_user.id)
    if birthdate:
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✏️ Изменить дату")],
                [KeyboardButton(text="🚫 Отмена")]
            ], resize_keyboard=True
        )
        await message.answer(f"Текущая дата рождения: *{birthdate}*", reply_markup=kb, parse_mode="Markdown")
        await state.set_state(ProfileStates.waiting_for_new_birthdate)
    else:
        await message.answer(
            "Введи дату своего рождения в формате ДД.ММ.ГГГГ\nНапример: 15.05.1990",
            reply_markup=get_cancel_kb()
        )
        await state.set_state(ProfileStates.waiting_for_new_birthdate)

@dp.message(ProfileStates.waiting_for_new_birthdate)
async def set_birthdate(message: types.Message, state: FSMContext):
    if message.text.lower() == "отмена" or message.text == "🚫 отмена":
        await state.clear()
        return await message.answer("Ок.", reply_markup=get_main_kb())

    if message.text == "✏️ Изменить дату":
        return await message.answer("Введи новую дату (ДД.ММ.ГГГГ):")

    date_obj = parse_date(message.text)
    if date_obj:
        date_str = date_obj.strftime("%d.%m.%Y")
        set_user_birthdate(message.from_user.id, date_str)
        await state.clear()
        await message.answer(
            f"✅ Дата рождения сохранена: *{date_str}*\nТеперь прогнозы станут точнее!",
            reply_markup=get_main_kb(),
            parse_mode="Markdown"
        )
    else:
        await message.answer("Неверный формат. Попробуй ДД.ММ.ГГГГ")

# --- КОМПЛЕКСНЫЙ ПРОГНОЗ ---

@dp.message(F.text == "🔮 Комплексный прогноз на день")
async def complex_forecast_start(message: types.Message, state: FSMContext):
    await state.set_state(HoroscopeStates.waiting_for_sign_day)
    await message.answer("🌌 Выбери свой знак зодиака:", reply_markup=get_zodiac_kb())

@dp.message(HoroscopeStates.waiting_for_sign_day, F.text.in_(ZODIAC_SIGNS))
async def process_complex_forecast(message: types.Message, state: FSMContext):
    sign = message.text
    user_id = message.from_user.id
    now = datetime.now()
    
    # 1. Универсальное число дня
    u_num = calculate_universal_day(now)
    
    # 2. Проверяем дату рождения для Личного числа
    bday_str = get_user_birthdate(user_id)
    personal_num = None
    personal_text = ""
    
    if bday_str:
        bday_obj = parse_date(bday_str)
        if bday_obj:
            personal_num = calculate_personal_day(now, bday_obj)
            personal_text = f"Твое Личное число дня: {personal_num} (Рассчитано от твоей даты рождения)."

    # 3. Карта Рода
    random_card = random.choice(ROD_CARDS)
    
    # 4. Промпт
    prompt = (
        f"Сегодня {now.strftime('%d %B %Y')}. Знак: {sign}. "
        f"Универсальное число дня: {u_num}. {personal_text} "
        f"Выпавшая Карта Рода: '{random_card}'.\n\n"
        
        f"Составь прогноз:\n"
        f"1. **🌟 АСТРОЛОГИЯ**: Для {sign}.\n"
        f"2. **🔢 НУМЕРОЛОГИЯ**: Объясни значение Универсального числа {u_num}. "
        f"{'Если есть Личное число (' + str(personal_num) + '), объясни, как оно влияет именно на этого человека, в чем разница с общим днем.' if personal_num else 'Рекомендую указать дату рождения в профиле для точного личного расчета.'}\n"
        f"3. **🃏 ПОСЛАНИЕ РОДА**: Интерпретация карты '{random_card}'."
    )
    
    status = await message.answer("🔮 Совершаю обряд...")
    response = await ask_mystic(prompt)
    
    await status.delete()
    await message.answer(response, reply_markup=get_main_kb(), parse_mode="Markdown")
    await state.clear()

# --- ГОРОСКОП НА НЕДЕЛЮ ---

@dp.message(F.text == "🌟 Гороскоп на неделю")
async def horoscope_week(message: types.Message, state: FSMContext):
    await state.set_state(HoroscopeStates.waiting_for_sign_week)
    await message.answer("🌌 Выбери свой знак:", reply_markup=get_zodiac_kb())

@dp.message(HoroscopeStates.waiting_for_sign_week, F.text.in_(ZODIAC_SIGNS))
async def process_sign_week(message: types.Message, state: FSMContext):
    sign = message.text
    prompt = f"Прогноз на неделю для {sign}."
    status = await message.answer("🔮 Смотрю в будущее...")
    response = await ask_mystic(prompt)
    await status.delete()
    await message.answer(response, reply_markup=get_main_kb())
    await state.clear()

# --- НУМЕРОЛОГИЯ ---

@dp.message(F.text == "🔢 Моя нумерология")
async def numerology_start(message: types.Message, state: FSMContext):
    bday = get_user_birthdate(message.from_user.id)
    if bday:
        # Если дата есть, сразу раскладываем
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔄 Рассчитать для другой даты")], [KeyboardButton(text="🚫 Отмена")]],
            resize_keyboard=True
        )
        await message.answer(f"Я использую твою сохраненную дату: *{bday}*. Готово?", reply_markup=kb, parse_mode="Markdown")
        # Упростим логику: если нажал Рассчитать -> стейт, если Отмена -> clear. 
        # Для простоты тут просто перейдем к обработке, который будет использовать сохраненную дату, если не сказано иного
        await state.set_state(NumerologyStates.waiting_for_birthdate)
    else:
        await message.answer("📅 Введи дату рождения (ДД.ММ.ГГГГ):", reply_markup=get_cancel_kb())
        await state.set_state(NumerologyStates.waiting_for_birthdate)

@dp.message(NumerologyStates.waiting_for_birthdate)
async def numerology_process(message: types.Message, state: FSMContext):
    text = message.text.lower()
    
    if text == "отмена" or text == "🚫 отмена":
        await state.clear()
        return await message.answer("Ок.", reply_markup=get_main_kb())
    
    # Если нажал "Рассчитать для другой даты" или просто ввел дату
    target_date_str = message.text
    if text == "🔄 рассчитать для другой даты":
        return await message.answer("Введи новую дату:")

    # Проверяем, это дата или кнопка повторного использования
    if "рассчитать" not in text:
        date_obj = parse_date(target_date_str)
        if not date_obj:
            # Если парс не удался, но у пользователя ЕСТЬ сохраненная дата, может он просто нажал что-то не то?
            # Для надежности: если введено не дата, ошибка.
            return await message.answer("Неверный формат даты. Используй ДД.ММ.ГГГГ")
        
        bday_to_use = date_obj.strftime("%d.%m.%Y")
    else:
        # Если это кнопка "для другой даты" (но мы уже выше вернули), сюда не попадем.
        # Здесь логика: если пользователь ввел дату - используем её.
        # Если пользователь нажал "Рассчитать" в контексте, когда дата уже есть в базе... 
        # Хм, давай упростим: если текст - это кнопка "Рассчитать для другой даты", мы выше просили ввести. 
        # Значит сюда приходит только ДАТА.
        bday_to_use = target_date_str # но нужно распарсить
        date_obj = parse_date(bday_to_use)
        if date_obj:
            bday_to_use = date_obj.strftime("%d.%m.%Y")

    # Используем последнюю успешно распаршенную дату
    if not date_obj: 
        # Последняя попытка: берем из БД, если пользователь просто ткнул "Ок" или отправил пустое? 
        # В FSM так нельзя.
        # Если дата не распарсилась, выходим.
        return await message.answer("Введите корректную дату ДД.ММ.ГГГГ")

    prompt = f"Глубокий разбор даты рождения: {bday_to_use}. Число души, судьбы, кармические хвосты."
    status = await message.answer("🔢 Считаю...")
    response = await ask_mystic(prompt)
    await status.delete()
    await message.answer(response, reply_markup=get_main_kb())
    await state.clear()

# --- ОРАКУЛ ---

@dp.message(F.text == "🙏 Вопрос Оракулу")
async def oracle_mode(message: types.Message):
    await message.answer("Спроси меня...", reply_markup=get_cancel_kb())

@dp.message()
async def general_text_handler(message: types.Message):
    if message.text.lower() in ["отмена", "🚫 отмена"]:
        return await message.answer("Ок", reply_markup=get_main_kb())
    
    prompt = f"Вопрос: '{message.text}'. Дай мистический ответ."
    status = await message.answer("🧘‍♂️...")
    response = await ask_mystic(prompt)
    await status.delete()
    await message.answer(response, reply_markup=get_main_kb())

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("Mystic Bot started.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
