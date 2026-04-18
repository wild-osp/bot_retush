import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram import Router
import google.generativeai as genai
import os
from io import BytesIO

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")          # добавишь на bothost.ru в переменных окружения
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # тоже в переменных окружения

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-3.1-flash-image")  # Nano Banana 2

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Готовые промпты (кнопки)
PROMPTS = {
    "enhance": "Улучши качество фото, сделай чётче и красивее, но НЕ меняй лицо человека",
    "background": "Поменяй фон на современный минималистичный (белый/серый/природа), но НЕ меняй лицо и тело человека",
    "portrait": "Сделай профессиональный портрет: улучши кожу, освещение, но НЕ меняй черты лица",
    "color": "Сделай цвета ярче и естественнее, улучши качество, лицо не трогай",
    "style": "Преврати фото в стиль кино (кинематографичный свет), лицо оставь реалистичным",
    # Добавляй свои сюда ↓
    # "custom1": "Твой новый промпт...",
}

@router.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Привет! Отправь мне фото, и я его отретуширую через Gemini Nano Banana 2.\n"
        "Выбери действие после отправки фото:",
        reply_markup=types.ReplyKeyboardRemove()
    )

@router.message(F.photo)
async def handle_photo(message: types.Message):
    # Скачиваем фото
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    
    # Сохраняем в память
    user_data = {message.from_user.id: file_bytes.getvalue()}
    
    # Кнопки
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Улучшить качество", callback_data="enhance")],
        [InlineKeyboardButton(text="🌄 Изменить фон", callback_data="background")],
        [InlineKeyboardButton(text="🖼 Профессиональный портрет", callback_data="portrait")],
        [InlineKeyboardButton(text="🌈 Яркие цвета", callback_data="color")],
        [InlineKeyboardButton(text="🎥 Стиль кино", callback_data="style")],
        # Добавляй новые кнопки здесь
    ])
    
    await message.answer("✅ Фото получено! Выбери, что сделать:", reply_markup=keyboard)
    # Сохраняем фото во временном хранилище (в aiogram можно использовать bot.storage или простой dict)
    # Для простоты используем глобальный dict (для одного сервера нормально)
    global photo_storage
    if 'photo_storage' not in globals():
        photo_storage = {}
    photo_storage[message.from_user.id] = user_data[message.from_user.id]

@router.callback_query()
async def process_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in photo_storage:
        await callback.answer("Фото устарело, отправь заново")
        return
    
    prompt_key = callback.data
    prompt = PROMPTS.get(prompt_key, "Улучши фото")
    
    await callback.answer("🔄 Обрабатываю через Nano Banana 2...")
    
    photo_bytes = photo_storage[user_id]
    
    # Отправляем в Gemini Nano Banana 2
    response = model.generate_content(
        [
            prompt,  # твой промпт
            {"mime_type": "image/jpeg", "data": photo_bytes}
        ],
        generation_config={
            "temperature": 0.7,
        }
    )
    
    # Gemini возвращает сгенерированное изображение
    if response.parts and hasattr(response.parts[0], 'inline_data'):
        image_bytes = response.parts[0].inline_data.data
        await bot.send_photo(
            user_id,
            photo=types.BufferedInputFile(image_bytes, filename="retouched.jpg"),
            caption=f"✅ Готово! Промпт: {prompt}\n\nХочешь ещё что-то изменить? Отправь новое фото или нажми кнопку."
        )
    else:
        await bot.send_message(user_id, "❌ Не удалось обработать. Попробуй другой промпт.")
    
    # Удаляем старое фото из памяти
    del photo_storage[user_id]

dp.include_router(router)

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
