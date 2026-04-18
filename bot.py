import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

import os
from io import BytesIO

# Новый Google GenAI SDK
from google import genai
from google.genai import types

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

# Модели для Nano Banana 2 (приоритет: самая новая → запасная)
MODELS = [
    "gemini-3.1-flash-image-preview",   # Nano Banana 2 (основная)
    "gemini-2.5-flash-image"            # Nano Banana (запасная)
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Промпты для кнопок
PROMPTS = {
    "enhance": "Улучши качество фото, сделай его чётче, красивее и профессиональнее, но НЕ меняй лицо человека и его черты.",
    "background": "Поменяй фон на современный минималистичный или красивый (природа, студия, город), но НЕ меняй лицо, тело и одежду человека.",
    "portrait": "Сделай профессиональный студийный портрет: улучши кожу, освещение, цвета, но НЕ меняй черты лица.",
    "color": "Сделай цвета более яркими и естественными, улучши общее качество фото, лицо не трогай.",
    "cinema": "Преврати фото в кинематографичный стиль с красивым светом и атмосферой, но оставь лицо реалистичным.",
    "remove_bg": "Удали фон полностью и сделай прозрачный фон (или чисто белый), лицо и тело оставь без изменений.",
}

photo_storage = {}

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Привет! Я бот для ретуши фото через **Gemini Nano Banana 2**.\n\n"
        "Отправь мне фото и выбери действие кнопками."
    )

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    
    photo_storage[message.from_user.id] = file_bytes.getvalue()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Улучшить качество", callback_data="enhance")],
        [InlineKeyboardButton(text="🌄 Изменить фон", callback_data="background")],
        [InlineKeyboardButton(text="🖼 Профессиональный портрет", callback_data="portrait")],
        [InlineKeyboardButton(text="🌈 Яркие цвета", callback_data="color")],
        [InlineKeyboardButton(text="🎥 Кинематографичный стиль", callback_data="cinema")],
        [InlineKeyboardButton(text="✂️ Удалить фон", callback_data="remove_bg")],
    ])

    await message.answer("✅ Фото получено!\n\nВыбери действие:", reply_markup=keyboard)

@dp.callback_query()
async def process_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id not in photo_storage:
        await callback.answer("Фото устарело. Отправь заново.", show_alert=True)
        return

    prompt_key = callback.data
    prompt_text = PROMPTS.get(prompt_key, "Улучши качество фото, не меняя лицо.")

    await callback.answer("🔄 Обрабатываю через Nano Banana 2...")

    photo_bytes = photo_storage[user_id]
    success = False

    for model_name in MODELS:
        try:
            await bot.send_message(user_id, f"🔄 Пробую модель: {model_name}")

            response = client.models.generate_content(
                model=model_name,
                contents=[
                    prompt_text,
                    types.Part.from_bytes(
                        data=photo_bytes,
                        mime_type="image/jpeg"
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.7,
                )
            )

            # Извлекаем изображение
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        image_bytes = part.inline_data.data
                        
                        await bot.send_photo(
                            chat_id=user_id,
                            photo=types.BufferedInputFile(image_bytes, filename="retouched.jpg"),
                            caption=f"✅ Готово! (модель: {model_name})\n\nПромпт: {prompt_text[:100]}..."
                        )
                        success = True
                        break
                if success:
                    break
            else:
                await bot.send_message(user_id, f"Модель {model_name} не вернула изображение.")

        except Exception as e:
            error_str = str(e).lower()
            logging.error(f"Ошибка с моделью {model_name}: {e}")
            if "not found" in error_str or "model" in error_str:
                await bot.send_message(user_id, f"❌ Модель {model_name} недоступна, пробую следующую...")
                continue
            else:
                await bot.send_message(user_id, f"❌ Ошибка: {str(e)[:300]}")
                break

    if not success:
        await bot.send_message(user_id, "❌ Не удалось обработать фото ни одной моделью. Попробуй позже или другое фото.")

    # Очистка
    if user_id in photo_storage:
        del photo_storage[user_id]

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
