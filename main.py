import asyncio
import logging
import os
import sys
from datetime import datetime

# Библиотеки Aiogram
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Библиотеки для AI и конфига
from dotenv import load_dotenv
from groq import AsyncGroq

# --- ЗАГРУЗКА КОНФИГУРАЦИИ ---
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Проверка наличия токенов (чтобы бот не упал молча)
if not TOKEN or not GROQ_API_KEY:
    sys.exit("ОШИБКА: Не заданы переменные окружения BOT_TOKEN или GROQ_API_KEY")

# Инициализация
bot = Bot(token=TOKEN)
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# Логирование (обязательно stream=sys.stdout для Render)
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- ДАННЫЕ И КОНСТАНТЫ ---

# Список знаков зодиака для кнопок
ZODIAC_SIGNS = [
    "♈ Овен", "♉ Телец", "♊ Близнецы", "♋ Рак",
    "♌ Лев", "♍ Дева", "♎ Весы", "♏ Скорпион",
    "♐ Стрелец", "♑ Козерог", "♒ Водолей", "♓ Рыбы"
]

# Системный промпт (Личность AI)
MYSTIC_PERSONA = (
    "Ты — мудрый Мистик, Астролог и Нумеролог. "
    "Твой стиль речи — возвышенный, таинственный, но добрый. "
    "Используй термины: 'энергия', 'вибрации', 'карма', 'вселенная'. "
    "Твоя задача — составлять гороскопы и давать мистические советы. "
    "Структурируй ответы абзацами. Используй эмодзи для атмосферы."
)

# --- МАШИНА СОСТОЯНИЙ (FSM) ---

class HoroscopeStates(StatesGroup):
    waiting_for_sign_day = State()
    waiting_for_sign_week = State()

class NumerologyStates(StatesGroup):
    waiting_for_birthdate = State()

# --- КЛАВИАТУРЫ ---

def get_main_kb():
    buttons = [
        [KeyboardButton(text="🔮 Гороскоп на сегодня")],
        [KeyboardButton(text="🌟 Гороскоп на неделю")],
        [KeyboardButton(text="🔢 Нумерология (дата рождения)")],
        [KeyboardButton(text="🙏 Вопрос Оракулу")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_zodiac_kb():
    """Клавиатура с 4 колонками"""
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

# --- ЛОГИКА AI ---

async def ask_mystic(user_prompt: str) -> str:
    """Отправляет запрос в Groq API"""
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": MYSTIC_PERSONA},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.1-70b-versatile", # Или llama-3.1-8b-instant
            temperature=0.8,
            max_tokens=1024,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка Groq API: {e}")
        return "⚠️ Каналы связи с космосом временно перекрыты. Попробуй позже."

# --- ХЭНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✨ **Приветствую, путник...**\n\n"
        "Я помогу тебе обрести гармонию через знания звезд и цифр.\n"
        "Выбирай, что тебя интересует:",
        reply_markup=get_main_kb(),
        parse_mode="Markdown"
    )

# --- ГОРОСКОПЫ ---

@dp.message(F.text == "🔮 Гороскоп на сегодня")
async def horoscope_today(message: types.Message, state: FSMContext):
    await state.set_state(HoroscopeStates.waiting_for_sign_day)
    await message.answer("🌌 Выбери свой знак зодиака для прогноза на сегодня:", reply_markup=get_zodiac_kb())

@dp.message(F.text == "🌟 Гороскоп на неделю")
async def horoscope_week(message: types.Message, state: FSMContext):
    await state.set_state(HoroscopeStates.waiting_for_sign_week)
    await message.answer("🌌 Выбери свой знак зодиака для прогноза на неделю:", reply_markup=get_zodiac_kb())

# Обработка выбора знака для "Дня"
@dp.message(HoroscopeStates.waiting_for_sign_day, F.text.in_(ZODIAC_SIGNS))
async def process_sign_day(message: types.Message, state: FSMContext):
    sign = message.text
    today = datetime.now().strftime("%d %B %Y")
    
    prompt = (
        f"Сегодня {today}. Составь красивый и мистический гороскоп на СЕГОДНЯ для знака {sign}. "
        f"Расскажи об энергии дня, советах и возможных ловушках."
    )
    
    status = await message.answer("🔮 Взглядаю на звездную карту...")
    response = await ask_mystic(prompt)
    
    await status.delete()
    await message.answer(response, reply_markup=get_main_kb())
    await state.clear()

# Обработка выбора знака для "Недели"
@dp.message(HoroscopeStates.waiting_for_sign_week, F.text.in_(ZODIAC_SIGNS))
async def process_sign_week(message: types.Message, state: FSMContext):
    sign = message.text
    
    prompt = (
        f"Составь детальный гороскоп на БЛИЖАЙШУЮ НЕДЕЛЮ для знака {sign}. "
        f"Оформи его по дням или выдели главные тренды недели."
    )
    
    status = await message.answer("🔮 Читаю лунные фазы...")
    response = await ask_mystic(prompt)
    
    await status.delete()
    await message.answer(response, reply_markup=get_main_kb())
    await state.clear()

# --- НУМЕРОЛОГИЯ ---

@dp.message(F.text == "🔢 Нумерология (дата рождения)")
async def numerology_start(message: types.Message, state: FSMContext):
    await state.set_state(NumerologyStates.waiting_for_birthdate)
    await message.answer(
        "📅 Введи дату своего рождения в формате ДД.ММ.ГГГГ\n"
        "Например: 15.05.1990",
        reply_markup=get_cancel_kb()
    )

@dp.message(NumerologyStates.waiting_for_birthdate)
async def numerology_process(message: types.Message, state: FSMContext):
    birthdate = message.text
    
    # Простая проверка на ввод чисел
    if not any(char.isdigit() for char in birthdate):
        return await message.answer("Пожалуйста, используй цифры для даты.")
        
    if "отмена" in birthdate.lower():
        await state.clear()
        return await message.answer("Возвращаемся...", reply_markup=get_main_kb())

    prompt = (
        f"Проведи нумерологический разбор даты рождения: {birthdate}. "
        f"Расскажи о числе судьбы, главных чертах характера и кармических задачах."
    )
    
    status = await message.answer("🔢 Считаю вибрации вселенной...")
    response = await ask_mystic(prompt)
    
    await status.delete()
    await message.answer(response, reply_markup=get_main_kb())
    await state.clear()

# --- ВОПРОС ОРАКУЛУ ---

@dp.message(F.text == "🙏 Вопрос Оракулу")
async def oracle_mode(message: types.Message):
    await message.answer(
        "Спроси меня о том, что тебя тревожит. Я отвечу мудростью звезд и карт.",
        reply_markup=get_cancel_kb()
    )

# Общий обработчик текста (для Оракула и отмены)
@dp.message()
async def general_text_handler(message: types.Message):
    text = message.text.lower()
    
    # Обработка отмены в любом состоянии
    if text == "🚫 отмена" or text == "отмена":
        # Сбрасываем состояние (если есть)
        current_state = await dp.current_state(user=message.from_user.id).get_state()
        if current_state:
            await dp.current_state(user=message.from_user.id).clear()
        
        await message.answer("Действие отменено.", reply_markup=get_main_kb())
        return

    # Если мы не в режиме гороскопа/нумерологии и не отмена — считаем это вопросом Оракулу
    # (Aiogram 3.x позволяет проверить состояние, но для простоты ловим все, что не попало в кнопки)
    # Но лучше проверить, активны ли стейты, чтобы не спамить Оракулом во время ввода даты.
    
    # Проверяем, есть ли активное состояние
    from aiogram.fsm.storage.memory import MemoryStorage
    # Простая проверка: если это не кнопки меню и мы не в явном стейте, считаем вопросом.
    # Однако FSM перехватывает сообщения в стейтах, поэтому сюда попадут только свободные сообщения.
    
    prompt = f"Пользователь спрашивает: '{message.text}'. Дай мистический, глубокий и полезный ответ."
    status = await message.answer("🧘‍♂️ Вхожу в транс...")
    response = await ask_mystic(prompt)
    
    await status.delete()
    await message.answer(response, reply_markup=get_main_kb())

# --- ЗАПУСК ---

async def main():
    # Удаляем вебхуки перед запуском поллинга
    await bot.delete_webhook(drop_pending_updates=True)
    print("Mystic Bot started successfully.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
