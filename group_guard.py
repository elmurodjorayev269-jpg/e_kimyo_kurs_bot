import asyncio
import logging
import re
from datetime import timedelta
from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.types import ChatPermissions

guard_router = Router(name="group_guard")

# Qorovul sozlamalari (Admin paneldan ham o'zgartirish mumkin)
GUARD_CONFIG = {
    "enabled": True,             # Qorovulni yoqish/o'chirish
    "block_links": True,         # Havola, @username va forwardlarni o'chirish
    "block_bad_words": True,     # So'kinish va haqoratlarni o'chirish
    "block_media_nsfw": False,   # True bo'lsa: oddiy a'zolarning rasm/video/stiker/GIFlarini o'chiradi
    "max_warnings": 2,           # Nechta ogohlantirishdan keyin bloklansin (1 = darhol blok)
    "ban_forever": True,         # True = butunlay Ban, False = 24 soatga Mute
}

# Taqiqlangan so'zlar bazasi (kichik harflarda yozing)
BAD_WORDS = {
    "soz1",
    "soz2",
    "haqorat1",
}

LINK_REGEX = re.compile(
    r"(https?://\S+|t\.me/\S+|telegram\.me/\S+|www\.\S+|@[a-zA-Z0-9_]{4,}|\b\S+\.(uz|ru|com|net|org|me|xyz|info)\b)",
    re.IGNORECASE,
)

# Ogohlantirishlar hisoblagichi: {(chat_id, user_id): soni}
warnings_db: dict[tuple[int, int], int] = {}


def _clean_text(text: str) -> str:
    return re.sub(r"[^a-zа-яё0-9ʻ’']", "", text.lower())


def has_profanity(text: str) -> bool:
    if not text:
        return False
    words = re.findall(r"[a-zа-яё0-9ʻ’']+", text.lower())
    if any(w in BAD_WORDS for w in words):
        return True
    normalized = _clean_text(text)
    return any(bad in normalized for bad in BAD_WORDS)


def has_link_or_forward(message: types.Message) -> bool:
    entities = (message.entities or []) + (message.caption_entities or [])
    if any(e.type in ("url", "text_link", "mention") for e in entities):
        return True

    text = f"{message.text or ''} {message.caption or ''}"
    if LINK_REGEX.search(text):
        return True

    if message.forward_origin is not None:
        return True

    return False


async def is_admin_or_channel(bot: Bot, message: types.Message) -> bool:
    # Asosiy kanaldan kelgan avtomatik postlarga tegmaymiz
    if message.is_automatic_forward or not message.from_user:
        return True
    if message.from_user.id in (777000, 1087968824):
        return True
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in ("administrator", "creator")


async def apply_punishment(bot: Bot, message: types.Message, reason: str):
    chat_id = message.chat.id
    user = message.from_user

    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"Xabarni o'chirib bo'lmadi: {e}")

    key = (chat_id, user.id)
    warnings_db[key] = warnings_db.get(key, 0) + 1
    count = warnings_db[key]

    if count >= GUARD_CONFIG["max_warnings"]:
        try:
            if GUARD_CONFIG["ban_forever"]:
                await bot.ban_chat_member(chat_id=chat_id, user_id=user.id)
                status_msg = "guruhdan butunlay bloklandi 🚫"
            else:
                await bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=timedelta(hours=24),
                )
                status_msg = "24 soatga yozishdan cheklandi 🔇"

            warnings_db.pop(key, None)
            notice = await bot.send_message(
                chat_id,
                f"🛡️ <b>{user.full_name}</b> {status_msg}\nSabab: {reason}.",
                parse_mode="HTML",
            )
        except Exception as e:
            logging.error(f"Bloklashda xatolik: {e}")
            return
    else:
        notice = await bot.send_message(
            chat_id,
            f"⚠️ <b>{user.full_name}</b>, {reason}!\n"
            f"Ogohlantirish: <b>{count}/{GUARD_CONFIG['max_warnings']}</b>",
            parse_mode="HTML",
        )

    await asyncio.sleep(8)
    try:
        await notice.delete()
    except Exception:
        pass


# Guruhda /qorovul buyrug'i orqali adminlar tezkor yoqib-o'chirishi mumkin
@guard_router.message(F.chat.type.in_({"group", "supergroup"}), Command("qorovul"))
async def toggle_guard_cmd(message: types.Message, bot: Bot):
    if not await is_admin_or_channel(bot, message):
        return
    GUARD_CONFIG["enabled"] = not GUARD_CONFIG["enabled"]
    holat = "YOQILDI ✅" if GUARD_CONFIG["enabled"] else "O'CHIRILDI ❌"
    res = await message.reply(f"🛡️ Guruh qorovuli: <b>{holat}</b>", parse_mode="HTML")
    await asyncio.sleep(5)
    try:
        await message.delete()
        await res.delete()
    except Exception:
        pass


# Guruhdagi barcha xabarlarni tekshiruvchi asosiy filtr
@guard_router.message(F.chat.type.in_({"group", "supergroup"}))
async def group_protector(message: types.Message, bot: Bot):
    if not GUARD_CONFIG["enabled"]:
        return

    if await is_admin_or_channel(bot, message):
        return

    full_text = f"{message.text or ''} {message.caption or ''}".strip()

    # 1. Havola va reklama nazorati
    if GUARD_CONFIG["block_links"] and has_link_or_forward(message):
        await apply_punishment(bot, message, "guruhga havola yoki reklama tashlash taqiqlangan")
        return

    # 2. So'kinish nazorati
    if GUARD_CONFIG["block_bad_words"] and has_profanity(full_text):
        await apply_punishment(bot, message, "guruhda haqoratli so'z yozish taqiqlangan")
        return

    # 3. 18+ / Porno va keraksiz media nazorati
    is_media = bool(
        message.photo or message.video or message.animation or message.sticker or message.video_note
    )
    if is_media and GUARD_CONFIG["block_media_nsfw"]:
        await apply_punishment(bot, message, "guruhga media yoki stiker tashlash cheklangan")
        return
