import os
import asyncio
import random
import sqlite3
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, PollAnswer, ChatPermissions
from aiogram.exceptions import TelegramMigrateToChat

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")

ADMIN_IDS = [7004839619]
ADMIN_USERNAME = "onardo-bit"
GROUP_ID = -1004382624629 
EXACT_777_VALUE = 64 

if not TOKEN:
    print("⚠️ ОШИБКА: Переменная BOT_TOKEN не установлена в Railway!")

bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
db = sqlite3.connect("bot_data.db", check_same_thread=False)
cur = db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, name TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS prizes (game TEXT PRIMARY KEY, text TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, wins_777 INTEGER DEFAULT 0, wins_21 INTEGER DEFAULT 0, wins_quiz INTEGER DEFAULT 0, wins_roulette INTEGER DEFAULT 0)")

# Авто-добавление колонки wins_roulette, если БД создана ранее
try:
    cur.execute("ALTER TABLE stats ADD COLUMN wins_roulette INTEGER DEFAULT 0")
except:
    pass
db.commit()

def get_config(key, default):
    cur.execute("SELECT value FROM config WHERE key=?", (key,))
    res = cur.fetchone()
    return res[0] if res else default

def set_config(key, value):
    cur.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, str(value)))
    db.commit()

def add_win(uid: int, game_type: str):
    cur.execute("INSERT OR IGNORE INTO stats (id) VALUES (?)", (uid,))
    if game_type == "777":
        cur.execute("UPDATE stats SET wins_777 = wins_777 + 1 WHERE id=?", (uid,))
    elif game_type == "21":
        cur.execute("UPDATE stats SET wins_21 = wins_21 + 1 WHERE id=?", (uid,))
    elif game_type == "quiz":
        cur.execute("UPDATE stats SET wins_quiz = wins_quiz + 1 WHERE id=?", (uid,))
    elif game_type == "roulette":
        cur.execute("UPDATE stats SET wins_roulette = wins_roulette + 1 WHERE id=?", (uid,))
    db.commit()

# --- БАЗА ВОПРОСОВ ДЛЯ ВИКТОРИНЫ ---
QUIZ_QUESTION_POOL = [
    ("Сколько планет в Солнечной системе?", ["7", "8", "9", "10"], 1),
    ("Какой химический символ у Золота?", ["Ag", "Fe", "Au", "Pb"], 2),
    ("В каком году человек впервые полетел в космос?", ["1957", "1961", "1965", "1969"], 1),
    ("Столица Франции?", ["Берлин", "Париж", "Рим", "Мадрид"], 1),
    ("Корень из 144?", ["10", "11", "12", "14"], 2),
    ("Какая самая длинная река в мире?", ["Амазонка", "Нил", "Миссисипи", "Янцзы"], 0),
    ("Сколько хромосом у здорового человека?", ["42", "44", "46", "48"], 2),
    ("Кто написал роман 'Война и мир'?", ["Достоевский", "Толстой", "Пушкин", "Тургенев"], 1),
    ("Какая планета самая большая в Солнечной системе?", ["Марс", "Сатурн", "Юпитер", "Нептун"], 2),
    ("Какое вещество самое твёрдое на Земле?", ["Графен", "Алмаз", "Титан", "Кварц"], 1),
    ("Сколько материков на Земле?", ["5", "6", "7", "8"], 1),
    ("В каком году началась Вторая мировая война?", ["1914", "1939", "1941", "1945"], 1),
    ("Какая птица не умеет летать, но отлично плавает?", ["Орёл", "Пингвин", "Страус", "Пеликан"], 1),
    ("Какое число обозначается римской цифрой 'X'?", ["5", "10", "50", "100"], 1),
    ("Какой газ преобладает в атмосфере Земли?", ["Кислород", "Азот", "Углекислый газ", "Водород"], 1),
    ("Сколько граней у классического куба?", ["4", "6", "8", "12"], 1),
    ("Кто открыл закон всемирного тяготения?", ["Эйнштейн", "Ньютон", "Галилей", "Тесла"], 1),
    ("Какая страна самая большая по площади?", ["Канада", "Китай", "США", "Россия"], 3),
    ("Как называется ближайшая к Земле звезда?", ["Сириус", "Солнце", "Проксима Центавра", "Полярная"], 1),
    ("Какое животное является самым быстрым на суше?", ["Лев", "Гепард", "Антилопа", "Сокол"], 1),
    ("Сколько градусов составляет сумма углов треугольника?", ["90°", "180°", "270°", "360°"], 1),
    ("Какая океанская впадина является самой глубокой?", ["Марианская", "Бермудская", "Зондская", "Пуэрто-Рико"], 0),
    ("Кто написал поэму 'Евгений Онегин'?", ["Пушкин", "Лермонтов", "Гоголь", "Чехов"], 0),
    ("Какое озеро является самым глубоким в мире?", ["Виктория", "Мичиган", "Байкал", "Каспийское"], 2),
    ("Какой элемент обозначается буквой 'O' в таблице Менделеева?", ["Олово", "Кислород", "Осмий", "Озон"], 1)
]

# --- СОСТОЯНИЯ ИГР ---
game_777_active = False
game_quiz_active = False
game_21_active = False
game_roulette_active = False

reg_users = []  
quiz_scores = {} 

active_turn_21 = None 
active_turn_rr = None

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def hide_admin_cmd(message: types.Message):
    if message.chat.type != "private":
        try:
            await message.delete()
        except Exception:
            pass

def get_mention(user_id: int, username: str = None) -> str:
    return f"@{username}" if username else f"<a href='tg://user?id={user_id}'>Игрок</a>"

async def safe_send_message(chat_id: int, text: str, **kwargs):
    global GROUP_ID
    try:
        if 'parse_mode' not in kwargs:
            kwargs['parse_mode'] = "HTML"
        return await bot.send_message(chat_id, text, **kwargs)
    except TelegramMigrateToChat as e:
        GROUP_ID = e.migrate_to_chat_id
        return await bot.send_message(GROUP_ID, text, **kwargs)
    except Exception as e:
        print(f"Ошибка отправки сообщения: {e}")

# --- КОМАНДЫ (ДЛЯ ВСЕХ) ---
@dp.message(Command("profile"))
async def show_profile(message: types.Message):
    uid = message.from_user.id
    cur.execute("SELECT wins_777, wins_21, wins_quiz, wins_roulette FROM stats WHERE id=?", (uid,))
    res = cur.fetchone()
    w777, w21, wq, wr = res if res else (0, 0, 0, 0)
    
    text = (
        f"👤 <b>Профиль игрока:</b> {message.from_user.full_name}\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"🎮 Тег: {get_mention(uid, message.from_user.username)}\n\n"
        f"🏆 <b>СТАТИСТИКА ПОБЕД:</b>\n"
        f"🎰 Лудка 777: <b>{w777}</b>\n"
        f"🎲 Игра 21: <b>{w21}</b>\n"
        f"🎓 Викторина: <b>{wq}</b>\n"
        f"🔫 Русская Рулетка: <b>{wr}</b>"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("admin"))
async def show_admin(message: types.Message):
    await message.answer(f"👑 <b>Главный администратор:</b> @{ADMIN_USERNAME}\nПо вопросам призов и предложений пишите ему.", parse_mode="HTML")

# --- АДМИН-УПРАВЛЕНИЕ ---
@dp.message(Command("chat"))
async def chat_control(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Используйте: `/chat -` (закрыть) или `/chat +` (открыть)")
        return
        
    try:
        if args[1] == "-":
            await bot.set_chat_permissions(GROUP_ID, ChatPermissions(can_send_messages=False))
            await safe_send_message(GROUP_ID, "🔇 Чат закрыт (режим «Только чтение»).")
        elif args[1] == "+":
            await bot.set_chat_permissions(
                GROUP_ID,
                ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )
            await safe_send_message(GROUP_ID, "🔊 Чат открыт.")
    except Exception as e:
        await message.answer(f"Ошибка при изменении прав чата: {e}")

@dp.message(Command("cancel"))
async def cancel_all_games(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    
    global game_777_active, game_21_active, game_quiz_active, game_roulette_active, active_turn_21, active_turn_rr
    game_777_active = False
    game_21_active = False
    game_quiz_active = False
    game_roulette_active = False
    
    if active_turn_21 and active_turn_21.get('event'): active_turn_21['event'].set()
    if active_turn_rr and active_turn_rr.get('event'): active_turn_rr['event'].set()
        
    await safe_send_message(GROUP_ID, "🛑 <b>ВНИМАНИЕ!</b>\nВсе текущие игры были принудительно отменены администратором!")

@dp.message(Command("jointime"))
async def set_jointime(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    try:
        t = int(message.text.split()[1])
        set_config("jointime", t)
        await message.answer(f"✅ Время регистрации: {t} сек.")
    except:
        await message.answer("Формат: `/jointime 300`")

@dp.message(Command("prize"))
async def set_prize(message: types.Message):
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    args = message.text.split(maxsplit=2)
    if len(args) < 3: return
    cur.execute("INSERT OR REPLACE INTO prizes (game, text) VALUES (?, ?)", (args[1].lower(), args[2]))
    db.commit()
    await message.answer(f"✅ Приз для {args[1]} сохранён.")

# --- ИГРА 1: 777 ---
@dp.message(Command("start777"))
async def start_777(message: types.Message):
    global game_777_active
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)
    game_777_active = True
    await safe_send_message(
        GROUP_ID,
        "🎰 <b>ИГРА «ЛУДКА 777» НАЧАЛАСЬ!</b>\n\nОтправляйте эмодзи 🎰 со своей клавиатуры в чат.\nКто первым выбьет 7️⃣7️⃣7️⃣ — тот победил!"
    )

@dp.message(F.dice.emoji == "🎰")
async def check_777_roll(message: types.Message):
    global game_777_active
    if not game_777_active or message.chat.id != GROUP_ID: return

    if message.dice.value == EXACT_777_VALUE:
        game_777_active = False
        add_win(message.from_user.id, "777")
        
        cur.execute("SELECT text FROM prizes WHERE game='777'")
        pz = cur.fetchone()
        
        await message.reply(
            f"🎉 <b>ПОБЕДА! 7️⃣7️⃣7️⃣</b>\n\n"
            f"🏆 Победитель: {get_mention(message.from_user.id, message.from_user.username)}\n"
            f"🎁 Приз: {pz[0] if pz else 'Не указан'}\n\n"
            f"За призом к @{ADMIN_USERNAME}", parse_mode="HTML"
        )

# --- ИГРА 2: ИГРА 21 ---
@dp.message(Command("start21"))
async def start_21(message: types.Message):
    global game_21_active, reg_users
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)

    game_21_active = True
    reg_users = []
    join_time = int(get_config("jointime", 900))

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Участвовать 🎲", callback_data="reg_21")
    ]])

    await safe_send_message(GROUP_ID, f"🎲 <b>РЕГИСТРАЦИЯ НА ИГРУ «21»</b>\n\nЖми кнопку ниже! Время: <b>{join_time} сек.</b>", reply_markup=kb)
    await asyncio.sleep(join_time)
    await process_21_game()

@dp.callback_query(F.data == "reg_21")
async def register_21_user(callback: types.CallbackQuery):
    if callback.from_user.id not in reg_users:
        reg_users.append(callback.from_user.id)
        cur.execute("INSERT OR REPLACE INTO users (id, username, name) VALUES (?, ?, ?)", 
                    (callback.from_user.id, callback.from_user.username, callback.from_user.full_name))
        db.commit()
        await callback.answer("Вы зарегистрированы!")
    else:
        await callback.answer("Вы уже участвуете!")

@dp.callback_query(F.data == "roll_21")
async def process_user_roll(callback: types.CallbackQuery):
    global active_turn_21
    if not game_21_active or not active_turn_21:
        await callback.answer("Сейчас нельзя бросить кубик.", show_alert=True)
        return
    if callback.from_user.id != active_turn_21['player_id']:
        await callback.answer("⏳ Сейчас не ваш ход!", show_alert=True)
        return
        
    active_turn_21['player_id'] = None 
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass

    dice_msg = await bot.send_dice(GROUP_ID, emoji="🎲")
    active_turn_21['dice_value'] = dice_msg.dice.value
    active_turn_21['event'].set()
    await callback.answer("Кубик брошен!")

async def process_21_game():
    global game_21_active, active_turn_21
    if not reg_users:
        await safe_send_message(GROUP_ID, "❌ Никто не зарегистрировался. Игра «21» отменена.")
        game_21_active = False
        return

    players_queue = []
    for uid in reg_users:
        cur.execute("SELECT username FROM users WHERE id=?", (uid,))
        res = cur.fetchone()
        un = res[0] if res else None
        players_queue.append({"id": uid, "un": un, "score": 0})

    mentions = [get_mention(p["id"], p["un"]) for p in players_queue]
    await safe_send_message(
        GROUP_ID, 
        f"🚀 <b>ИГРА «21» НАЧАЛАСЬ!</b>\n\n"
        f"👥 <b>Участники:</b> {', '.join(mentions)}\n\n"
        f"📌 <i>Правила: 60 секунд на ход. Перебор (>21) = ВЫЛЕТ!</i>"
    )

    initial_players = [dict(p) for p in players_queue]
    winner = None

    while game_21_active and not winner:
        if len(players_queue) == 1:
            winner = players_queue[0]
            break

        if not players_queue:
            await safe_send_message(GROUP_ID, "🔄 Все игроки выбыли! Начинаем раунд заново...")
            players_queue = [dict(p) for p in initial_players]
            for p in players_queue: p["score"] = 0
            continue

        player = players_queue.pop(0)
        mention = get_mention(player["id"], player["un"])
        
        turn_event = asyncio.Event()
        active_turn_21 = {
            'player_id': player["id"],
            'event': turn_event,
            'dice_value': 0
        }

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Кинуть 🎲", callback_data="roll_21")
        ]])
        
        turn_msg = await safe_send_message(
            GROUP_ID, 
            f"🎲 Ход игрока {mention} (Сумма: <b>{player['score']}</b>)\n⏳ У вас <b>60 секунд</b>!", 
            reply_markup=kb
        )

        try:
            await asyncio.wait_for(turn_event.wait(), timeout=60.0)
            if not game_21_active: break

            await asyncio.sleep(1.5)
            val = active_turn_21['dice_value']
            player["score"] += val

            await safe_send_message(GROUP_ID, f"{mention}: 🎲 Выпало <b>{val}</b> | Текущая сумма: <b>{player['score']}</b>")

            if player["score"] == 21:
                winner = player
                break
            elif player["score"] > 21:
                await safe_send_message(GROUP_ID, f"💥 {mention} набрал <b>{player['score']}</b> (>21) и <b>ВЫБЫВАЕТ</b> из игры!")
            else:
                players_queue.append(player)

        except asyncio.TimeoutError:
            try: await turn_msg.edit_reply_markup(reply_markup=None)
            except: pass
            await safe_send_message(GROUP_ID, f"⏰ Время вышло! {mention} проигнорировал ход и <b>ВЫБЫВАЕТ</b>!")

        active_turn_21 = None
        await asyncio.sleep(2.0)

    if winner:
        game_21_active = False
        add_win(winner['id'], "21")
        cur.execute("SELECT text FROM prizes WHERE game='21'")
        pz = cur.fetchone()
        await safe_send_message(
            GROUP_ID,
            f"🏆 <b>ЕДИНСТВЕННЫЙ ПОБЕДИТЕЛЬ В 21:</b> {get_mention(winner['id'], winner['un'])}\n"
            f"🎯 Результат: <b>{winner['score']}</b>!\n"
            f"🎁 Приз: {pz[0] if pz else 'Не указан'}\n\nНапишите @{ADMIN_USERNAME}!"
        )

# --- ИГРА 3: ВИКТОРИНА ---
@dp.message(Command("startquiz"))
async def start_quiz(message: types.Message):
    global game_quiz_active, reg_users, quiz_scores
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)

    game_quiz_active = True
    reg_users = []
    quiz_scores = {}
    join_time = int(get_config("jointime", 900))

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Участвовать 🎓", callback_data="reg_quiz")
    ]])

    await safe_send_message(GROUP_ID, f"🎓 <b>ВИКТОРИНА!</b>\n\n5 случайных вопросов. Время на вход: <b>{join_time} сек.</b>", reply_markup=kb)
    await asyncio.sleep(join_time)
    await run_quiz_questions()

@dp.callback_query(F.data == "reg_quiz")
async def register_quiz_user(callback: types.CallbackQuery):
    if callback.from_user.id not in reg_users:
        reg_users.append(callback.from_user.id)
        cur.execute("INSERT OR REPLACE INTO users (id, username, name) VALUES (?, ?, ?)", 
                    (callback.from_user.id, callback.from_user.username, callback.from_user.full_name))
        db.commit()
        quiz_scores[callback.from_user.id] = {"score": 0, "last_ts": 0, "username": callback.from_user.username}
        await callback.answer("Вы в игре!")
    else:
        await callback.answer("Уже зарегистрированы!")

async def run_quiz_questions():
    global game_quiz_active
    if not reg_users:
        await safe_send_message(GROUP_ID, "❌ Нет участников. Викторина отменена.")
        game_quiz_active = False
        return

    mentions = []
    for uid in reg_users:
        cur.execute("SELECT username FROM users WHERE id=?", (uid,))
        res = cur.fetchone()
        un = res[0] if res else None
        mentions.append(get_mention(uid, un))
        
    await safe_send_message(GROUP_ID, f"🧠 <b>ВИКТОРИНА НАЧИНАЕТСЯ!</b>\n\n👥 <b>Участники:</b> {', '.join(mentions)}")

    selected_questions = random.sample(QUIZ_QUESTION_POOL, 5)

    for q_text, opts, correct_idx in selected_questions:
        if not game_quiz_active: break
        await bot.send_poll(
            chat_id=GROUP_ID, question=q_text, options=opts, is_anonymous=False, 
            type="quiz", correct_option_id=correct_idx, open_period=30
        )
        await asyncio.sleep(32)

    if not game_quiz_active: return

    if not quiz_scores:
        await safe_send_message(GROUP_ID, "Викторина завершена. Ответы не получены.")
        game_quiz_active = False
        return

    sorted_players = sorted(quiz_scores.items(), key=lambda x: (-x[1]["score"], x[1]["last_ts"]))
    win_id, win_data = sorted_players[0]
    add_win(win_id, "quiz")

    cur.execute("SELECT text FROM prizes WHERE game='quiz'")
    pz = cur.fetchone()

    await safe_send_message(
        GROUP_ID,
        f"🏆 <b>ПОБЕДИТЕЛЬ ВИКТОРИНЫ:</b> {get_mention(win_id, win_data['username'])}\n"
        f"📊 Очки: <b>{win_data['score']}</b>\n🎁 Приз: {pz[0] if pz else 'Не указан'}\n\nПиши @{ADMIN_USERNAME}!"
    )
    game_quiz_active = False

@dp.poll_answer()
async def process_poll_answer(poll_answer: PollAnswer):
    if not game_quiz_active: return
    if poll_answer.user_id in quiz_scores:
        quiz_scores[poll_answer.user_id]["score"] += 1
        quiz_scores[poll_answer.user_id]["last_ts"] = time.time()

# --- ИГРА 4: РУССКАЯ РУЛЕТКА ---
@dp.message(Command("startroulette"))
async def start_roulette(message: types.Message):
    global game_roulette_active, reg_users
    if not await is_admin(message.from_user.id): return
    await hide_admin_cmd(message)

    game_roulette_active = True
    reg_users = []
    join_time = int(get_config("jointime", 900))

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Участвовать 🔫", callback_data="reg_rr")
    ]])

    await safe_send_message(
        GROUP_ID, 
        f"🔫 <b>РЕГИСТРАЦИЯ НА «РУССКУЮ РУЛЕТКУ»</b>\n\n"
        f"Испытай удачу! Регистрация длится <b>{join_time} сек.</b>", 
        reply_markup=kb
    )
    await asyncio.sleep(join_time)
    await process_roulette_game()

@dp.callback_query(F.data == "reg_rr")
async def register_rr_user(callback: types.CallbackQuery):
    if callback.from_user.id not in reg_users:
        reg_users.append(callback.from_user.id)
        cur.execute("INSERT OR REPLACE INTO users (id, username, name) VALUES (?, ?, ?)", 
                    (callback.from_user.id, callback.from_user.username, callback.from_user.full_name))
        db.commit()
        await callback.answer("Вы зарегистрированы на Рулетку!")
    else:
        await callback.answer("Вы уже участвуете!")

@dp.callback_query(F.data == "shot_rr")
async def process_rr_shot(callback: types.CallbackQuery):
    global active_turn_rr
    if not game_roulette_active or not active_turn_rr:
        await callback.answer("Сейчас нельзя спустить курок.", show_alert=True)
        return
    if callback.from_user.id != active_turn_rr['player_id']:
        await callback.answer("⏳ Сейчас не ваш ход!", show_alert=True)
        return

    active_turn_rr['player_id'] = None
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass

    active_turn_rr['event'].set()
    await callback.answer("Вы спустили курок...")

async def process_roulette_game():
    global game_roulette_active, active_turn_rr
    if not reg_users:
        await safe_send_message(GROUP_ID, "❌ Никто не зарегистрировался. Русская Рулетка отменена.")
        game_roulette_active = False
        return

    players_queue = []
    for uid in reg_users:
        cur.execute("SELECT username FROM users WHERE id=?", (uid,))
        res = cur.fetchone()
        un = res[0] if res else None
        players_queue.append({"id": uid, "un": un})

    mentions = [get_mention(p["id"], p["un"]) for p in players_queue]
    await safe_send_message(
        GROUP_ID, 
        f"🔫 <b>РУССКАЯ РУЛЕТКА НАЧИНАЕТСЯ!</b>\n\n"
        f"👥 <b>Участники:</b> {', '.join(mentions)}\n\n"
        f"⚙️ <i>Барабан заряжен (1 патрон из 6). У вас 60 секунд на ход!</i>"
    )

    initial_players = [dict(p) for p in players_queue]
    winner = None

    # Создаём барабан из 6 камор (1 патрон)
    cylinder = [True] + [False] * 5
    random.shuffle(cylinder)

    while game_roulette_active and not winner:
        # Остался 1 выживший — он победитель!
        if len(players_queue) == 1:
            winner = players_queue[0]
            break

        # Если выбыли все — перезапуск раунда
        if not players_queue:
            await safe_send_message(GROUP_ID, "🔄 Все игроки погибли! Перезапуск револьвера...")
            players_queue = [dict(p) for p in initial_players]
            cylinder = [True] + [False] * 5
            random.shuffle(cylinder)
            continue

        player = players_queue.pop(0)
        mention = get_mention(player["id"], player["un"])

        turn_event = asyncio.Event()
        active_turn_rr = {
            'player_id': player["id"],
            'event': turn_event
        }

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Спустить курок 💥", callback_data="shot_rr")
        ]])

        turn_msg = await safe_send_message(
            GROUP_ID, 
            f"🎯 Ход игрока {mention}\n⏳ У вас <b>60 секунд</b>, чтобы спустить курок!", 
            reply_markup=kb
        )

        try:
            await asyncio.wait_for(turn_event.wait(), timeout=60.0)
            if not game_roulette_active: break

            await asyncio.sleep(1.0)

            # Проверяем выстрел
            is_bullet = cylinder.pop(0)

            if is_bullet:
                await safe_send_message(GROUP_ID, f"💥 <b>БАНГ!</b> Выстрел прогремел! {mention} <b>ВЫБЫВАЕТ</b> из игры!")
                # Перезаряжаем и прокручиваем барабан заново
                cylinder = [True] + [False] * 5
                random.shuffle(cylinder)
            else:
                await safe_send_message(GROUP_ID, f"🔕 <b>ЩЁЛК!</b> Камора пуста. {mention} выживает и пасы передаются далее!")
                players_queue.append(player)
                if not cylinder: # Если вдруг кончились каморы
                    cylinder = [True] + [False] * 5
                    random.shuffle(cylinder)

        except asyncio.TimeoutError:
            try: await turn_msg.edit_reply_markup(reply_markup=None)
            except: pass
            await safe_send_message(GROUP_ID, f"🐔 Время вышло! {mention} струсил, не спустил курок и <b>ДИСКВАЛИФИЦИРУЕТСЯ</b>!")

        active_turn_rr = None
        await asyncio.sleep(2.0)

    if winner:
        game_roulette_active = False
        add_win(winner['id'], "roulette")
        cur.execute("SELECT text FROM prizes WHERE game='roulette'")
        pz = cur.fetchone()
        await safe_send_message(
            GROUP_ID,
            f"🏆 <b>ЕДИНСТВЕННЫЙ ВЫЖИВШИЙ В РУЛЕТКЕ:</b> {get_mention(winner['id'], winner['un'])}\n"
            f"🎁 Приз: {pz[0] if pz else 'Не указан'}\n\nНапишите @{ADMIN_USERNAME} для получения!"
        )

# --- СТАРТ ---
async def main():
    if bot: await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
