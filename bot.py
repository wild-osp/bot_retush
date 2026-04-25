import asyncio
import logging
import base64
import os

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

MODEL_NAME = "google/gemini-3.1-flash-image-preview"

photo_storage = {}      # оригинальное фото
last_result = {}        # последнее обработанное фото
processing = {}         # защита от двойного нажатия

# ================= ПРОМПТЫ (сильная защита лица) =================
PROMPTS = {
    "restore": "Профессионально восстанови старое или повреждённое фото. Убери царапины, шум, пятна, трещины, выцветание. Сделай чёткость и естественные цвета. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА ЧЕЛОВЕКА. Сохрани полное сходство. Photorealistic, high detail.",
    
    "restore_extend": "Восстанови старое фото и немного расширь его (дорисуй плечи и фон, чтобы фото стало крупнее). НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА. Всё должно быть пропорционально и естественно.",
    
    "ritual_portrait": "Сделай красивое ритуальное портретное фото с мягким студийным освещением и достойным видом. Улучши качество. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА ЧЕЛОВЕКА. Сохрани максимальное сходство.",
    
    "ritual_with_ribbon": "Сделай ритуальный портрет и добавь в ПРАВЫЙ НИЖНИЙ УГОЛ чёрную траурную ленту по диагонали. Лента простая, аккуратная, только лента, без бантиков, без цветов, без украшений. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА.",
    
    "ritual_strict": "Сделай ритуальный портрет со строгим фоном и строгой одеждой (тёмный костюм или платье). Никаких крестов и лишних траурных элементов. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА.",
    
    "bg_auto": "Поменяй фон на спокойный нейтральный фон, подходящий для ритуальной печати. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ, ОДЕЖДУ И ЧЕРТЫ ЛИЦА.",
    
    "clothes_auto": "Поменяй одежду на строгую траурную одежду. НЕ ИЗМЕНЯЙ ЛИЦО, ГЛАЗА, РОТ, УШИ И ЧЕРТЫ ЛИЦА. Одежда должна быть пропорциональной.",
}

def main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔧 Восстановление старого фото", callback_data="menu:restore")
    kb.button(text="🖼 Ритуальный портрет", callback_data="menu:ritual")
    kb.button(text="🌫 Смена фона", callback_data="menu:bg")
    kb.button(text="👔 Смена одежды", callback_data="menu:clothes")
    kb.button(text="🧼 Максимальная очистка", callback_data="clean")
    kb.button(text="🎨 Восстановить цвета", callback_data="color_restore")
    kb.button(text="✍️ Свой промпт", callback_data="custom")
    kb.button(text="🔄 Доработать последнее фото", callback_data="redo_last")
    kb.adjust(1)
    return kb.as_markup()

def restore_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Восстановить старое фото", callback_data="restore")
    kb.button(text="Восстановить + расширить размер", callback_data="restore_extend")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def ritual_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Ритуальный портрет", callback_data="ritual_portrait")
    kb.button(text="Ритуальный портрет + лента", callback_data="ritual_with_ribbon")
    kb.button(text="Ритуальный портрет + строгий фон и одежда", callback_data="ritual_strict")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def bg_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Автоподбор спокойного фона", callback_data="bg_auto")
    kb.button(text="Смена фона по моему описанию", callback_data="bg_custom")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def clothes_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="Автоподбор строгой одежды", callback_data="clothes_auto")
    kb.button(text="Смена одежды по моему описанию", callback_data="clothes_custom")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Ритуальный ретушёр готов к работе!\n\n"
        "Отправь фото и выбирай нужное действие."
    )

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    file = await bot.get_file(message.photo[-1].file_id)
    file_bytes = await bot.download_file(file.file_path)

    photo_storage[user_id] = file_bytes.getvalue()
    last_result[user_id] = None
    processing[user_id] = False

    await message.answer("✅ Фото получено!\nЧто нужно сделать для траурной печати?", reply_markup=main_keyboard())

@dp.callback_query()
async def process_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if user_id in processing and processing.get(user_id):
        await callback.answer("⏳ Уже обрабатывается, подожди...", show_alert=True)
        return

    if user_id not in photo_storage:
        await callback.answer("Фото устарело. Отправь заново.", show_alert=True)
        return

    # Открытие подменю
    if data == "menu:restore":
        await callback.message.edit_reply_markup(reply_markup=restore_keyboard())
        return
    if data == "menu:ritual":
        await callback.message.edit_reply_markup(reply_markup=ritual_keyboard())
        return
    if data == "menu:bg":
        await callback.message.edit_reply_markup(reply_markup=bg_keyboard())
        return
    if data == "menu:clothes":
        await callback.message.edit_reply_markup(reply_markup=clothes_keyboard())
        return
    if data == "back:main":
        await callback.message.edit_reply_markup(reply_markup=main_keyboard())
        return

    # Защита от двойного нажатия
    processing[user_id] = True
    await callback.answer("🔄 Обрабатываю через Nano Banana 2...")

    prompt_key = data
    prompt_text = PROMPTS.get(prompt_key, "Улучши качество фото, не меняя лицо.")

    # Выбираем какое фото обрабатывать
    if prompt_key == "redo_last" and last_result.get(user_id):
        photo_bytes = last_result[user_id]
    else:
        photo_bytes = photo_storage[user_id]

    base64_image = base64.b64encode(photo_bytes).decode("utf-8")

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://t.me",
                    "X-Title": "Ritual Retouch Bot",
                },
                json={
                    "model": MODEL_NAME,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}],
                    "modalities": ["image", "text"],
                    "max_tokens": 2048,
                }
            )

            data_json = response.json()

            if "choices" in data_json and data_json["choices"]:
                msg = data_json["choices"][0].get("message", {})
                if msg.get("images"):
                    for img in msg["images"]:
                        url = img.get("image_url", {}).get("url", "")
                        if url.startswith("data:image"):
                            result_bytes = base64.b64decode(url.split("base64,")[-1])
                            last_result[user_id] = result_bytes

                            await bot.send_media_group(
                                chat_id=user_id,
                                media=[
                                    types.InputMediaPhoto(
                                        media=types.BufferedInputFile(photo_bytes, filename="original.jpg"),
                                        caption="📸 Оригинал"
                                    ),
                                    types.InputMediaPhoto(
                                        media=types.BufferedInputFile(result_bytes, filename="result.jpg"),
                                        caption=f"✅ Готово для печати"
                                    )
                                ]
                            )
                            processing[user_id] = False
                            return

            await bot.send_message(user_id, "❌ Не удалось получить изображение от модели.")

    except Exception as e:
        logging.error(f"OpenRouter error: {e}")
        await bot.send_message(user_id, f"❌ Ошибка: {str(e)[:300]}")

    processing[user_id] = False

@dp.message()
async def handle_text(message: types.Message):
    # Пока заглушка для "Свой промпт" и кастомных описаний
    await message.answer("🔄 Функция обработки по тексту пока в разработке.\nПока используй готовые кнопки.")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
