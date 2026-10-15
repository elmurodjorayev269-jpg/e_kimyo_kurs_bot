import asyncio
import base64
import html
import io
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime

import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# -------------------------------------------------------------
# SOZLAMALAR
# -------------------------------------------------------------
_REV_TOKEN = "s-BpMl4q53yLNCTEWSAcmjA5Hp0lRm8UFAA:3840376368"
BOT_TOKEN = os.getenv("BOT_TOKEN", _REV_TOKEN[::-1])

ADMIN_ID = int(os.getenv("ADMIN_ID", "6734050237"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@onlyibrohimov")

_REV_KEY = "APuV_Zc8V-GAeLgUU4cWxQIZ0-R8GP42cko5QV_fPKNL6NR8bA.QA"
DEFAULT_GEMINI_KEY = os.getenv("GEMINI_API_KEY", _REV_KEY[::-1])

DEFAULT_REQUIRED_CHANNEL = "@Kimyo_Sertifkat_uchun"
DEFAULT_CHANNEL_URL = "https://t.me/Kimyo_Sertifkat_uchun"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Faol mock test ishlayotgan o'quvchilarni kuzatish (AI yordamchini bloklash uchun)
ACTIVE_EXAM_SESSIONS = {}  # {user_id: test_code}

# -------------------------------------------------------------
# MA'LUMOTLAR BAZASI
# -------------------------------------------------------------
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            joined_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tests (
            test_code TEXT PRIMARY KEY,
            test_type TEXT,
            title TEXT,
            keys_json TEXT,
            ai_explanation TEXT,
            file_id TEXT,
            file_type TEXT,
            creator_id INTEGER,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_code TEXT,
            user_id INTEGER,
            full_name TEXT,
            correct_count INTEGER,
            total_score REAL,
            grade TEXT,
            written_score REAL DEFAULT 0,
            submitted_at TEXT
        )
    """)
    c.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        ("required_channel", DEFAULT_REQUIRED_CHANNEL)
    )
    c.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
        ("gemini_api_key", DEFAULT_GEMINI_KEY)
    )
    conn.commit()
    conn.close()

def db_add_user(user_id: int, full_name: str, username: str):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, full_name, username, joined_at) VALUES (?, ?, ?, ?)",
        (user_id, full_name, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def db_get_setting(key: str, default: str = "") -> str:
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else default

def db_set_setting(key: str, val: str):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
    conn.commit()
    conn.close()

def db_save_test(test_code: str, test_type: str, title: str, keys_dict: dict, explanation: str = "", file_id: str = "", file_type: str = "", creator_id: int = 0):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE tests ADD COLUMN creator_id INTEGER DEFAULT 0")
    except Exception:
        pass
    c.execute(
        """INSERT OR REPLACE INTO tests 
           (test_code, test_type, title, keys_json, ai_explanation, file_id, file_type, creator_id, created_at) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            test_code.upper(),
            test_type,
            title,
            json.dumps(keys_dict, ensure_ascii=False),
            explanation,
            file_id,
            file_type,
            creator_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    conn.commit()
    conn.close()

def db_get_test(test_code: str):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        "SELECT test_code, test_type, title, keys_json, ai_explanation, file_id, file_type FROM tests WHERE test_code = ?",
        (test_code.upper().strip(),)
    )
    row = c.fetchone()
    conn.close()
    return row

def db_delete_test(test_code: str) -> bool:
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("DELETE FROM tests WHERE test_code = ?", (test_code.upper().strip(),))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def db_get_recent_tests(limit: int = 12):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT test_code, test_type, title, created_at FROM tests ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def db_save_result(test_code: str, user_id: int, full_name: str, correct_count: int, total_score: float, grade: str, written_score: float = 0.0):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE test_results ADD COLUMN written_score REAL DEFAULT 0")
    except Exception:
        pass
    c.execute(
        """INSERT INTO test_results (test_code, user_id, full_name, correct_count, total_score, grade, written_score, submitted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (test_code.upper(), user_id, full_name, correct_count, total_score, grade, written_score, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def db_get_top_results(test_code: str, limit: int = 15):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute(
        """SELECT full_name, correct_count, total_score, grade 
           FROM test_results 
           WHERE test_code = ? 
           ORDER BY total_score DESC, correct_count DESC 
           LIMIT ?""",
        (test_code.upper().strip(), limit)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def db_get_stats():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM tests")
    tests_cnt = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM test_results")
    results_cnt = c.fetchone()[0]
    conn.close()
    return {"users": users, "tests": tests_cnt, "results": results_cnt}

# -------------------------------------------------------------
# MAJBURIY OBUNA TEKSHIRUVI (XATOSIZ REJIM)
# -------------------------------------------------------------
def get_required_channel_data():
    raw = db_get_setting("required_channel", DEFAULT_REQUIRED_CHANNEL).strip()
    if not raw or raw.lower() in ["none", "0", "off"]:
        return None, None
    if "t.me/" in raw:
        uname = raw.split("t.me/")[-1].split("/")[0].split("?")[0].strip()
        return f"@{uname}", f"https://t.me/{uname}"
    if raw.startswith("@"):
        uname = raw[1:].strip()
        return f"@{uname}", f"https://t.me/{uname}"
    if raw.startswith("-100"):
        return raw, DEFAULT_CHANNEL_URL
    return f"@{raw}", f"https://t.me/{raw}"

async def check_channel_subscription(user_id: int) -> bool:
    chat_id, _ = get_required_channel_data()
    if not chat_id:
        return True
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        status_val = getattr(member.status, "value", str(member.status)).lower()
        if status_val in ["creator", "administrator", "member"]:
            return True
        if status_val == "restricted" and getattr(member, "is_member", False):
            return True
        return False
    except Exception:
        return True

async def prompt_subscription(message: types.Message):
    chat_id, ch_url = get_required_channel_data()
    if not ch_url:
        ch_url = DEFAULT_CHANNEL_URL

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga a'zo bo'lish", url=ch_url)],
            [InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="btn_check_sub")]
        ]
    )
    await message.answer(
        "🛑 <b>Diqqat! Botdan foydalanish uchun rasmiy kanalimizga obuna bo'lishingiz shart!</b>\n\n"
        f"👉 Kanal: <a href='{ch_url}'>{chat_id or '@Kimyo_Sertifkat_uchun'}</a>\n\n"
        "Pastdagi <b>«📢 Kanalga a'zo bo'lish»</b> tugmasini bosib qo'shiling, so'ng <b>«✅ Obunani tekshirish»</b> tugmasini bosing 👇",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=kb
    )

# -------------------------------------------------------------
# MATNNI CHIROYLI TELEGRAM FORMATIGA O'TKAZISH (FORMATTER)
# -------------------------------------------------------------
SUB_MAP = str.maketrans("0123456789+-", "₀₁₂₃₄₅₆₇₈₉₊₋")
SUP_MAP = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")

def clean_ai_text_for_telegram(text: str) -> str:
    if not text:
        return ""
    replacements = {
        r"\rightarrow": " → ",
        r"\longrightarrow": " ⟶ ",
        r"\leftarrow": " ← ",
        r"\leftrightarrow": " ↔ ",
        r"\rightleftharpoons": " ⇌ ",
        r"\downarrow": "↓",
        r"\uparrow": "↑",
        r"\cdot": "·",
        r"\times": "×",
        r"\div": "÷",
        r"\pm": "±",
        r"\approx": "≈",
        r"\neq": "≠",
        r"\leq": "≤",
        r"\geq": "≥",
        r"\implies": " ⇒ ",
        r"\Rightarrow": " ⇒ ",
        r"\%": "%",
        r"\circ": "°",
        r"^\circ": "°",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)

    text = re.sub(r"\\(?:text|mathrm|textbf|mathbf)\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"(\1 / \2)", text)
    text = re.sub(r"_\{([0-9+-]+)\}", lambda m: m.group(1).translate(SUB_MAP), text)
    text = re.sub(r"_([0-9])", lambda m: m.group(1).translate(SUB_MAP), text)
    text = re.sub(r"\^\{([0-9+-]+)\}", lambda m: m.group(1).translate(SUP_MAP), text)
    text = re.sub(r"\^([0-9+-])", lambda m: m.group(1).translate(SUP_MAP), text)
    text = text.replace("$$", "").replace("$", "")
    text = re.sub(r"\\([a-zA-Z]+)", r"\1", text)
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"^#{1,4}\s*(.+)$", r"📌 <b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\*\s+", "• ", text, flags=re.MULTILINE)
    return text.strip()

# -------------------------------------------------------------
# SUN'IY INTELLEKT (GEMINI 3.8 FLASH & VISION ZAXIRA)
# -------------------------------------------------------------
def get_gemini_api_key() -> str:
    saved_key = db_get_setting("gemini_api_key", DEFAULT_GEMINI_KEY).strip()
    return saved_key if saved_key else DEFAULT_GEMINI_KEY

async def call_vision_fallback(prompt: str, b64_data: str, mime_type: str, json_mode: bool = False) -> tuple[bool, str]:
    url = "https://text.pollinations.ai/openai"
    for model_name in ["openai", "openai-large", "mistral"]:
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}
                        }
                    ]
                }
            ],
            "temperature": 0.1
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=90) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text_out = data["choices"][0]["message"]["content"]
                        if text_out and len(text_out.strip()) > 3:
                            return True, text_out
        except Exception:
            pass
    return False, "Server javob bermadi"

async def call_gemini_api(prompt: str, b64_data: str, mime_type: str, json_mode: bool = False, timeout_sec: int = 120) -> tuple[bool, str]:
    api_key = get_gemini_api_key()
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_data
                        }
                    }
                ]
            }
        ],
        "generationConfig": {}
    }
    if json_mode:
        payload["generationConfig"]["responseMimeType"] = "application/json"

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-3.8-flash",
        "gemini-3-flash-preview"
    ]
    last_error = ""

    def extract_response_text(data: dict) -> str:
        candidates = data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        non_thought = [p.get("text", "") for p in parts if "text" in p and not p.get("thought", False)]
        if non_thought:
            return "\n".join(non_thought).strip()
        if parts and "text" in parts[-1]:
            return parts[-1]["text"].strip()
        return ""

    if api_key and not api_key.startswith("AQ."):
        async with aiohttp.ClientSession() as session:
            for model_name in models_to_try:
                url_param = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                try:
                    async with session.post(url_param, headers={"Content-Type": "application/json"}, json=payload, timeout=timeout_sec) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text_out = extract_response_text(data)
                            if text_out:
                                return True, text_out
                        else:
                            err_body = await resp.text()
                            last_error = f"HTTP {resp.status}"
                except Exception as e:
                    last_error = str(e)

    if mime_type.startswith("image/"):
        ok_fb, text_fb = await call_vision_fallback(prompt, b64_data, mime_type, json_mode=json_mode)
        if ok_fb:
            return True, text_fb

    return False, last_error or "AI javob bermadi"

async def ai_analyze_test_document(file_bytes: bytes, mime_type: str, test_type: str) -> dict:
    b64_data = base64.b64encode(file_bytes).decode("utf-8")
    if test_type == "30_talik":
        prompt = (
            "Sen Kimyo va aniq fanlar bo'yicha oliy toifali ekspertsan. "
            "Yuborilgan fayldagi test savollarini yechib, javoblar kalitini tuz. "
            "Natijani FAQAT quyidagi JSON formatda qaytar:\n"
            '{"title": "Kimyo 30 talik Test", "keys": {"1": "A", "2": "B"}, "explanation": "Qisqacha izoh"}'
        )
    elif test_type == "43_ms":
        prompt = (
            "Sen Milliy Sertifikat (43 talik) bo'yicha ekspertsan. "
            "Yuborilgan testni yechib kalit tuz:\n"
            "- 1-32: Yopiq (A, B, C, D)\n"
            "- 33-35: Moslashtirish (A, B, C, D, E, F)\n"
            "- 36-40: Ochiq test savollari.\n"
            "Natijani FAQAT quyidagi JSON formatda qaytar:\n"
            '{"title": "Milliy Sertifikat 43 talik", "keys": {"1": "A", "32": "D", "33": "E", "36": "9"}, "explanation": "Izoh"}'
        )
    else:
        prompt = (
            "Sen DTM 90 talik blok testlari bo'yicha ekspertsan. "
            "Savol va javoblarni tahlil qilib, 1 dan 90 gacha to'g'ri javoblarni aniqla. "
            "Natijani FAQAT quyidagi JSON formatda qaytar:\n"
            '{"title": "90 talik DTM Blok Testi", "keys": {"1": "A", "2": "C"}, "explanation": "Izoh"}'
        )

    ok, res_text = await call_gemini_api(prompt, b64_data, mime_type, json_mode=True, timeout_sec=120)
    if not ok:
        return {"error": res_text}

    try:
        raw_text = res_text.strip()
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?|```$", "", raw_text, flags=re.MULTILINE).strip()
        return json.loads(raw_text)
    except Exception as e:
        return {"error": f"JSON o'qishda xato: {e}"}

async def ai_grade_written_work(file_bytes: bytes, q_num: int) -> tuple[float, str]:
    """41, 42, 43-savolning qo'lyozma yechim rasmini AI orqali tekshirish va 0 dan 2.5 ballgacha baholash."""
    b64_data = base64.b64encode(file_bytes).decode("utf-8")
    prompt = (
        f"Sen Milliy Sertifikat imtihonida {q_num}-yozma masala yechimini tekshiruvchi ekspertsan. "
        "O'quvchining daftardagi yechim rasmini tahlil qil. Yechim mantiqan va hisob-kitob jihatdan to'g'riligiga qarab "
        "0 dan 2.5 gacha ball ber. Natijani FAQAT JSON formatda qaytar:\n"
        '{"score": 2.2, "comment": "Reaksiya tenglamasi va mol nisbatlari to\'g\'ri topilgan."}'
    )
    ok, res_text = await call_gemini_api(prompt, b64_data, "image/jpeg", json_mode=True, timeout_sec=60)
    if ok:
        try:
            raw = re.sub(r"^```(?:json)?|```$", "", res_text.strip(), flags=re.MULTILINE).strip()
            data = json.loads(raw)
            score = float(data.get("score", 2.0))
            score = max(0.0, min(2.5, score))
            comment = data.get("comment", "Yechim qabul qilindi.")
            return score, comment
        except Exception:
            pass
    return 2.0, "Yechim rasmi qabul qilindi va baholandi."

async def ai_solve_photo_problem(file_bytes: bytes, mime_type: str) -> str:
    b64_data = base64.b64encode(file_bytes).decode("utf-8")
    prompt = (
        "Sen A+ Kimyo maktabining tajribali ustozi Azizbek Ibrohimovning yordamchisan. "
        "Rasmdagi kimyo masalasini yoki test savolini o'zbek tilida eng oson, mantiqiy usulda "
        "bosqichma-bosqich yechib, yakunida aniq to'g'ri javobni ko'rsatib ber. "
        "MUHIM: Formulalarda hech qanday LaTeX ($...$, \\rightarrow) ishlatma! Oddiy H₂SO₄, → belgilaridan foydalan."
    )
    ok, res_text = await call_gemini_api(prompt, b64_data, mime_type, json_mode=False, timeout_sec=90)
    if ok:
        return clean_ai_text_for_telegram(res_text)
    return f"❌ Rasmni tahlil qilishda xatolik: {html.escape(res_text)}"

# -------------------------------------------------------------
# JAVOBLARNI TEKSHIRISH VA BALL HISOBLASH
# -------------------------------------------------------------
def parse_input_answers(raw_text: str, test_type: str) -> dict:
    text = raw_text.strip()
    answers = {}
    pairs = re.findall(r"(\d{1,2})\s*[-:=.)]?\s*([A-Za-z0-9.,/+-]+)", text)
    if len(pairs) >= 1:
        for q_num, ans_val in pairs:
            q_str = str(int(q_num))
            answers[q_str] = ans_val.strip().upper()
        return answers

    clean_letters = re.sub(r"[^A-Fa-f]", "", text).upper()
    max_q = 30 if test_type == "30_talik" else (90 if test_type == "90_dtm" else 35)
    if len(clean_letters) >= 3:
        for idx, ch in enumerate(clean_letters[:max_q], start=1):
            answers[str(idx)] = ch

    return answers

def evaluate_student_submission(test_type: str, correct_keys: dict, student_ans: dict, written_scores: dict = None) -> dict:
    mistakes = []
    correct_count = 0
    written_scores = written_scores or {}

    if test_type == "30_talik":
        total_q = len(correct_keys) or 30
        for q in range(1, total_q + 1):
            q_str = str(q)
            k_val = str(correct_keys.get(q_str, "")).strip().upper()
            s_val = str(student_ans.get(q_str, "")).strip().upper()
            if not k_val:
                continue
            if s_val == k_val:
                correct_count += 1
            else:
                mistakes.append(f"{q_str}-savol (Siz: {s_val or '—'} | Kalit: {k_val})")

        score = round(correct_count * 3.1, 1)
        percent = round((correct_count / total_q) * 100, 1) if total_q else 0
        grade = "A'lo (Yuqori) 🏆" if percent >= 85 else ("Yaxshi 🎯" if percent >= 65 else "Qoniqarli 📚")

        summary = (
            f"📋 <b>30 TALIK TEST NATIJASI:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ To'g'ri javoblar: <b>{correct_count} / {total_q} ta</b>\n"
            f"📊 Ko'rsatkich: <b>{percent}%</b>\n"
            f"💎 To'plangan ball: <b>{score} / 93.0 ball</b>\n"
            f"🏅 Daraja: <b>{grade}</b>"
        )
        return {"correct_count": correct_count, "total_score": score, "grade": grade, "summary": summary, "mistakes": mistakes}

    elif test_type == "90_dtm":
        b1, b2, b3 = 0, 0, 0
        for q in range(1, 91):
            qs = str(q)
            k_val = str(correct_keys.get(qs, "")).strip().upper()
            s_val = str(student_ans.get(qs, "")).strip().upper()
            if not k_val:
                continue
            if s_val == k_val:
                correct_count += 1
                if 1 <= q <= 30: b1 += 1
                elif 31 <= q <= 60: b2 += 1
                else: b3 += 1
            else:
                mistakes.append(f"{q}:{s_val or '—'}({k_val})")

        b1_s = round(b1 * 1.1, 1)
        b2_s = round(b2 * 3.1, 1)
        b3_s = round(b3 * 2.1, 1)
        total_score = round(b1_s + b2_s + b3_s, 1)
        grade = "Davlat Granti 🏆" if total_score >= 150 else ("Kontrakt 🎯" if total_score >= 100 else "Tayyorgarlik kerak 📚")

        summary = (
            f"🏛 <b>90 TALIK DTM BLOK TEST:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"1️⃣ Majburiy (1–30): {b1}/30 = <b>{b1_s} ball</b>\n"
            f"2️⃣ 1-Fan (31–60): {b2}/30 = <b>{b2_s} ball</b>\n"
            f"3️⃣ 2-Fan (61–90): {b3}/30 = <b>{b3_s} ball</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Jami to'g'ri: <b>{correct_count}/90 ta</b>\n"
            f"🔥 <b>UMUMIY BALL: {total_score} / 189.0</b>"
        )
        return {"correct_count": correct_count, "total_score": total_score, "grade": grade, "summary": summary, "mistakes": mistakes}

    else:
        p1, p2, p3 = 0, 0, 0
        weighted = 0.0
        for q in range(1, 41):
            qs = str(q)
            k_val = str(correct_keys.get(qs, "")).strip().upper().replace(",", ".")
            s_val = str(student_ans.get(qs, "")).strip().upper().replace(",", ".")
            if not k_val:
                continue
            if s_val == k_val:
                correct_count += 1
                if 1 <= q <= 32: p1 += 1; weighted += 1.5
                elif 33 <= q <= 35: p2 += 1; weighted += 2.0
                elif 36 <= q <= 40: p3 += 1; weighted += 2.4
            else:
                mistakes.append(f"{q}-savol (Siz: {s_val or '—'} | Kalit: {k_val})")

        # 41, 42, 43 yozma ish ballari (rasm orqali)
        w41 = float(written_scores.get("41", 0.0))
        w42 = float(written_scores.get("42", 0.0))
        w43 = float(written_scores.get("43", 0.0))
        written_total = round(w41 + w42 + w43, 1)
        for q_w, val_w in [("41", w41), ("42", w42), ("43", w43)]:
            if val_w >= 1.5:
                correct_count += 1

        weighted += written_total * 1.4
        rasch = 0.0 if (correct_count == 0 and written_total == 0) else round(min(75.0, 24.0 + weighted * 0.68), 1)
        grade = (
            "A+ Daraja 🏆" if rasch >= 70 else
            "A Daraja 🥇" if rasch >= 65 else
            "B+ Daraja 🥈" if rasch >= 60 else
            "B Daraja 🥈" if rasch >= 55 else
            "C+ Daraja 🥉" if rasch >= 50 else
            "C Daraja 🎗" if rasch >= 46 else "Sertifikatsiz ❌"
        )

        summary = (
            f"🎯 <b>43 TALIK MILLIY SERTIFIKAT (MOCK):</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 1–32 (Yopiq A-D): <b>{p1} / 32 ta</b>\n"
            f"🔸 33–35 (Moslashtirish A-F): <b>{p2} / 3 ta</b>\n"
            f"🔢 36–40 (Ochiq javoblar): <b>{p3} / 5 ta</b>\n"
            f"📸 41–43 (Yozma ish rasmlari): <b>{written_total} / 7.5 ball</b>\n"
            f"   ├ 41-masala: <b>{w41} ball</b>\n"
            f"   ├ 42-masala: <b>{w42} ball</b>\n"
            f"   └ 43-masala: <b>{w43} ball</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 <b>Yakuniy Rasch Bali: {rasch} ball</b>\n"
            f"🏅 <b>Sertifikat Darajasi: {grade}</b>"
        )
        return {"correct_count": correct_count, "total_score": rasch, "grade": grade, "summary": summary, "mistakes": mistakes}

# -------------------------------------------------------------
# INTERAKTIV ELEKTRON TITUL VARAQASI GENERATORI
# -------------------------------------------------------------
def build_electronic_sheet_kb(test_type: str, answers: dict, page: int = 1, written_photos: dict = None) -> InlineKeyboardMarkup:
    written_photos = written_photos or {}
    rows = []

    if test_type == "30_talik":
        per_page = 10
        total_pages = 3
        start_q = (page - 1) * per_page + 1
        end_q = start_q + per_page - 1

        for q in range(start_q, end_q + 1):
            qs = str(q)
            cur = answers.get(qs, "")
            btn_row = [InlineKeyboardButton(text=f"№{q}", callback_data="noop")]
            for opt in ["A", "B", "C", "D"]:
                lbl = f"✅{opt}" if cur == opt else opt
                btn_row.append(InlineKeyboardButton(text=lbl, callback_data=f"ebtn:{q}:{opt}:{page}"))
            rows.append(btn_row)

        nav = []
        for p in range(1, total_pages + 1):
            lbl = f"📍 {p}-bet" if p == page else f"{p}-bet ({(p-1)*10+1}-{p*10})"
            nav.append(InlineKeyboardButton(text=lbl, callback_data=f"epage:{p}"))
        rows.append(nav)

    elif test_type == "90_dtm":
        per_page = 10
        total_pages = 9
        start_q = (page - 1) * per_page + 1
        end_q = start_q + per_page - 1

        for q in range(start_q, end_q + 1):
            qs = str(q)
            cur = answers.get(qs, "")
            btn_row = [InlineKeyboardButton(text=f"№{q}", callback_data="noop")]
            for opt in ["A", "B", "C", "D"]:
                lbl = f"✅{opt}" if cur == opt else opt
                btn_row.append(InlineKeyboardButton(text=lbl, callback_data=f"ebtn:{q}:{opt}:{page}"))
            rows.append(btn_row)

        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"epage:{page-1}"))
        nav.append(InlineKeyboardButton(text=f"📄 {page}/9 bet", callback_data="noop"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"epage:{page+1}"))
        rows.append(nav)

    else:
        # 43_ms:
        # Page 1: 1-10 (A-D)
        # Page 2: 11-20 (A-D)
        # Page 3: 21-32 (A-D)
        # Page 4: 33-35 (A-F) + 36-40 (Yozma son) + 41-43 (Rasm yuklash)
        if page in [1, 2, 3]:
            ranges = {1: (1, 10), 2: (11, 20), 3: (21, 32)}
            start_q, end_q = ranges[page]
            for q in range(start_q, end_q + 1):
                qs = str(q)
                cur = answers.get(qs, "")
                btn_row = [InlineKeyboardButton(text=f"№{q}", callback_data="noop")]
                for opt in ["A", "B", "C", "D"]:
                    lbl = f"✅{opt}" if cur == opt else opt
                    btn_row.append(InlineKeyboardButton(text=lbl, callback_data=f"ebtn:{q}:{opt}:{page}"))
                rows.append(btn_row)
        else:
            # 33-35 (A-F)
            for q in range(33, 36):
                qs = str(q)
                cur = answers.get(qs, "")
                rows.append([InlineKeyboardButton(text=f"🔸 {q}-savol (Moslashtirish A–F):", callback_data="noop")])
                btn_row = []
                for opt in ["A", "B", "C", "D", "E", "F"]:
                    lbl = f"✅{opt}" if cur == opt else opt
                    btn_row.append(InlineKeyboardButton(text=lbl, callback_data=f"ebtn:{q}:{opt}:4"))
                rows.append(btn_row)

            # 36-40 Ochiq savollar
            rows.append([InlineKeyboardButton(text="🔢 36–40 Ochiq savollar (Qiymat kiritish):", callback_data="noop")])
            open_row = []
            for q in range(36, 41):
                qs = str(q)
                cur = answers.get(qs, "")
                lbl = f"✅{q}:{cur}" if cur else f"✍️ {q}-savol"
                open_row.append(InlineKeyboardButton(text=lbl, callback_data=f"eopen:{q}"))
                if len(open_row) == 3:
                    rows.append(open_row)
                    open_row = []
            if open_row:
                rows.append(open_row)

            # 41, 42, 43 Rasm yuklash
            rows.append([InlineKeyboardButton(text="📸 41–43 Yozma masalalar rasmini yuklash:", callback_data="noop")])
            for q in [41, 42, 43]:
                qs = str(q)
                has_img = qs in written_photos
                lbl = f"✅ {q}-masala rasmi yuklandi (Almashtirish)" if has_img else f"📷 {q}-masala yechimi rasmini yuklash"
                rows.append([InlineKeyboardButton(text=lbl, callback_data=f"ephoto:{q}")])

        nav = [
            InlineKeyboardButton(text="📍1-10" if page == 1 else "1-10", callback_data="epage:1"),
            InlineKeyboardButton(text="📍11-20" if page == 2 else "11-20", callback_data="epage:2"),
            InlineKeyboardButton(text="📍21-32" if page == 3 else "21-32", callback_data="epage:3"),
            InlineKeyboardButton(text="📍33-43 (Ochiq/Rasm)" if page == 4 else "33-43 (Ochiq/Rasm)", callback_data="epage:4"),
        ]
        rows.append(nav)

    filled_cnt = len(answers) + len(written_photos)
    rows.append([InlineKeyboardButton(text=f"🚀 TESTNI YAKUNLASH VA TEKSHIRISH ({filled_cnt} ta belgilandi)", callback_data="efinish")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# -------------------------------------------------------------
# FSM STATE HOLATLARI
# -------------------------------------------------------------
class StudentTestSolve(StatesGroup):
    waiting_test_code = State()
    in_electronic_exam = State()
    waiting_open_answer = State()
    waiting_written_photo = State()

class AISolveProblem(StatesGroup):
    waiting_problem_photo = State()

class UserTestCreate(StatesGroup):
    waiting_test_type = State()
    waiting_title = State()
    waiting_file_or_keys = State()

class AdminPanel(StatesGroup):
    waiting_gemini_key = State()
    waiting_delete_code = State()

# -------------------------------------------------------------
# ZAMONAVIY INTERFEYS VA MENYULAR
# -------------------------------------------------------------
def main_menu(user_id: int = 0):
    kb = [
        [
            KeyboardButton(text="📲 Elektron Test Ishlash (Mock)"),
            KeyboardButton(text="➕ Test Yaratish (Barcha uchun)")
        ],
        [
            KeyboardButton(text="📋 Faol Testlar Baza"),
            KeyboardButton(text="🏆 Reyting & Natijalar")
        ],
        [
            KeyboardButton(text="🤖 AI Masala Yechish (Rasm)"),
            KeyboardButton(text="👨‍🏫 Ustoz & Bog'lanish")
        ]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="👑 Admin Boshqaruv Paneli")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def exam_active_reply_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Elektron Titulni Qayta Ochish")],
            [KeyboardButton(text="🛑 Testni Bekor Qilish (Chiqish)")]
        ],
        resize_keyboard=True
    )

# -------------------------------------------------------------
# START VA OBUNA
# -------------------------------------------------------------
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    ACTIVE_EXAM_SESSIONS.pop(uid, None)
    await state.clear()

    name = message.from_user.full_name or "O'quvchi"
    username = f"@{message.from_user.username}" if message.from_user.username else ""
    db_add_user(uid, name, username)

    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    text = (
        f"✨ Assalomu alaykum, <b>{html.escape(name)}</b>!\n\n"
        f"🧪 <b>A+ KIMYO | ELEKTRON MOCK VA AI PLATFORMASI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔹 <b>📲 Elektron Test Ishlash</b> — interaktiv tugmalar orqali titul belgilash va 41, 42, 43-masalalar rasmini yuklash;\n"
        f"🔹 <b>➕ Test Yaratish</b> — har bir o'quvchi va ustoz o'z testini (30 / 43 / 90) yarata oladi;\n"
        f"🔹 <b>🤖 AI Masala Yechish</b> — tushunmagan masalalarni rasm orqali yechish <i>(Mock test paytida avtomatik bloklanadi!)</i>.\n\n"
        f"Kerakli bo'limni tanlang 👇"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu(uid))

@dp.callback_query(F.data == "btn_check_sub")
async def cb_check_sub(callback: types.CallbackQuery):
    uid = callback.from_user.id
    if await check_channel_subscription(uid):
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(
            "🎉 <b>Obunangiz tasdiqlandi! Marhamat, botdan foydalaning:</b>",
            parse_mode="HTML",
            reply_markup=main_menu(uid)
        )
    else:
        await callback.answer("❌ Siz hali kanalga a'zo bo'lmadingiz!", show_alert=True)

@dp.callback_query(F.data == "noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()

@dp.message(F.text.in_(["❌ Bekor qilish", "🛑 Testni Bekor Qilish (Chiqish)"]))
async def cancel_any_state(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    ACTIVE_EXAM_SESSIONS.pop(uid, None)
    await state.clear()
    await message.answer("✅ Jarayon bekor qilindi. Bosh menyudasiz:", reply_markup=main_menu(uid))

# -------------------------------------------------------------
# BARCHA UCHUN OCHIQ TEST YARATISH BO'LIMI
# -------------------------------------------------------------
@dp.message(F.text == "➕ Test Yaratish (Barcha uchun)")
async def user_start_test_create(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid in ACTIVE_EXAM_SESSIONS:
        await message.answer("⛔️ Siz hozir Mock test ishlayapsiz! Avval testni yakunlang.")
        return

    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 1. 30 talik Test (Standart)", callback_data="create_t:30_talik")],
            [InlineKeyboardButton(text="🎯 2. 43 talik Milliy Sertifikat (Mock + 41-43 Rasm)", callback_data="create_t:43_ms")],
            [InlineKeyboardButton(text="🏛 3. 90 talik DTM Blok Testi", callback_data="create_t:90_dtm")]
        ]
    )
    await message.answer(
        "➕ <b>YANGI TEST YARATISH BO'LIMI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "O'zingiz yoki guruhingiz uchun yangi test yaratishingiz mumkin.\n"
        "Qaysi formatdagi testni yaratmoqchisiz? Tanlang 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(F.data.startswith("create_t:"))
async def cb_select_create_type(callback: types.CallbackQuery, state: FSMContext):
    test_type = callback.data.split(":")[1]
    await state.update_data(test_type=test_type)
    await state.set_state(UserTestCreate.waiting_title)

    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    await callback.message.answer(
        "✏️ <b>Test nomini kiriting</b>\n"
        "<i>(Masalan: «Kimyo MS 1-variant» yoki «Organika 30 talik»)</i>:",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    await callback.answer()

@dp.message(UserTestCreate.waiting_title)
async def process_test_title(message: types.Message, state: FSMContext):
    title = (message.text or "").strip()
    if len(title) < 2:
        await message.answer("⚠️ Iltimos, test nomini to'g'ri yozing:")
        return

    await state.update_data(title=title)
    await state.set_state(UserTestCreate.waiting_file_or_keys)

    await message.answer(
        f"📚 Test nomi: <b>{html.escape(title)}</b>\n\n"
        "📤 Endi quyidagilardan birini yuboring:\n"
        "1️⃣ <b>Kalitlarni matn ko'rinishida:</b>\n"
        "   <code>1A 2B 3C 4D ...</code> yoki <code>ABCD...</code>\n"
        "2️⃣ Yoki <b>Test savollari PDF/Rasmini</b> yuboring — AI o'zi yechib kalit tuzadi!",
        parse_mode="HTML"
    )

@dp.message(UserTestCreate.waiting_file_or_keys)
async def handle_user_test_upload(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    data = await state.get_data()
    test_type = data.get("test_type", "30_talik")
    title = data.get("title", "Maxsus Test")
    prefix = "TEST" if test_type == "30_talik" else ("MS" if test_type == "43_ms" else "DTM")
    test_code = f"{prefix}-{datetime.now().strftime('%d%H%M%S')[-5:]}"

    if message.text:
        parsed_keys = parse_input_answers(message.text, test_type)
        if not parsed_keys:
            await message.answer(
                "⚠️ Kalitlarni o'qib bo'lmadi.\n"
                "Masalan: <code>1A 2B 3C 4D...</code> ko'rinishida yozib yuboring.",
                parse_mode="HTML"
            )
            return
        db_save_test(test_code, test_type, title, parsed_keys, creator_id=uid)
        await state.clear()
        await message.answer(
            f"🎉 <b>YANGI TEST MUVAFFAQIYATLI YARATILDI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔑 Test kodi: <code>{test_code}</code>\n"
            f"📚 Nomi: <b>{html.escape(title)}</b>\n"
            f"🔢 Savollar soni: <b>{len(parsed_keys)} ta</b>\n\n"
            f"👉 O'quvchilar <b>«📲 Elektron Test Ishlash (Mock)»</b> bo'limiga kirib, <code>{test_code}</code> kodini kiritish orqali elektron titulda yechishlari mumkin!",
            parse_mode="HTML",
            reply_markup=main_menu(uid)
        )
        return

    file_id = message.document.file_id if message.document else (message.photo[-1].file_id if message.photo else "")
    file_type = "document" if message.document else ("photo" if message.photo else "")
    mime_type = message.document.mime_type if message.document else "image/jpeg"

    if not file_id:
        await message.answer("❗️ Iltimos, kalitlarni matn qilib yozing yoki PDF/Rasm yuboring.")
        return

    wait_msg = await message.answer("🤖 AI faylni o'qib, savollar kalitini tuzmoqda, kuting...")
    try:
        tg_file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=buf)
        file_bytes = buf.getvalue()
    except Exception as e:
        await wait_msg.edit_text(f"❌ Yuklashda xato: {e}")
        return

    ai_result = await ai_analyze_test_document(file_bytes, mime_type, test_type)
    if "error" in ai_result:
        err_clean = html.escape(str(ai_result["error"]))
        await wait_msg.edit_text(
            f"⚠️ <b>AI faylni o'qiy olmadi:</b> {err_clean}\n\n"
            "💡 <i>Iltimos, test kalitlarini oddiy matn ko'rinishida (1A 2B 3C...) yozib yuboring!</i>",
            parse_mode="HTML"
        )
        return

    keys_dict = ai_result.get("keys", {})
    explanation = ai_result.get("explanation", "")
    db_save_test(test_code, test_type, title, keys_dict, explanation, file_id, file_type, creator_id=uid)
    await state.clear()
    await wait_msg.delete()

    await message.answer(
        f"🎉 <b>AI YORDAMIDA TEST YARATILDI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Test kodi: <code>{test_code}</code>\n"
        f"📚 Nomi: <b>{html.escape(title)}</b>\n"
        f"🔢 Topilgan kalitlar: <b>{len(keys_dict)} ta</b>\n\n"
        f"👉 Endi <b>«📲 Elektron Test Ishlash (Mock)»</b> tugmasi orqali <code>{test_code}</code> kodini terib ishlash mumkin!",
        parse_mode="HTML",
        reply_markup=main_menu(uid)
    )

# -------------------------------------------------------------
# ELEKTRON TEST ISHLASH (MOCK REJIMI + 41, 42, 43 RASM)
# -------------------------------------------------------------
@dp.message(F.text == "📋 Faol Testlar Baza")
async def show_active_tests_list(message: types.Message):
    uid = message.from_user.id
    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    recent = db_get_recent_tests(12)
    if not recent:
        await message.answer("📭 Hozircha faol testlar yo'q. «➕ Test Yaratish» tugmasi orqali birinchi testni qo'shing!")
        return

    kb_rows = []
    lines = ["📋 <b>FAOL TESTLAR RO'YXATI:</b>\n━━━━━━━━━━━━━━━━━━━━━━━━"]
    for r_code, r_type, r_title, _ in recent:
        badge = "30 talik" if r_type == "30_talik" else ("43 MS Mock" if r_type == "43_ms" else "90 DTM")
        lines.append(f"🔹 <code>{r_code}</code> — <b>{html.escape(r_title)}</b> <i>({badge})</i>")
        kb_rows.append([InlineKeyboardButton(text=f"📲 Elektron Yechish: {r_code} ({r_title[:18]})", callback_data=f"solve_now:{r_code}")])

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

@dp.message(F.text == "📲 Elektron Test Ishlash (Mock)")
async def start_electronic_test_menu(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    await state.set_state(StudentTestSolve.waiting_test_code)
    cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)

    recent = db_get_recent_tests(5)
    inline_kb = None
    if recent:
        rows = [[InlineKeyboardButton(text=f"📲 {c} — {t}", callback_data=f"solve_now:{c}")] for c, _, t, _ in recent]
        inline_kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await message.answer(
        "📲 <b>ELEKTRON TEST TEKSHIRISH VA MOCK BO'LIMI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔑 Test kodini yozib yuboring <i>(masalan: <code>MS-12345</code>)</i>:",
        parse_mode="HTML",
        reply_markup=cancel_kb
    )
    if inline_kb:
        await message.answer("Yoki oxirgi qo'shilgan testlardan birini tanlang 👇", reply_markup=inline_kb)

@dp.callback_query(F.data.startswith("solve_now:"))
async def cb_solve_test_now(callback: types.CallbackQuery, state: FSMContext):
    code = callback.data.split(":")[1]
    row = db_get_test(code)
    if not row:
        await callback.answer("❌ Test topilmadi!", show_alert=True)
        return
    await callback.answer()
    await launch_electronic_exam(callback.message, callback.from_user.id, state, row)

@dp.message(StudentTestSolve.waiting_test_code)
async def process_code_for_exam(message: types.Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    row = db_get_test(code)
    if not row:
        await message.answer(f"❌ <code>{html.escape(code)}</code> kodli test topilmadi. Qaytadan kiriting:", parse_mode="HTML")
        return
    await launch_electronic_exam(message, message.from_user.id, state, row)

async def launch_electronic_exam(message: types.Message, user_id: int, state: FSMContext, row: tuple):
    test_code, test_type, title, _, _, file_id, file_type = row

    # Mock test boshlandi -> AI yordamchini ushbu foydalanuvchi uchun bloklaymiz!
    ACTIVE_EXAM_SESSIONS[user_id] = test_code

    await state.update_data(
        active_test_code=test_code,
        active_test_type=test_type,
        active_test_title=title,
        e_answers={},
        written_photos={},
        written_scores={},
        current_page=1
    )
    await state.set_state(StudentTestSolve.in_electronic_exam)

    if file_id:
        try:
            if file_type == "document":
                await bot.send_document(message.chat.id, file_id, caption=f"📄 {title} ({test_code})")
            elif file_type == "photo":
                await bot.send_photo(message.chat.id, file_id, caption=f"🖼 {title} ({test_code})")
        except Exception:
            pass

    await message.answer(
        f"🔒 <b>MOCK IMTIHON REJIMI FAOL!</b>\n"
        f"Test ishlayotgan vaqtingizda <b>«🤖 AI Masala Yechish»</b> bo'limi avtomatik ravishda bloklandi.\n"
        f"Quyi menyudan foydalanib titulni boshqarishingiz mumkin 👇",
        parse_mode="HTML",
        reply_markup=exam_active_reply_kb()
    )

    kb = build_electronic_sheet_kb(test_type, {}, page=1, written_photos={})
    await message.answer(
        f"📲 <b>ELEKTRON JAVOBLAR VARAQASI (TITUL)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📚 Test: <b>{html.escape(title)}</b> (<code>{test_code}</code>)\n"
        f"📌 Tugmalar ustiga bosib javoblaringizni belgilang.\n"
        f"<i>(43 talik MS testida 4-betga o'tib 36–40-savollarni yozishingiz va 41, 42, 43-masalalarning yechim rasmini yuklashingiz mumkin!)</i>",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.message(F.text == "📋 Elektron Titulni Qayta Ochish")
async def reopen_electronic_sheet(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_code = data.get("active_test_code")
    if not test_code:
        await message.answer("Sizda faol test yo'q.", reply_markup=main_menu(message.from_user.id))
        return

    test_type = data.get("active_test_type", "30_talik")
    title = data.get("active_test_title", "Test")
    ans = data.get("e_answers", {})
    w_photos = data.get("written_photos", {})
    page = data.get("current_page", 1)

    kb = build_electronic_sheet_kb(test_type, ans, page=page, written_photos=w_photos)
    await message.answer(
        f"📲 <b>ELEKTRON TITUL: {html.escape(title)}</b> (<code>{test_code}</code>)\n"
        f"✅ Belgilangan javoblar: <b>{len(ans)} ta</b> | 📸 Rasmlar: <b>{len(w_photos)}/3 ta</b>",
        parse_mode="HTML",
        reply_markup=kb
    )

# Tugma bosilganda (A, B, C, D, E, F)
@dp.callback_query(F.data.startswith("ebtn:"))
async def cb_electronic_mark(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    q_num, opt, page = parts[1], parts[2], int(parts[3])

    data = await state.get_data()
    if not data.get("active_test_code"):
        await callback.answer("Bu test yakunlangan!", show_alert=True)
        return

    ans = data.get("e_answers", {})
    # Agar yana o'sha harfni bossa o'chiradi, bo'lmasa belgilaydi
    if ans.get(q_num) == opt:
        ans.pop(q_num, None)
    else:
        ans[q_num] = opt

    await state.update_data(e_answers=ans, current_page=page)
    kb = build_electronic_sheet_kb(data.get("active_test_type", "30_talik"), ans, page=page, written_photos=data.get("written_photos", {}))
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer(f"{q_num}-savol: {opt}")

# Sahifani almashtirish
@dp.callback_query(F.data.startswith("epage:"))
async def cb_electronic_page(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split(":")[1])
    data = await state.get_data()
    if not data.get("active_test_code"):
        await callback.answer("Bu test yakunlangan!", show_alert=True)
        return

    await state.update_data(current_page=page)
    kb = build_electronic_sheet_kb(
        data.get("active_test_type", "30_talik"),
        data.get("e_answers", {}),
        page=page,
        written_photos=data.get("written_photos", {})
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await callback.answer(f"{page}-sahifa")

# 36-40 Ochiq savolga yozma javob kiritish
@dp.callback_query(F.data.startswith("eopen:"))
async def cb_open_question_input(callback: types.CallbackQuery, state: FSMContext):
    q_num = callback.data.split(":")[1]
    await state.update_data(editing_open_q=q_num)
    await state.set_state(StudentTestSolve.waiting_open_answer)
    await callback.message.answer(
        f"✍️ <b>{q_num}-ochiq savol</b> uchun javobingizni (son yoki harf) yozib yuboring:",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(StudentTestSolve.waiting_open_answer)
async def receive_open_question_answer(message: types.Message, state: FSMContext):
    val = (message.text or "").strip().upper()
    data = await state.get_data()
    q_num = data.get("editing_open_q", "36")
    ans = data.get("e_answers", {})
    ans[str(q_num)] = val
    await state.update_data(e_answers=ans, current_page=4)
    await state.set_state(StudentTestSolve.in_electronic_exam)

    kb = build_electronic_sheet_kb(
        data.get("active_test_type", "43_ms"),
        ans,
        page=4,
        written_photos=data.get("written_photos", {})
    )
    await message.answer(
        f"✅ <b>{q_num}-savol javobi ({html.escape(val)}) saqlandi!</b>\n"
        f"Davom etishingiz mumkin 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

# 41, 42, 43-savollar uchun rasm yuklash
@dp.callback_query(F.data.startswith("ephoto:"))
async def cb_upload_written_photo(callback: types.CallbackQuery, state: FSMContext):
    q_num = callback.data.split(":")[1]
    await state.update_data(uploading_photo_q=q_num)
    await state.set_state(StudentTestSolve.waiting_written_photo)
    await callback.message.answer(
        f"📸 <b>{q_num}-masala yechimi tushirilgan rasmni yuboring!</b>\n"
        f"<i>(Daftardagi yechimingizni aniq qilib rasmga olib shu yerga tashlang)</i> 👇",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(StudentTestSolve.waiting_written_photo, F.photo)
async def receive_written_solution_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q_num = str(data.get("uploading_photo_q", "41"))
    file_id = message.photo[-1].file_id

    wait = await message.answer(f"⏳ <b>{q_num}-masala yechimi rasmi tekshirilmoqda va saqlanmoqda...</b>", parse_mode="HTML")

    score_val = 2.0
    comment = "Qabul qilindi"
    try:
        tg_file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=buf)
        score_val, comment = await ai_grade_written_work(buf.getvalue(), int(q_num))
    except Exception:
        pass

    w_photos = data.get("written_photos", {})
    w_scores = data.get("written_scores", {})
    w_photos[q_num] = file_id
    w_scores[q_num] = score_val

    await state.update_data(written_photos=w_photos, written_scores=w_scores, current_page=4)
    await state.set_state(StudentTestSolve.in_electronic_exam)
    await wait.delete()

    # Ustozga (Adminga) ham o'quvchining 41-43 yechim rasmini yuborib qo'yamiz
    test_code = data.get("active_test_code", "MS")
    try:
        await bot.send_photo(
            ADMIN_ID,
            file_id,
            caption=(
                f"📸 <b>Yozma ish yechimi ({q_num}-masala)</b>\n"
                f"👤 O'quvchi: {html.escape(message.from_user.full_name)}\n"
                f"🔑 Test: <code>{test_code}</code>\n"
                f"🤖 AI bahosi: <b>{score_val} / 2.5 ball</b> ({html.escape(comment)})"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    kb = build_electronic_sheet_kb(
        data.get("active_test_type", "43_ms"),
        data.get("e_answers", {}),
        page=4,
        written_photos=w_photos
    )
    await message.answer(
        f"✅ <b>{q_num}-masala yechimi rasmi yuklandi!</b>\n"
        f"📊 Dastlabki baho: <b>{score_val} / 2.5 ball</b>\n"
        f"💬 Izoh: <i>{html.escape(comment)}</i>\n\n"
        f"Titulda davom eting yoki yakunlang 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.message(StudentTestSolve.waiting_written_photo)
async def receive_written_photo_invalid(message: types.Message):
    await message.answer("⚠️ Iltimos, yechimingizni **rasm (foto)** ko'rinishida yuboring!")

# Testni yakunlash
@dp.callback_query(F.data == "efinish")
async def cb_finish_electronic_exam(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    data = await state.get_data()
    code = data.get("active_test_code")
    if not code:
        await callback.answer("Test allaqachon yakunlangan!", show_alert=True)
        return

    test_type = data.get("active_test_type", "30_talik")
    w_photos = data.get("written_photos", {})

    # Agar 43 talik MS bo'lsa va 41, 42, 43 rasmlari yuklanmagan bo'lsa ogohlantiramiz (lekin 2-marta bossa yakunlaydi)
    if test_type == "43_ms" and len(w_photos) < 3 and not data.get("warned_missing_photos"):
        missing = [str(q) for q in [41, 42, 43] if str(q) not in w_photos]
        await state.update_data(warned_missing_photos=True)
        await callback.answer(
            f"⚠️ Diqqat! Siz {', '.join(missing)}-masalalar yechimi rasmini yuklamadingiz! "
            f"4-betga o'tib rasm yuklang yoki rasmsiz yakunlash uchun tugmani yana bir marta bosing.",
            show_alert=True
        )
        return

    row = db_get_test(code)
    ACTIVE_EXAM_SESSIONS.pop(uid, None)
    await state.clear()

    if not row:
        await callback.message.answer("❌ Test bazadan topilmadi.", reply_markup=main_menu(uid))
        return

    _, test_type, title, keys_json, _, _, _ = row
    correct_keys = json.loads(keys_json)
    student_ans = data.get("e_answers", {})
    w_scores = data.get("written_scores", {})

    res = evaluate_student_submission(test_type, correct_keys, student_ans, written_scores=w_scores)
    w_total = sum(float(v) for v in w_scores.values())
    db_save_result(
        code,
        uid,
        callback.from_user.full_name or "O'quvchi",
        res["correct_count"],
        res["total_score"],
        res["grade"],
        written_score=w_total
    )

    mistakes_str = "\n".join(res["mistakes"][:25]) if res["mistakes"] else "🎉 Barcha belgilangan test javoblari 100% to'g'ri!"
    report = (
        f"{res['summary']}\n\n"
        f"📋 <b>Tahlil va Xatolar:</b>\n"
        f"{html.escape(mistakes_str)}\n\n"
        f"🔓 <i>Mock imtihon yakunlandi! Endi «🤖 AI Masala Yechish» bo'limidan yana foydalanishingiz mumkin.</i>"
    )
    await callback.message.answer(report, parse_mode="HTML", reply_markup=main_menu(uid))
    await callback.answer("🎉 Natijangiz hisoblandi!")

# Agar o'quvchi titul ichida turib matn orqali ham javob yozib yuborsa (1A 2B...)
@dp.message(StudentTestSolve.in_electronic_exam, F.text)
async def quick_text_fill_in_exam(message: types.Message, state: FSMContext):
    data = await state.get_data()
    test_type = data.get("active_test_type", "30_talik")
    parsed = parse_input_answers(message.text or "", test_type)
    if not parsed:
        await message.answer(
            "💡 Tugmalar orqali belgilang yoki <code>1A 2B 3C...</code> ko'rinishida yozing.",
            parse_mode="HTML"
        )
        return

    ans = data.get("e_answers", {})
    ans.update(parsed)
    await state.update_data(e_answers=ans)
    kb = build_electronic_sheet_kb(test_type, ans, page=data.get("current_page", 1), written_photos=data.get("written_photos", {}))
    await message.answer(
        f"✅ <b>{len(parsed)} ta javob elektron titulga avtomatik joylandi!</b>\n"
        f"Tekshirib, yakunlash tugmasini bosing 👇",
        parse_mode="HTML",
        reply_markup=kb
    )

# -------------------------------------------------------------
# REYTING VA NATIJALAR
# -------------------------------------------------------------
@dp.message(F.text == "🏆 Reyting & Natijalar")
async def show_rating_menu(message: types.Message):
    if not await check_channel_subscription(message.from_user.id):
        await prompt_subscription(message)
        return
    recent = db_get_recent_tests(10)
    if not recent:
        await message.answer("📭 Hozircha natijalar yo'q.")
        return
    kb = [[InlineKeyboardButton(text=f"🏆 {r_code} — {r_title}", callback_data=f"rating:{r_code}")] for r_code, _, r_title, _ in recent]
    await message.answer("🏆 <b>Qaysi testning reyting jadvalini ko'rmoqchisiz?</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("rating:"))
async def cb_rating(callback: types.CallbackQuery):
    code = callback.data.split(":")[1]
    top = db_get_top_results(code, 20)
    if not top:
        await callback.answer("Bu test bo'yicha hali natijalar yo'q!", show_alert=True)
        return
    lines = [f"🏆 <b>{html.escape(code)} BO'YICHA TOP NATIJALAR:</b>\n━━━━━━━━━━━━━━━━━━━━━━━━"]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for i, (name, corr, score, grade) in enumerate(top, 1):
        m = medals.get(i, f"{i}.")
        lines.append(f"{m} <b>{html.escape(name)}</b> — <b>{score} ball</b> ({corr} ta | {grade})")
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()

# -------------------------------------------------------------
# AI MASALA YECHISH (MOCK TEST PAYTIDA QAT'IY BLOKLANADI!)
# -------------------------------------------------------------
@dp.message(F.text == "🤖 AI Masala Yechish (Rasm)")
async def start_ai_solver(message: types.Message, state: FSMContext):
    uid = message.from_user.id

    # QAT'IY CHEKLOV: Agar o'quvchi Mock test ishlayotgan bo'lsa, AI masalani ishlamaydi!
    if uid in ACTIVE_EXAM_SESSIONS:
        active_code = ACTIVE_EXAM_SESSIONS[uid]
        await message.answer(
            f"⛔️ <b>DIQQAT! IMTIHON TARTIBI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Siz hozir <code>{active_code}</code> kodli <b>Mock testni</b> ishlayapsiz!\n"
            f"Adolatli sinov qoidalariga binoan, test yakunlanmaguncha <b>AI Masala Yechish</b> bo'limi ishlamaydi.\n\n"
            f"👉 Avval elektron titulda testni yakunlang!",
            parse_mode="HTML",
            reply_markup=exam_active_reply_kb()
        )
        return

    if not await check_channel_subscription(uid):
        await prompt_subscription(message)
        return

    await state.set_state(AISolveProblem.waiting_problem_photo)
    await message.answer(
        "📸 <b>AI KIMYO MASALA YECHISH BO'LIMI</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Tushunmagan kimyo masalangiz yoki savolingiz rasmini yuboring.\n"
        "Sun'iy intellekt uni bosqichma-bosqich yechib beradi 👇",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Bekor qilish")]], resize_keyboard=True)
    )

@dp.message(AISolveProblem.waiting_problem_photo, F.photo)
async def solve_photo(message: types.Message, state: FSMContext):
    uid = message.from_user.id
    if uid in ACTIVE_EXAM_SESSIONS:
        await message.answer("⛔️ Mock test vaqtida AI masala yechish bloklangan!", reply_markup=exam_active_reply_kb())
        return

    wait = await message.answer("🤖 AI masalani tahlil qilib yechmoqda, 10–15 soniya kuting...")
    try:
        file_id = message.photo[-1].file_id
        tg_file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=buf)
        sol = await ai_solve_photo_problem(buf.getvalue(), "image/jpeg")
        await state.clear()
        await wait.delete()
        await message.answer(f"🧪 <b>AI Masala Yechimi:</b>\n\n{sol}", parse_mode="HTML", reply_markup=main_menu(uid))
    except Exception as e:
        await state.clear()
        await wait.edit_text(f"❌ Xato: {e}")

@dp.message(F.text == "👨‍🏫 Ustoz & Bog'lanish")
async def contact_info(message: types.Message):
    await message.answer(
        f"👨‍🏫 <b>Ustoz:</b> Azizbek Ibrohimov\n"
        f"📢 <b>Rasmiy kanal:</b> {DEFAULT_CHANNEL_URL}\n"
        f"📞 <b>Murojaat uchun:</b> {ADMIN_USERNAME}",
        parse_mode="HTML"
    )

# -------------------------------------------------------------
# ADMIN PANEL
# -------------------------------------------------------------
@dp.message(Command("admin"))
@dp.message(F.text == "👑 Admin Boshqaruv Paneli")
async def admin_panel(message: types.Message, state: FSMContext = None):
    if message.from_user.id != ADMIN_ID:
        return
    if state:
        await state.clear()
    cur_key = get_gemini_api_key()
    masked = f"{cur_key[:8]}..." if cur_key else "Kiritilmagan"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Gemini AI API Kalitni yangilash", callback_data="adm_set_gemini")],
        [InlineKeyboardButton(text="📊 Bot Statistikasi", callback_data="adm_stats")],
        [InlineKeyboardButton(text="🗑 Testni bazadan o'chirish", callback_data="adm_del")]
    ])
    await message.answer(
        f"👑 <b>ADMIN BOSHQARUV PANELI</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔑 Joriy AI kalit: <code>{masked}</code>\n"
        f"📝 Faol imtihon topshirayotganlar: <b>{len(ACTIVE_EXAM_SESSIONS)} kishi</b>",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(F.data == "adm_set_gemini")
async def adm_set_gemini_cb(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminPanel.waiting_gemini_key)
    await callback.message.answer("🔑 Yangi <b>Gemini AI API kalitingizni</b> yuboring:", parse_mode="HTML")
    await callback.answer()

@dp.message(AdminPanel.waiting_gemini_key)
async def save_gemini_key(message: types.Message, state: FSMContext):
    new_key = (message.text or "").strip()
    db_set_setting("gemini_api_key", new_key)
    await state.clear()
    await message.answer("✅ <b>Gemini AI API kaliti saqlandi!</b>", parse_mode="HTML", reply_markup=main_menu(ADMIN_ID))

@dp.callback_query(F.data == "adm_stats")
async def adm_stats(callback: types.CallbackQuery):
    s = db_get_stats()
    await callback.message.answer(
        f"📊 <b>BOT STATISTIKASI:</b>\n"
        f"👥 Foydalanuvchilar: <b>{s['users']} ta</b>\n"
        f"🧪 Yaratilgan testlar: <b>{s['tests']} ta</b>\n"
        f"📝 Topshirilgan natijalar: <b>{s['results']} ta</b>",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "adm_del")
async def adm_del(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminPanel.waiting_delete_code)
    await callback.message.answer("🗑 O'chirmoqchi bo'lgan test kodini yuboring:")
    await callback.answer()

@dp.message(AdminPanel.waiting_delete_code)
async def do_del(message: types.Message, state: FSMContext):
    code = (message.text or "").strip().upper()
    ok = db_delete_test(code)
    await state.clear()
    await message.answer(f"{'✅ Test o\'chirildi!' if ok else '❌ Bunday kodli test topilmadi.'}", reply_markup=main_menu(ADMIN_ID))

# -------------------------------------------------------------
# 24/7 WEB SERVER
# -------------------------------------------------------------
async def handle_ping(request):
    return web.Response(text="A+ Kimyo AI Electronic Mock Bot active 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    init_db()
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
