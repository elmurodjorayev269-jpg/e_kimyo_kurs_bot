import os
import re
import time
import base64
import threading
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Qorovul sozlamalari
GUARD_CONFIG = {
    "enabled": True,             # Qorovulni yoqish/o'chirish
    "block_links": True,         # Havola, @username va forwardlarni o'chirish
    "block_bad_words": True,     # So'kinish va haqoratlarni o'chirish
    "ai_nsfw_check": True,       # AI orqali faqat 18+ rasm, stiker, GIF va videolarni ushlash
    "max_warnings": 2,           # Nechta ogohlantirishdan keyin bloklansin
    "ban_forever": True,         # True = butunlay Ban, False = 24 soatga Mute
}

EXACT_BAD_WORDS = {
    "it", "eshak", "mol", "chochqa", "cho'chqa", "lox", "loh", "sucka", "suka",
    "blya", "blyat", "nah", "nax", "pox", "poh", "xuy", "huy", "xui", "hui",
    "eb", "yeb", "sik", "seq", "sex", "seks", "porno", "porn", "xxx",
    "сука", "бля", "блять", "лох", "хуй", "еб", "ёб", "секс", "порно",
    "fuck", "shit", "bitch", "dick", "cock", "pussy", "slut", "whore",
}

ROOT_BAD_WORDS = {
    "ahmoq", "axmoq", "tentak", "jinni", "iflos", "harom", "xarom", "haromi", "xaromi",
    "qanjq", "qanjiq", "fohisha", "foxisha", "jalab", "jalap", "sharmanda", "betamiz",
    "beodob", "terpila", "kazzob", "muttaham", "maraz", "razill", "ablah", "ablax",
    "hayvon", "xayvon", "to'ng'iz", "tongiz", "eshshak", "dalbayob", "dolboeb",
    "dalbayop", "gandon", "gandoncha", "pidar", "pidaras", "pedik", "g'ar", "gar",
    "sikin", "sikay", "sikey", "sikish", "sikaman", "sikadi", "sikilgan",
    "qo'toq", "qotoq", "qutoq", "qu'toq", "amcha", "amlar", "aming", "amingga",
    "emchak", "ko't", "kotvachcha", "ko'tvachcha", "kotlik", "ko'tlik",
    "onangni", "onangdi", "oneni", "onengni", "enangni", "eneni", "singlingni",
    "opangni", "og'zingga", "ogzingga", "og'zinga", "ogzinga", "kallanga",
    "basharangga", "aftingga", "daxuya", "chort", "chmo", "chmoshnik",
    "ахмок", "аҳмоқ", "тентак", "жинни", "ифлос", "харом", "ҳаром", "хароми", "ҳароми",
    "канжик", "қанжиқ", "фохиша", "фоҳиша", "жалаб", "жалап", "шарманда",
    "каззоб", "муттахам", "муттаҳам", "мараз", "аблах", "аблаҳ",
    "хайвон", "ҳайвон", "тунгиз", "тўнғиз", "эшак", "эшшак",
    "далбаёб", "долбоёб", "гандон", "пидар", "пидарас", "педик", "ғар",
    "сикин", "сикай", "сикей", "сикиш", "сикаман", "сикади", "сикилган",
    "куток", "қўтоқ", "қутоқ", "аминг", "амингга", "эмчак", "кутвачча", "кўтвачча",
    "онангни", "онангди", "онени", "онангнинг", "энангни", "синглингни",
    "опангни", "огзингга", "оғзингга", "башарангга", "афтингга", "чмо", "чмошник",
    "бляд", "сучк", "хуйн", "хуев", "хуёв", "охуе", "ахуе", "нахуй", "похуй",
    "пизд", "ебан", "ёбан", "ебат", "ебал", "ебло", "уебок", "уёбок", "заеб",
    "мудак", "мудил", "гандон", "пидор", "шлюх", "шалав", "мраз", "тварь",
    "ублюд", "дебил", "идиот", "кретин", "сволоч", "падл", "гнид", "хуесос",
    "pizd", "pidor", "ebat", "ebal", "yeban", "xuyna", "huyna", "nahuy", "pohuy",
    "shlyux", "shalav", "mudak", "ublyud", "debil", "svoloch", "xuesos", "huesos",
    "fucking", "fucker", "motherfuck", "bullshit", "asshole", "bastard", "dumbass",
    "jerkoff", "wanker", "cunt", "faggot", "nigger", "nigga",
}

LEET_MAP = str.maketrans({
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b",
    "@": "a", "$": "s", "!": "i",
})

LINK_REGEX = re.compile(
    r"(https?://\S+|t\.me/\S+|telegram\.me/\S+|www\.\S+|@[a-zA-Z0-9_]{4,}|\b\S+\.(uz|ru|com|net|org|me|xyz|info)\b)",
    re.IGNORECASE,
)

warnings_db = {}


def _normalize_text(text: str) -> str:
    lowered = text.lower().translate(LEET_MAP)
    lowered = lowered.replace("o‘", "o").replace("o'", "o").replace("oʻ", "o")
    lowered = lowered.replace("g‘", "g").replace("g'", "g").replace("gʻ", "g")
    cleaned = re.sub(r"[^a-zа-яёқғҳў]", "", lowered)
    cleaned = re.sub(r"(.)\1{2,}", r"\1", cleaned)
    return cleaned


def has_profanity(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower().translate(LEET_MAP)
    lowered = lowered.replace("o‘", "o").replace("o'", "o").replace("oʻ", "o")
    lowered = lowered.replace("g‘", "g").replace("g'", "g").replace("gʻ", "g")

    words = re.findall(r"[a-zа-яёқғҳў]+", lowered)
    for w in words:
        w_short = re.sub(r"(.)\1{2,}", r"\1", w)
        if w in EXACT_BAD_WORDS or w_short in EXACT_BAD_WORDS:
            return True
        for root in ROOT_BAD_WORDS:
            if root in w or root in w_short:
                return True

    joined = _normalize_text(text)
    for root in ROOT_BAD_WORDS:
        if root in joined:
            return True
    return False


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


def is_nsfw_by_ai(bot, message) -> bool:
    """Rasm, stiker, GIF yoki videoning muqovasini AI orqali tekshiradi."""
    if not GEMINI_API_KEY:
        return False

    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.sticker:
        if message.sticker.thumb:
            file_id = message.sticker.thumb.file_id
        elif not message.sticker.is_animated and not message.sticker.is_video:
            file_id = message.sticker.file_id
    elif message.animation and message.animation.thumb:
        file_id = message.animation.thumb.file_id
    elif message.video and message.video.thumb:
        file_id = message.video.thumb.file_id
    elif message.video_note and message.video_note.thumb:
        file_id = message.video_note.thumb.file_id

    if not file_id:
        return False

    try:
        file_info = bot.get_file(file_id)
        img_bytes = bot.download_file(file_info.file_path)
        b64_img = base64.b64encode(img_bytes).decode("utf-8")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{
                "parts": [
                    {
                        "text": (
                            "Does this image contain sexually explicit content, nudity, pornography, or NSFW material? "
                            "Reply with strictly one word: YES or NO."
                        )
                    },
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": b64_img
                        }
                    }
                ]
            }]
        }
        resp = requests.post(url, json=payload, timeout=6)
        if resp.status_code == 200:
            answer = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
            return answer.startswith("YES")
    except Exception as e:
        print(f"AI NSFW tekshiruv xatosi: {e}")

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


def _delete_later(bot, chat_id, message_id, delay=5):
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
    except Exception:
        pass


def apply_punishment(bot, message, reason: str, instant_ban: bool = False):
    chat_id = message.chat.id
    user = message.from_user

    try:
        bot.delete_message(chat_id, message.message_id)
    except Exception:
        pass

    key = (chat_id, user.id)
    warnings_db[key] = warnings_db.get(key, 0) + 1
    count = warnings_db[key]

    if instant_ban or count >= GUARD_CONFIG["max_warnings"]:
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

        # 2. So'kinish va haqorat tekshiruvi
        if GUARD_CONFIG["block_bad_words"] and has_profanity(full_text):
            apply_punishment(bot, message, "guruhda haqoratli so'z yozish taqiqlangan")
            return

        # 3. AI orqali 18+ (porno) rasm, stiker, GIF va videolarni aniqlash
        if GUARD_CONFIG["ai_nsfw_check"] and message.content_type in ("photo", "sticker", "animation", "video", "video_note"):
            if is_nsfw_by_ai(bot, message):
                apply_punishment(bot, message, "guruhga 18+ (behayo) kontent tashlash taqiqlangan", instant_ban=True)
                return
