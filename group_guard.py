import re
import time
import threading

# Qorovul sozlamalari
GUARD_CONFIG = {
    "enabled": True,             # Qorovulni yoqish/o'chirish
    "block_links": True,         # Havola, @username va forwardlarni o'chirish
    "block_bad_words": True,     # So'kinish va haqoratlarni o'chirish
    "block_media_nsfw": False,   # True bo'lsa: oddiy a'zolarning rasm/video/stikerlarini o'chiradi
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
warnings_db = {}


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


def has_link_or_forward(message) -> bool:
    entities = (message.entities or []) + (message.caption_entities or [])
    if any(e.type in ("url", "text_link", "mention") for e in entities):
        return True

    text = f"{message.text or ''} {message.caption or ''}"
    if LINK_REGEX.search(text):
        return True

    if getattr(message, "forward_from", None) or getattr(message, "forward_from_chat", None) or getattr(message, "forward_date", None):
        return True

    return False


def is_admin_or_channel(bot, message) -> bool:
    if getattr(message, "is_automatic_forward", False) or not message.from_user:
        return True
    if message.from_user.id in (777000, 1087968824):
        return True
    try:
        member = bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def _delete_later(bot, chat_id, message_id, delay=8):
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def apply_punishment(bot, message, reason: str):
    chat_id = message.chat.id
    user = message.from_user

    try:
        bot.delete_message(chat_id, message.message_id)
    except Exception:
        pass

    key = (chat_id, user.id)
    warnings_db[key] = warnings_db.get(key, 0) + 1
    count = warnings_db[key]

    if count >= GUARD_CONFIG["max_warnings"]:
        try:
            if GUARD_CONFIG["ban_forever"]:
                bot.ban_chat_member(chat_id, user.id)
                status_msg = "guruhdan butunlay bloklandi 🚫"
            else:
                bot.restrict_chat_member(
                    chat_id,
                    user.id,
                    until_date=int(time.time()) + 86400,
                    can_send_messages=False,
                )
                status_msg = "24 soatga yozishdan cheklandi 🔇"

            warnings_db.pop(key, None)
            notice = bot.send_message(
                chat_id,
                f"🛡️ <b>{user.first_name}</b> {status_msg}\nSabab: {reason}.",
                parse_mode="HTML",
            )
            threading.Thread(target=_delete_later, args=(bot, chat_id, notice.message_id), daemon=True).start()
        except Exception as e:
            print(f"Bloklashda xatolik: {e}")
    else:
        notice = bot.send_message(
            chat_id,
            f"⚠️ <b>{user.first_name}</b>, {reason}!\n"
            f"Ogohlantirish: <b>{count}/{GUARD_CONFIG['max_warnings']}</b>",
            parse_mode="HTML",
        )
        threading.Thread(target=_delete_later, args=(bot, chat_id, notice.message_id), daemon=True).start()


def register_guard(bot):
    @bot.message_handler(
        chat_types=["group", "supergroup"],
        commands=["qorovul"],
    )
    def toggle_guard(message):
        if not is_admin_or_channel(bot, message):
            return
        GUARD_CONFIG["enabled"] = not GUARD_CONFIG["enabled"]
        holat = "YOQILDI ✅" if GUARD_CONFIG["enabled"] else "O'CHIRILDI ❌"
        res = bot.reply_to(message, f"🛡️ Guruh qorovuli: <b>{holat}</b>", parse_mode="HTML")
        threading.Thread(target=_delete_later, args=(bot, message.chat.id, message.message_id, 5), daemon=True).start()
        threading.Thread(target=_delete_later, args=(bot, message.chat.id, res.message_id, 5), daemon=True).start()

    @bot.message_handler(
        chat_types=["group", "supergroup"],
        content_types=["text", "photo", "video", "animation", "sticker", "video_note", "document", "audio", "voice"],
    )
    def group_protector(message):
        if not GUARD_CONFIG["enabled"]:
            return
        if is_admin_or_channel(bot, message):
            return

        full_text = f"{message.text or ''} {message.caption or ''}".strip()

        # 1. Havola va reklama tekshiruvi
        if GUARD_CONFIG["block_links"] and has_link_or_forward(message):
            apply_punishment(bot, message, "guruhga havola yoki reklama tashlash taqiqlangan")
            return

        # 2. So'kinish tekshiruvi
        if GUARD_CONFIG["block_bad_words"] and has_profanity(full_text):
            apply_punishment(bot, message, "guruhda haqoratli so'z yozish taqiqlangan")
            return

        # 3. Keraksiz media nazorati
        if message.content_type in ("photo", "video", "animation", "sticker", "video_note") and GUARD_CONFIG["block_media_nsfw"]:
            apply_punishment(bot, message, "guruhga media yoki stiker tashlash cheklangan")
            return
