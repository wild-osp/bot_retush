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

photo_storage = {}   # оригинальное фото
last_result = {}     # последнее успешно обработанное фото

# ================= ПРОМПТЫ =================

PROMPTS = {
    # Восстановление
    "restore_old": (
        "Профессионально восстанови старое или повреждённое фото: убери царапины, шум, пыль, трещины, "
        "выцветание. Сохрани естественные цвета и резкость. "
        "СТРОГО: не изменять лицо, глаза, рот, нос, уши, форму головы и мимику. Photorealistic."
    ),

    "clean_max": (
        "Максимально очисти фото: убери шум, пыль, мелкие дефекты, артефакты. "
        "СТРОГО: не изменять лицо и черты лица."
    ),

    "color_restore": (
        "Восстанови естественные цвета старого или выцветшего фото. "
        "СТРОГО: не изменять лицо и черты лица."
    ),

    # Ритуальный портрет
    "ritual_portrait": (
        "Создай строгий ритуальный портрет с мягким студийным освещением и аккуратной композицией. "
        "СТРОГО: никаких рамок, крестов, свечей, бантиков, декоративных элементов, орнаментов, надписей. "
        "Только чистый строгий портрет. Лицо и черты лица не изменять."
    ),

    # Лента
    "ribbon_bottom": (
        "Добавь в правый нижний угол изображения чёрную атласную траурную ленту по диагонали. "
        "Лента должна быть аккуратной, без бантиков, без украшений. "
        "СТРОГО: лента размещается на изображении, НЕ на человеке, НЕ на одежде."
    ),

    # Фоны
    "bg_gray": (
        "Замени фон на спокойный светло‑серый градиент. "
        "СТРОГО: не изменять лицо, черты лица, мимику, волосы, одежду."
    ),

    "bg_dark": (
        "Замени фон на тёмный классический ритуальный фон. "
        "СТРОГО: не изменять лицо, черты лица, мимику, волосы, одежду."
    ),

    "bg_white": (
        "Замени фон на чисто белый. "
        "СТРОГО: не изменять лицо, черты лица, мимику, волосы, одежду."
    ),

    # Одежда
    "clothes_male": (
        "Замени одежду на строгий тёмный мужской костюм. "
        "СТРОГО: не изменять лицо, черты лица, мимику, волосы."
    ),

    "clothes_female": (
        "Замени одежду на тёмное строгое женское платье. "
        "СТРОГО: не изменять лицо, черты лица, мимику, волосы."
    ),

    "clothes_formal": (
        "Замени одежду на формальную траурную одежду. "
        "СТРОГО: не изменять лицо, черты лица, мимику, волосы."
    ),

    # Обычная обработка
    "enhance_quality": (
        "Улучшить качество фото: повысить резкость, детализацию, цвет. "
        "СТРОГО: не изменять лицо и черты лица."
    ),

    "style_change": (
        "Измени стиль фото: мягкий портретный, киношный, аккуратный художественный стиль. "
        "СТРОГО: не изменять лицо и черты лица."
    ),

    "denoise": (
        "Убери шум, артефакты и цифровые искажения. "
        "СТРОГО: не изменять лицо и черты лица."
    ),
}

# ================= КЛАВИАТУРЫ =================

def main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🛠 Восстановление и улучшение", callback_data="menu:restore")
    kb.button(text="🖼 Ритуальный портрет", callback_data="menu:ritual")
    kb.button(text="🎀 Добавить траурную ленту", callback_data="ribbon_bottom")
    kb.button(text="🎨 Смена фона", callback_data="menu:bg")
    kb.button(text="👔 Смена одежды", callback_data="menu:clothes")
    kb.button(text="✍️ Свой промпт", callback_data="custom_global")
    kb.button(text="🖌 Обычная обработка", callback_data="menu:normal")
    kb.button(text="🔄 Доработать последнее фото", callback_data="redo_last")
    kb.adjust(1)
    return kb.as_markup()

def restore_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔧 Восстановить старое фото", callback_data="restore_old")
    kb.button(text="🧼 Максимальная очистка", callback_data="clean_max")
    kb.button(text="🎨 Восстановить цвета", callback_data="color_restore")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def ritual_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🖼 Создать ритуальный портрет", callback_data="ritual_portrait")
    kb.button(text="✍️ Свой ритуальный промпт", callback_data="custom_ritual")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def bg_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🌫 Светло‑серый градиент", callback_data="bg_gray")
    kb.button(text="🌑 Тёмный классический", callback_data="bg_dark")
    kb.button(text="⚪ Чисто белый", callback_data="bg_white")
    kb.button(text="✍️ Свой промпт (фон)", callback_data="custom_bg")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def clothes_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="👔 Тёмный мужской костюм", callback_data="clothes_male")
    kb.button(text="👗 Тёмное женское платье", callback_data="clothes_female")
    kb.button(text="🕴 Формальная траурная одежда", callback_data="clothes_formal")
    kb.button(text="✍️ Свой промпт (одежда)", callback_data="custom_clothes")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

def normal_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="✨ Улучшить качество", callback_data="enhance_quality")
    kb.button(text="🎨 Изменить стиль", callback_data="style_change")
    kb.button(text="🧹 Убрать шум", callback_data="denoise")
    kb.button(text="✍️ Свой промпт", callback_data="custom_normal")
    kb.button(text="← Назад", callback_data="back:main")
    kb.adjust(1)
    return kb.as_markup()

# ================= ОБРАБОТКА ФОТО =================

async def process_image(user_id, prompt_text, photo_bytes):
    await bot.send_message(user_id, "🔄 Обрабатываю фото…")

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
                            b64_data = url.split("base64,")[-1]
                            result_bytes = base64.b64decode(b64_data)
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
                                        caption=f"✅ Готово\n{prompt_text[:140]}..."
                                    )
                                ]
                            )
                            return

            await bot.send_message(user_id, "❌ Не удалось получить изображение.")

    except Exception as e:
        logging.error(f"OpenRouter error: {e}")
        await bot.send_message(user_id, f"❌ Ошибка: {str(e)[:350]}")

# ================= ХЕНДЛЕРЫ =================

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 **Ритуальный ретушёр** готов!\n\n"
        "Отправь фото и выбери действие."
    )

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    file = await bot.get_file(message.photo[-1].file_id)
    file_bytes = await bot.download_file(file.file_path)

    photo_storage[user_id] = file_bytes.getvalue()
    last_result[user_id] = None

    await message.answer("📸 Фото получено!\nВыбери действие:", reply_markup=main_keyboard())

@dp.callback_query()
async def process_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if user_id not in photo_storage:
        await callback.answer("Фото устарело. Отправь заново.", show_alert=True)
        return

    # Меню
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
    if data == "menu:normal":
        await callback.message.edit_reply_markup(reply_markup=normal_keyboard())
        return
    if data == "back:main":
        await callback.message.edit_reply_markup(reply_markup=main_keyboard())
        return

    # Свои промпты
    if data.startswith("custom"):
        mode = data.split("_")[1] if "_" in data else "global"
        await callback.message.edit_text(f"✍️ Напиши свой промпт ({mode}).")
        dp.custom_mode = mode
        return

    # Обработка
    prompt_text = PROMPTS.get(data)
    if not prompt_text:
        await callback.answer("Ошибка: неизвестная команда.")
        return

    await callback.message.delete()
    photo_bytes = last_result[user_id] if data == "redo_last" and last_result[user_id] else photo_storage[user_id]

    await process_image(user_id, prompt_text, photo_bytes)

@dp.message()
async def handle_custom_prompt(message: types.Message):
    user_id = message.from_user.id
    if user_id not in photo_storage:
        return

    mode = getattr(dp, "custom_mode", "global")
    user_text = message.text.strip()

    if mode == "ritual":
        full_prompt = (
            f"{user_text}. "
            "СТРОГО: никаких рамок, крестов, свечей, бантиков, декоративных элементов. "
            "Не изменять лицо и черты лица."
        )
    else:
        full_prompt = (
            f"{user_text}. "
            "СТРОГО: не изменять лицо, черты лица, мимику, форму головы."
        )

    await process_image(user_id, full_prompt, photo_storage[user_id])

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
