import os
import re
import json
import base64
import binascii
import logging
from json import JSONDecodeError
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, Query
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    Update,
    BufferedInputFile,
)
from aiogram.exceptions import TelegramAPIError

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("BOTTOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL") or os.getenv("WEBAPPURL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") or os.getenv("WEBHOOKSECRET")

dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if WEB_APP_URL:
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Create", web_app=WebAppInfo(url='https://ebalvasvrot.github.io/student-id-generator/'))]],
            resize_keyboard=True,
        )
        await message.answer("Привет! Нажми «Create», чтобы открыть мини‑апп.", reply_markup=kb)
    else:
        await message.answer("Привет! Бот на Render работает. Команда: /ping")

@dp.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer("pong")

@dp.message(F.web_app_data)
async def on_webapp(message: Message):
    try:
        payload = json.loads(message.web_app_data.data)
    except JSONDecodeError:
        await message.answer("Некорректные данные от WebApp.")
        return

    data_url = payload.get("image")
    filename = payload.get("filename", "card.png")

    if data_url and data_url.startswith("data:image"):
        try:
            header, b64data = data_url.split(",", 1)
        except ValueError:
            await message.answer("Некорректный формат data URL.")
            return

        m = re.match(r"data:(image/[\w.+-]+);base64", header)
        mime = m.group(1) if m else "image/png"

        if "." not in filename:
            filename += "." + mime.split("/")[-1]

        try:
            raw = base64.b64decode(b64data)
        except (binascii.Error, ValueError):
            await message.answer("Не удалось декодировать изображение (base64).")
            return

        buf = BufferedInputFile(raw, filename=filename)
        try:
            await message.bot.send_document(
                chat_id=message.chat.id,
                document=buf,
                caption="Твоя карточка",
            )
        except TelegramAPIError:
            await message.answer("Не удалось отправить изображение.")
        return

    await message.answer(f"Данные получены: {payload}")

@asynccontextmanager
async def lifespan(fa_app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN")
    bot = Bot(BOT_TOKEN)
    fa_app.state.bot = bot
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        yield
    finally:
        await bot.session.close()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    if not WEBHOOK_SECRET or token != WEBHOOK_SECRET:
        return Response(status_code=403)
    data = await request.json()
    update = Update.model_validate(data)
    bot: Bot = request.app.state.bot
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/set-webhook")
async def set_webhook(request: Request, token: str = Query(...)):
    if not WEBHOOK_SECRET or token != WEBHOOK_SECRET:
        return {"ok": False, "error": "forbidden"}
    base = str(request.base_url).rstrip("/")
    url = f"{base}/webhook/{WEBHOOK_SECRET}"
    bot: Bot = request.app.state.bot
    await bot.set_webhook(
        url=url,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
        allowed_updates=["message", "edited_message", "callback_query"],
    )
    return {"ok": True, "url": url}

@app.get("/")
async def root():

    return {"ok": True}

