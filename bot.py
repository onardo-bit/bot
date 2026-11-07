# ============================================
# ИГРОВОЙ БОТ ДЛЯ TELEGRAM
# pip install aiogram  |  python bot.py
# ============================================

import os
import asyncio
import sqlite3
import random
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, PollAnswer,
    InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
)
from aiogram.enums import PollType

# ============================================
# НАСТРОЙКИ
# ============================================
TOKEN = os.environ.get("BOT_TOKEN") or "9098594468:AAHYZT21NS_IYsc3B1N6w8bmP8y0F4ZvWeo"
ADMIN_IDS = [7004839619]
ADMIN_USERNAME = "onardo-bit"
GROUP_ID = -5370978242

DB_NAME = os.environ.get("DB_PATH", "game_bot.db")
EXACT_777_VALUE = 64  # Ровно 7️⃣7️⃣7️⃣ в Telegram API

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
active_games = {}

# ============================================
# БАЗА ДАННЫХ
# ============================================
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, wins INTEGER DEFAULT 0)""")
    c.execute("""CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT, game TEXT, day TEXT, time TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS prizes (
        game TEXT PRIMARY KEY, prize TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, val TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS deliveries (
        id INTEGER PRIMARY KEY AUTOINCREMENT, who TEXT, ts TEXT)""")
    conn.commit(); conn.close()

def get_setting(key, default):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT val FROM settings WHERE key = ?", (key,))
    r = c.fetchone(); conn.close()
    return r["val"] if r else default

def set_setting(key, val):
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, val) VALUES (?, ?)", (key, str(val)))
    conn.commit(); conn.close()

def get_join_seconds():
    return int(get_setting("join_seconds", "900"))

def get_timezone():
    return int(get_setting("tz", "3"))

def register_user(uid, name):
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (uid, name))
    c.execute("UPDATE users SET username = ? WHERE user_id = ?", (name, uid))
    conn.commit(); conn.close()

def is_registered(uid):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT 1 FROM users WHERE user_id = ?", (uid,))
    r = c.fetchone(); conn.close()
    return r is not None

def add_win(uid, name):
    register_user(uid, name)
    conn = get_db(); c = conn.cursor()
    c.execute("UPDATE users SET wins = wins + 1 WHERE user_id = ?", (uid,))
    conn.commit(); conn.close()

def get_user_stats(uid):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
    r = c.fetchone(); conn.close()
    return dict(r) if r else None

def get_prize(game):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT prize FROM prizes WHERE game = ?", (game,))
    r = c.fetchone(); conn.close()
    return r["prize"] if r else "Не назначен"

def set_prize(game, prize):
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO prizes (game, prize) VALUES (?, ?)", (game, prize))
    conn.commit(); conn.close()

def get_schedule():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM schedule")
    rows = c.fetchall(); conn.close()
    return [dict(r) for r in rows]

def add_schedule(game, day, time):
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO schedule (game, day, time) VALUES (?, ?, ?)", (game, day, time))
    conn.commit(); conn.close()

def remove_schedule(game):
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM schedule WHERE game = ?", (game,))
    conn.commit(); conn.close()

def clear_schedule():
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM schedule")
    conn.commit(); conn.close()

def mark_delivered(who):
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO deliveries (who, ts) VALUES (?, ?)",
              (who, datetime.now().isoformat()))
    conn.commit(); conn.close()

# ============================================
# ВОПРОСЫ ДЛЯ ВИКТОРИНЫ
# ============================================
QUESTIONS = [
    {"q": "Сколько будет 7 × 8?", "o": ["54", "56", "58", "64"], "c": 1},
    {"q": "Столица Франции?", "o": ["Лондон", "Берлин", "Париж", "Мадрид"], "c": 2},
    {"q": "Сколько континентов на Земле?", "o": ["5", "6", "7", "8"], "c": 2},
    {"q": "Кто написал «Войну и мир»?", "o": ["Достоевский", "Толстой", "Чехов", "Пушкин"], "c": 1},
    {"q": "Формула воды?", "o": ["CO2", "H2O", "NaCl", "O2"], "c": 1},
    {"q": "Сколько дней в високосном году?", "o": ["364", "365", "366", "367"], "c": 2},
    {"q": "Самая длинная река в мире?", "o": ["Амазонка", "Нил", "Миссисипи", "Янцзы"], "c": 1},
    {"q": "Какой газ мы вдыхаем?", "o": ["CO2", "N2", "O2", "H2"], "c": 2},
    {"q": "Сколько планет в Солнечной системе?", "o": ["7", "8", "9", "10"], "c": 1},
    {"q": "В каком году человек впервые полетел в космос?", "o": ["1957", "1961", "1965", "1969"], "c": 1},
    {"q": "Столица Японии?", "o": ["Пекин", "Сеул", "Токио", "Бангкок"], "c": 2},
    {"q": "Сколько будет 144 ÷ 12?", "o": ["10", "11", "12", "14"], "c": 2},
    {"q": "Какой океан самый большой?", "o": ["Атлантический", "Индийский", "Тихий", "Северный Ледовитый"], "c": 2},
    {"q": "Сколько букв в русском алфавите?", "o": ["30", "32", "33", "34"], "c": 2},
    {"q": "Какая планета ближе всего к Солнцу?", "o": ["Венера", "Марс", "Меркурий", "Земля"], "c": 2},
    {"q": "Сколько будет 15²?", "o": ["200", "215", "225", "250"], "c": 2},
    {"q": "Какой материк самый холодный?", "o": ["Гренландия", "Антарктида", "Арктика", "Сибирь"], "c": 1},
    {"q": "Сколько цветов в радуге?", "o": ["5", "6", "7", "8"], "c": 2},
    {"q": "Кто написал «Евгения Онегина»?", "o": ["Лермонтов", "Гоголь", "Пушкин", "Тургенев"], "c": 2},
    {"q": "Столица России?", "o": ["Москва", "Петербург", "Казань", "Новгород"], "c": 0},
]

# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================
def is_admin(uid):
    return uid in ADMIN_IDS

def make_player(user):
    uname = user.username
    return {
        "id": user.id,
        "name": uname or user.first_name or str(user.id),
        "tag": f"@{uname}" if uname else (user.first_name or str(user.id))
    }

def get_tag(game, uid):
    for p in game["players"]:
        if p["id"] == uid:
            return p["tag"]
    return str(uid)

_admin_mention_cache = None

async def admin_mention():
    global _admin_mention_cache
    if _admin_mention_cache:
        return _admin_mention_cache
    names = []
    for uid in ADMIN_IDS:
        try:
            chat = await bot.get_chat(uid)
            if chat.username:
                names.append("@" + chat.username)
                continue
        except Exception:
            pass
        names.append("@" + ADMIN_USERNAME if ADMIN_USERNAME else f"админ {uid}")
    _admin_mention_cache = ", ".join(names) or "@admin"
    return _admin_mention_cache

async def announce_winner(chat_id, player, game_name):
    add_win(player["id"], player["name"])
    who = await admin_mention()
    await bot.send_message(
        chat_id,
        f"🏆 ПОБЕДИТЕЛЬ: {player['tag']}!\n"
        f"🎮 Игра: {game_name}\n"
        f"🎁 Приз: {get_prize(game_name)}\n\n"
        f"{who}, вручите приз победителю!"
    )

async def hide_admin_cmd(msg: Message):
    """Удаляет сообщение админа из группы, чтобы участники не видели настройки"""
    if msg.chat.type in ("group", "supergroup"):
        try:
            await msg.delete()
        except Exception:
            pass

# ============================================
# ИГРА 1: ЛУДКА ДО 777 (ИГРОКИ САМИ КИДАЮТ 🎰 В ЧАТ)
# ============================================
async def run_777(chat_id):
    game = active_games.get("777")
    if not game or not game["players"]:
        await bot.send_message(chat_id, "😔 Никто не участвует. Игра отменена.")
        active_games.pop("777", None)
        return

    game["phase"] = "playing"

    await bot.send_message(
        chat_id,
        "🎰 ПОГНАЛИ!\n\n"
        "Отправляйте эмодзи 🎰 со своей клавиатуры прямо в чат!\n"
        "Кто первым выбьет ровно 7️⃣7️⃣7️⃣ — забирает победу!"
    )

@dp.message(F.dice & (F.dice.emoji == "🎰"))
async def on_user_slot_dice(msg: Message):
    game = active_games.get("777")
    if not game or game["phase"] != "playing":
        return

    uid = msg.from_user.id
    player_ids = [p["id"] for p in game["players"]]
    if uid not in player_ids:
        p = make_player(msg.from_user)
        game["players"].append(p)
    else:
        p = [x for x in game["players"] if x["id"] == uid][0]

    val = msg.dice.value

    if val == EXACT_777_VALUE:
        game["phase"] = "ended"
        await msg.reply(f"🎉 {p['tag']} ВЫБИЛ 7️⃣7️⃣7️⃣!")
        await announce_winner(msg.chat.id, p, "777")
        active_games.pop("777", None)

# ============================================
# ИГРА 2: ВИКТОРИНА
# ============================================
async def run_quiz(chat_id):
    game = active_games.get("quiz")
    if not game or not game["players"]:
        await bot.send_message(chat_id, "😔 Никто не участвует. Игра отменена.")
        active_games.pop("quiz", None)
        return

    game["phase"] = "playing"
    scores = {p["id"]: {"score": 0, "last_ts": 9999999999.0} for p in game["players"]}
    await bot.send_message(chat_id, "📚 Набор закрыт! 5 вопросов, 30 сек на каждый.")
    await asyncio.sleep(1)

    for i, q in enumerate(random.sample(QUESTIONS, 5), 1):
        await bot.send_message(chat_id, f"❓ Вопрос {i}/5: {q['q']}")
        poll = await bot.send_poll(
            chat_id=chat_id, question=q["q"], options=q["o"],
            type=PollType.QUIZ, correct_option_id=q["c"],
            is_anonymous=False, open_period=30
        )
        game["current_poll"] = poll.poll.id
        game["correct"] = q["c"]
        game["answered"] = {}
        await asyncio.sleep(31)

        for uid, d in game["answered"].items():
            if d["correct"]:
                scores[uid]["score"] += 1 + (1 if d["first"] else 0)
                scores[uid]["last_ts"] = d["ts"]

        top = sorted(scores.items(), key=lambda x: -x[1]["score"])[:3]
        lb = "\n".join(f"  {j+1}. {get_tag(game, uid)} — {data['score']} б." for j, (uid, data) in enumerate(top))
        await bot.send_message(chat_id, f"📊 Результаты после {i} вопроса:\n{lb}")
        await asyncio.sleep(1)

    ranked = sorted(scores.items(), key=lambda x: (-x[1]["score"], x[1]["last_ts"]))
    winner_uid = ranked[0][0]

    winner_player = [p for p in game["players"] if p["id"] == winner_uid][0]
    await announce_winner(chat_id, winner_player, "quiz")
    active_games.pop("quiz", None)

@dp.poll_answer()
async def on_poll_answer(pa: PollAnswer):
    game = active_games.get("quiz")
    if not game or game["phase"] != "playing":
        return
    if pa.poll_id != game.get("current_poll"):
        return
    uid = pa.user.id
    if uid not in [p["id"] for p in game["players"]]:
        return

    chosen = pa.option_ids[0] if pa.option_ids else -1
    correct = chosen == game["correct"]
    first = correct and not any(d["correct"] for d in game["answered"].values())
    game["answered"][uid] = {
        "correct": correct,
        "first": first,
        "ts": datetime.now().timestamp()
    }

# ============================================
# ИГРА 3: 21 (БЕЗ ЛАГОВ)
# ============================================
async def run_21(chat_id):
    game = active_games.get("21")
    if not game or not game["players"]:
        await bot.send_message(chat_id, "😔 Никто не участвует. Игра отменена.")
        active_games.pop("21", None)
        return

    game["phase"] = "playing"
    roster = list(game["players"])
    random.shuffle(roster)
    q_text = "\n".join(f"  {i+1}. {p['tag']}" for i, p in enumerate(roster))
    await bot.send_message(chat_id, f"📋 Очередь:\n{q_text}\n🎲 Начинаем!")
    await asyncio.sleep(2)

    round_no = 1
    queue = list(roster)
    sums = {p["id"]: 0 for p in roster}
    attempts = {p["id"]: 0 for p in roster}

    while True:
        if not queue:
            await bot.send_message(chat_id, "😔 Все выбыли! Начинаем раунд заново с теми же игроками.")
            await asyncio.sleep(3)
            queue = list(roster)
            sums = {p["id"]: 0 for p in roster}
            attempts = {p["id"]: 0 for p in roster}
            round_no = 1
            continue

        await bot.send_message(chat_id, f"--- Круг {round_no} ---")
        await asyncio.sleep(1.5)
        next_queue = []

        for p in queue:
            pid = p["id"]

            msg = await bot.send_dice(chat_id, emoji="🎲")
            val = msg.dice.value
            sums[pid] += val
            s = sums[pid]

            await asyncio.sleep(1.5)

            if s == 21:
                await bot.send_message(
                    chat_id, f"{p['tag']}: 🎲 Выпало {val} | Сумма: 21 — 🏆 ПОБЕДА!")
                await announce_winner(chat_id, p, "21")
                active_games.pop("21", None)
                return

            if s > 21:
                if attempts[pid] >= 1:
                    await bot.send_message(
                        chat_id, f"{p['tag']}: 🎲 Выпало {val} | Сумма: {s} — 💀 Выбыл окончательно!")
                else:
                    attempts[pid] += 1
                    sums[pid] = 0
                    await bot.send_message(
                        chat_id,
                        f"{p['tag']}: 🎲 Выпало {val} | Сумма: {s} — 💀 Перебор!\n"
                        f"Вторая попытка в конце очереди.")
                    next_queue.append(p)
            else:
                await bot.send_message(
                    chat_id, f"{p['tag']}: 🎲 Выпало {val} | Сумма: {s}")
                next_queue.append(p)

            await asyncio.sleep(2)

        queue = next_queue
        round_no += 1

# ============================================
# ЕДИНЫЙ ЗАПУСК ИГР
# ============================================
GAME_META = {
    "777":  ("🎰 ЛУДКА ДО 777!", "Кидайте эмодзи 🎰 в чат со своей клавиатуры. Кто первый выбьет 7️⃣7️⃣7️⃣ — победил!", False, run_777),
    "quiz": ("📚 ВИКТОРИНА!", "5 школьных вопросов, 30 сек на каждый.", True, run_quiz),
    "21":   ("🎲 ИГРА 21!", "Один бросок по кругу. 21 — победа. Перебор — вторая попытка.", True, run_21),
}

async def launch_game(game, chat_id, scheduled=False):
    if game in active_games:
        await bot.send_message(chat_id, f"⚠️ Игра {game} уже идёт.")
        return
    title, desc, need_reg, runner = GAME_META[game]
    sec = get_join_seconds()
    active_games[game] = {"players": [], "phase": "join"}

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Участвовать", callback_data=f"join_{game}")]
    ])
    tail = " (по расписанию)" if scheduled else ""
    reg = "Нужна регистрация (кнопка ниже)." if need_reg else "Регистрация не нужна."
    await bot.send_message(
        chat_id,
        f"{title}{tail}\n"
        f"🎁 Приз: {get_prize(game)}\n"
        f"{desc}\n{reg}\n"
        f"⏱ Набор: {sec // 60} мин. ({sec} сек.)",
        reply_markup=kb
    )
    await asyncio.sleep(sec)
    await bot.send_message(chat_id, "Набор закрыт, начинаем!")
    await runner(chat_id)

@dp.callback_query(F.data.startswith("join_"))
async def cb_join(call: CallbackQuery):
    game = call.data.split("_", 1)[1]
    state = active_games.get(game)
    if not state or state["phase"] != "join":
        await call.answer("⏳ Набор закрыт!", show_alert=True)
        return

    uid = call.from_user.id
    if uid in [p["id"] for p in state["players"]]:
        await call.answer("✅ Ты уже в игре!", show_alert=True)
        return

    p = make_player(call.from_user)
    need_reg = GAME_META[game][2]

    if need_reg and not is_registered(uid):
        register_user(uid, p["name"])
        text = f"🆕 {p['tag']} зарегистрирован и в игре!"
    else:
        text = f"✅ {p['tag']} в игре!"

    state["players"].append(p)
    await call.answer("✅ Ты в игре!", show_alert=True)
    await bot.send_message(GROUP_ID, text)

# ============================================
# КОМАНДЫ МОДЕРАЦИИ И УПРАВЛЕНИЯ
# ============================================
@dp.message(Command("mute"))
async def cmd_mute(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await hide_admin_cmd(msg)
    try:
        await bot.set_chat_permissions(
            GROUP_ID,
            ChatPermissions(can_send_messages=False)
        )
        await bot.send_message(GROUP_ID, "🔇 Чат замучен! Участники не могут писать.")
    except Exception as e:
        await bot.send_message(msg.from_user.id, f"❌ Ошибка /mute: {e}")

@dp.message(Command("unmute"))
async def cmd_unmute(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await hide_admin_cmd(msg)
    try:
        await bot.set_chat_permissions(
            GROUP_ID,
            ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        await bot.send_message(GROUP_ID, "🔊 Чат размучен! Все могут писать.")
    except Exception as e:
        await bot.send_message(msg.from_user.id, f"❌ Ошибка /unmute: {e}")

@dp.message(Command("start"))
async def cmd_start(msg: Message):
    if msg.chat.type in ("group", "supergroup"):
        await msg.answer("👋 Я игровой бот! Пишите мне в ЛС для настройки.")
    else:
        await msg.answer(
            "⚙️ ПАНЕЛЬ УПРАВЛЕНИЯ БОТОМ\n\n"
            "🎮 Запуск игр в группу:\n"
            "/start777  ·  /startquiz  ·  /start21\n\n"
            "🔇 Модерация:\n"
            "/mute — замутить группу\n"
            "/unmute — размутить группу\n\n"
            "⚙️ Настройки:\n"
            "/jointime 900 — время набора\n"
            "/schedule — расписание\n"
            "/set /remove /clear_schedule /timezone\n"
            "/prize /prizes /delivered"
        )

@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await hide_admin_cmd(msg)
    target = msg.from_user.id if msg.chat.type in ("group", "supergroup") else msg.chat.id
    await bot.send_message(
        target,
        "🎮 ИГРЫ: /start777 /startquiz /start21\n"
        "🔇 МОДЕРАЦИЯ: /mute /unmute\n"
        f"⏱ /jointime 900 — время набора (сейчас {get_join_seconds()} сек)\n"
        "📋 /schedule /set /remove /clear_schedule /timezone\n"
        "🎁 /prize /prizes /delivered"
    )

@dp.message(Command("myprofile"))
async def cmd_profile(msg: Message):
    s = get_user_stats(msg.from_user.id)
    if not s:
        await msg.answer("❌ Ещё не зарегистрирован. Нажми «Участвовать» в викторине или 21.")
        return
    await msg.answer(f"👤 {s['username']}\n📝 Регистрация: ✅\n🏆 Побед: {s['wins']}")

@dp.message(Command("start777"))
async def cmd_777(msg: Message):
    if is_admin(msg.from_user.id):
        await hide_admin_cmd(msg)
        asyncio.create_task(launch_game("777", GROUP_ID))

@dp.message(Command("startquiz"))
async def cmd_quiz(msg: Message):
    if is_admin(msg.from_user.id):
        await hide_admin_cmd(msg)
        asyncio.create_task(launch_game("quiz", GROUP_ID))

@dp.message(Command("start21"))
async def cmd_21(msg: Message):
    if is_admin(msg.from_user.id):
        await hide_admin_cmd(msg)
        asyncio.create_task(launch_game("21", GROUP_ID))

@dp.message(Command("jointime"))
async def cmd_jointime(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await hide_admin_cmd(msg)
    args = msg.text.split()
    sec = get_join_seconds()
    if len(args) < 2:
        await bot.send_message(
            msg.from_user.id,
            f"⏱ Сейчас набор: {sec} сек. ({sec // 60} мин.)\n"
            "Изменить: /jointime 900  (от 10 до 1800 сек)"
        )
        return
    try:
        val = int(args[1])
        if 10 <= val <= 1800:
            set_setting("join_seconds", val)
            await bot.send_message(msg.from_user.id, f"✅ Время набора: {val} сек. ({val // 60} мин.).")
        else:
            await bot.send_message(msg.from_user.id, "От 10 до 1800 секунд.")
    except ValueError:
        await bot.send_message(msg.from_user.id, "Напиши число секунд, например: /jointime 900")

@dp.message(Command("schedule"))
async def cmd_schedule(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await hide_admin_cmd(msg)
    rows = get_schedule()
    if not rows:
        await bot.send_message(msg.from_user.id, f"📋 Расписание пусто. Набор: {get_join_seconds()} сек, UTC+{get_timezone()}.")
        return
    t = "📋 Расписание:\n" + "\n".join(f"  {r['game']} — {r['day']} {r['time']}" for r in rows)
    await bot.send_message(msg.from_user.id, t + f"\n⏱ Набор: {get_join_seconds()} сек | UTC+{get_timezone()}")

DAYS_RU = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]

@dp.message(Command("set"))
async def cmd_set(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await hide_admin_cmd(msg)
    a = msg.text.split()
    if len(a) < 4 or a[1] not in GAME_META or a[2].upper() not in DAYS_RU:
        await bot.send_message(msg.from_user.id, "Формат: /set 777 ПН 18:00")
        return
    add_schedule(a[1], a[2].upper(), a[3])
    await bot.send_message(msg.from_user.id, f"✅ {a[1]} — {a[2].upper()} {a[3]}")

@dp.message(Command("remove"))
async def cmd_remove(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await hide_admin_cmd(msg)
    a = msg.text.split()
    if len(a) > 1:
        remove_schedule(a[1])
        await bot.send_message(msg.from_user.id, f"✅ {a[1]} убрана из расписания")

@dp.message(Command("clear_schedule"))
async def cmd_clear(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await hide_admin_cmd(msg)
    clear_schedule()
    await bot.send_message(msg.from_user.id, "✅ Расписание очищено")

@dp.message(Command("timezone"))
async def cmd_tz(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await hide_admin_cmd(msg)
    a = msg.text.split()
    if len(a) < 2:
        await bot.send_message(msg.from_user.id, f"UTC+{get_timezone()}. Изменить: /timezone 3")
        return
    try:
        set_setting("tz", int(a[1]))
        await bot.send_message(msg.from_user.id, f"✅ Часовой пояс: UTC+{get_timezone()}")
    except ValueError:
        await bot.send_message(msg.from_user.id, "Напиши число: /timezone 3")

@dp.message(Command("prize"))
async def cmd_prize(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await hide_admin_cmd(msg)
    a = msg.text.split(maxsplit=2)
    if len(a) < 3 or a[1] not in GAME_META:
        await bot.send_message(msg.from_user.id, "Формат: /prize 777 Звёздный подарок")
        return
    set_prize(a[1], a[2])
    await bot.send_message(msg.from_user.id, f"✅ Приз для {a[1]}: {a[2]}")

@dp.message(Command("prizes"))
async def cmd_prizes(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await hide_admin_cmd(msg)
    await bot.send_message(msg.from_user.id, "🎁 Призы:\n" + "\n".join(
        f"  {g}: {get_prize(g)}" for g in GAME_META))

@dp.message(Command("delivered"))
async def cmd_delivered(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await hide_admin_cmd(msg)
    a = msg.text.split()
    who = a[1] if len(a) > 1 else "?"
    mark_delivered(who)
    await bot.send_message(msg.from_user.id, f"✅ Вручение {who} отмечено!")

# ============================================
# РАСПИСАНИЕ 24/7
# ============================================
async def scheduler():
    fired = set()
    while True:
        now = datetime.now(timezone(timedelta(hours=get_timezone())))
        today = now.date().isoformat()
        cur_day = DAYS_RU[now.weekday()]
        cur_time = now.strftime("%H:%M")
        warn_time = (now + timedelta(minutes=5)).strftime("%H:%M")

        for r in get_schedule():
            g = r["game"]
            if r["day"] != cur_day or g not in GAME_META:
                continue

            if r["time"] == warn_time and (today, "warn", g) not in fired:
                fired.add((today, "warn", g))
                await bot.send_message(GROUP_ID, f"⏰ Через 5 минут — {GAME_META[g][0]}! Готовьтесь.")

            if r["time"] == cur_time and (today, "go", g) not in fired:
                fired.add((today, "go", g))
                if g not in active_games:
                    asyncio.create_task(launch_game(g, GROUP_ID, scheduled=True))

        await asyncio.sleep(20)

# ============================================
# ЗАПУСК
# ============================================
async def main():
    if not TOKEN or TOKEN.startswith("ВСТАВЬ"):
        raise SystemExit("❌ Вставь токен!")
    init_db()
    logging.info("✅ Бот запущен, набор %s сек, UTC+%s", get_join_seconds(), get_timezone())
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
