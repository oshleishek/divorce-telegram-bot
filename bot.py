"""
Telegram Bot для лідогенерації адвокатів (Розлучення)
Версія: 3.0 ULTIMATE
Автор: Стас + Claude

ЗМІНИ В v3.0:
- ✅ Аналітика конверсії на кожному етапі (окремий лист Analytics)
- ✅ Збір @username одразу при /start (окремий лист All_Users)
- ✅ Отримання імені з contact (видалено питання Q7 про ім'я)
- ✅ Видалено питання про бюджет (було Q6)
- ✅ Всі тексти помічені для легкого редагування
- ✅ Конфеті при записі на консультацію
- ✅ Flask web-server для Render (щоб не засипав)
"""


import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReactionTypeEmoji
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
from flask import Flask
import threading

# =====================================================
# НАЛАШТУВАННЯ ЛОГУВАННЯ
# =====================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =====================================================
# КОНСТАНТИ
# =====================================================

BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
MAKE_WEBHOOK_URL = os.environ.get('MAKE_WEBHOOK_URL', '')
GOOGLE_SHEET_URL = os.environ.get('GOOGLE_SHEET_URL')

# =====================================================
# ПІДКЛЮЧЕННЯ ДО GOOGLE SHEETS
# =====================================================

def init_google_sheets():
    """Ініціалізація підключення до Google Sheets"""
    try:
        required_vars = [
            'GOOGLE_PROJECT_ID', 
            'GOOGLE_PRIVATE_KEY', 
            'GOOGLE_CLIENT_EMAIL',
            'GOOGLE_SHEET_URL'
        ]
        missing_vars = [var for var in required_vars if not os.environ.get(var)]
        
        if missing_vars:
            logger.warning(f"⚠️ Google Sheets не налаштовано (відсутні змінні: {', '.join(missing_vars)})")
            return None, None, None
        
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        creds_dict = {
            "type": "service_account",
            "project_id": os.environ.get('GOOGLE_PROJECT_ID'),
            "private_key_id": os.environ.get('GOOGLE_PRIVATE_KEY_ID'),
            "private_key": os.environ.get('GOOGLE_PRIVATE_KEY', '').replace('\\n', '\n'),
            "client_email": os.environ.get('GOOGLE_CLIENT_EMAIL'),
            "client_id": os.environ.get('GOOGLE_CLIENT_ID'),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": os.environ.get('GOOGLE_CERT_URL')
        }
        
        logger.info("🔄 Підключення до Google Sheets...")
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        logger.info(f"🔄 Відкриваю таблицю по URL...")
        spreadsheet = client.open_by_url(GOOGLE_SHEET_URL)
        
        # Отримуємо або створюємо листи
        try:
            leads_sheet = spreadsheet.worksheet("Leads")
        except gspread.WorksheetNotFound:
            leads_sheet = spreadsheet.add_worksheet("Leads", rows=1000, cols=15)
            # Додаємо заголовки
            leads_sheet.append_row([
                "Дата завершення", "Telegram ID", "Username", "Ім'я", "Телефон",
                "Діти", "Згода супруга", "Майно", "Місце супруга", "Терміновість",
                "Сегмент", "Вартість", "Строки", "Статус"
            ])
        
        try:
            analytics_sheet = spreadsheet.worksheet("Analytics")
        except gspread.WorksheetNotFound:
            analytics_sheet = spreadsheet.add_worksheet("Analytics", rows=5000, cols=10)
            analytics_sheet.append_row([
                "Timestamp", "Telegram ID", "Username", "Event", "Details"
            ])
        
        try:
            all_users_sheet = spreadsheet.worksheet("All_Users")
        except gspread.WorksheetNotFound:
            all_users_sheet = spreadsheet.add_worksheet("All_Users", rows=5000, cols=10)
            all_users_sheet.append_row([
                "Дата першого контакту", "Telegram ID", "Username", 
                "First Name", "Last Name", "Завершив квіз", "Статус"
            ])
        
        logger.info(f"✅ Google Sheets підключено успішно")
        logger.info(f"  📊 Leads: {leads_sheet.title}")
        logger.info(f"  📈 Analytics: {analytics_sheet.title}")
        logger.info(f"  👥 All Users: {all_users_sheet.title}")
        
        return leads_sheet, analytics_sheet, all_users_sheet
        
    except Exception as e:
        logger.error(f"❌ Помилка підключення до Google Sheets: {type(e).__name__}: {str(e)}")
        return None, None, None

# Ініціалізуємо sheets
SHEETS_LEADS, SHEETS_ANALYTICS, SHEETS_ALL_USERS = init_google_sheets()

# =====================================================
# АНАЛІТИКА - ЛОГУВАННЯ ПОДІЙ
# =====================================================

async def log_event(telegram_id, username, event, details=""):
    """
    Логує кожну подію користувача для аналітики конверсії
    
    Події:
    - /start
    - quiz_started
    - q1_answered, q2_answered, q3_answered, q4_answered, q5_answered, q6_answered
    - phone_shared
    - consultation_booked
    """
    
    if SHEETS_ANALYTICS is None:
        return
    
    try:
        row = [
            datetime.now().isoformat(),
            str(telegram_id),
            username or "",
            event,
            details
        ]
        
        SHEETS_ANALYTICS.append_row(row)
        logger.info(f"📊 Analytics: {telegram_id} → {event}")
        
    except Exception as e:
        logger.error(f"❌ Помилка логування події: {e}")

async def save_all_user(telegram_id, username, first_name, last_name):
    """
    Зберігає ВСІХ користувачів, хто натиснув /start
    Навіть якщо не завершили квіз
    """
    
    if SHEETS_ALL_USERS is None:
        return
    
    try:
        # Перевіряємо чи вже є такий користувач
        existing = SHEETS_ALL_USERS.find(str(telegram_id), in_column=2)
        if existing:
            logger.info(f"👥 Користувач {telegram_id} вже в базі")
            return
        
        row = [
            datetime.now().isoformat(),
            str(telegram_id),
            username or "",
            first_name or "",
            last_name or "",
            "Ні",  # Завершив квіз
            "new"   # Статус
        ]
        
        SHEETS_ALL_USERS.append_row(row)
        logger.info(f"👥 Новий користувач в базі: {username or telegram_id}")
        
    except Exception as e:
        logger.error(f"❌ Помилка збереження користувача: {e}")

# =====================================================
# WEB-СЕРВЕР ДЛЯ RENDER (ЩОБ НЕ ЗАСИНАВ)
# =====================================================

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Divorce Bot is running!", 200

@app.route('/health')
def health():
    return {"status": "ok", "bot": "running"}, 200

def run_flask():
    """Запуск Flask в окремому потоці"""
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# =====================================================
# ЛОГІКА СЕГМЕНТАЦІЇ
# =====================================================

def determine_segment(user_data):
    """Визначає сегмент користувача на основі відповідей"""
    
    has_children = user_data.get('has_children') == 'yes'
    spouse_consent = user_data.get('spouse_consent')
    property_dispute = user_data.get('property_dispute') == 'yes'
    spouse_location = user_data.get('spouse_location')
    
    # СЕГМЕНТ A: "Швидкий і дешевий" (30%)
    if (not has_children and 
        spouse_consent == 'yes' and 
        not property_dispute):
        return ('A', '3500-5000 грн', '2-3 місяці')
    
    # СЕГМЕНТ D: "Міжнародний" (10%)
    if spouse_location in ['abroad', 'unknown']:
        return ('D', '10000-15000 грн', '3-4 місяці (онлайн)')
    
    # СЕГМЕНТ C: "Складний розділ" (20%)
    if property_dispute and has_children:
        return ('C', '15000-30000 грн', '6-12 місяців')
    
    # СЕГМЕНТ B: "Захист від агресора" (40%) - дефолтний
    return ('B', '12000 грн', '4-6 місяців')

# =====================================================
# 📝 ТЕКСТИ ДЛЯ КОРИСТУВАЧА
# =====================================================
# ⚠️ УВАГА: Тут всі тексти, які бачить користувач
# Можеш змінювати без програміста
# =====================================================

# 📝 ТЕКСТ: Привітання при /start
TEXT_WELCOME = """
👋 <b>Привіт! Я допоможу розрахувати вартість і строки вашого розлучення.</b>

Це займе <b>2 хвилини</b> та абсолютно <b>безкоштовно</b>.

Відповідайте чесно — так я зможу дати точний прогноз для вашої ситуації.

Готові почати?
"""

# 📝 ТЕКСТ: Питання 1 (Діти)
TEXT_Q1 = "❓ <b>Питання 1 з 6:</b>\n\nЧи є у вас спільні діти?"

# 📝 ТЕКСТ: Питання 2 (Згода супруга)
TEXT_Q2 = "❓ <b>Питання 2 з 6:</b>\n\nЧи згоден ваш чоловік/дружина на розлучення?"

# 📝 ТЕКСТ: Питання 3 (Розділ майна)
TEXT_Q3 = "❓ <b>Питання 3 з 6:</b>\n\nЧи є спір про розділ майна (квартира, машина, інше)?"

# 📝 ТЕКСТ: Питання 4 (Місце супруга)
TEXT_Q4 = "❓ <b>Питання 4 з 6:</b>\n\nДе зараз знаходиться ваш чоловік/дружина?"

# 📝 ТЕКСТ: Питання 5 (Терміновість)
TEXT_Q5 = "❓ <b>Питання 5 з 6:</b>\n\nСкільки часу у вас є на процес?"

# 📝 ТЕКСТ: Питання 6 (Запит номера телефону)
TEXT_Q6_PHONE = """
✅ Дякую за відповіді!

❓ <b>Останнє питання 6 з 6:</b>

Поділіться номером телефону, щоб я міг відправити вам детальний розрахунок.

<i>Натисніть кнопку нижче ⬇️</i>
"""

# 📝 ТЕКСТ: Результати по сегментах
SEGMENT_MESSAGES = {
    'A': """
🎯 <b>Ваш випадок: ШВИДКЕ РОЗЛУЧЕННЯ</b>

Чудові новини! Ваше розлучення може пройти швидко і без зайвих витрат.

💰 <b>Орієнтовна вартість:</b> {cost}
⏱ <b>Орієнтовні строки:</b> {time}

<b>Що входить:</b>
✅ Підготовка позовної заяви
✅ Подання до суду
✅ Представництво на 1 засіданні
✅ Отримання рішення суду

<i>Оскільки у вас немає дітей та є згода супруга, процес буде максимально простим.</i>
""",
    
    'B': """
🛡 <b>Ваш випадок: ЗАХИСТ ІНТЕРЕСІВ</b>

Розумію, що ваша ситуація непроста. Але у нас є досвід успішного вирішення таких справ.

💰 <b>Орієнтовна вартість:</b> {cost}
⏱ <b>Орієнтовні строки:</b> {time}

<b>Що входить:</b>
✅ Підготовка всіх документів
✅ Стратегія захисту ваших інтересів
✅ Представництво на всіх засіданнях
✅ Захист інтересів дитини
✅ Переговори з протилежною стороною

<i>Оскільки є діти та немає згоди супруга, важливо мати професійного адвоката.</i>
""",
    
    'C': """
💼 <b>Ваш випадок: СКЛАДНИЙ РОЗДІЛ МАЙНА</b>

Ваш випадок вимагає особливої уваги та професіоналізму.

💰 <b>Орієнтовна вартість:</b> {cost}
⏱ <b>Орієнтовні строки:</b> {time}

<b>Що входить:</b>
✅ Аналіз всього спільного майна
✅ Залучення оцінювачів (за потреби)
✅ Стратегія справедливого розділу
✅ Представництво на всіх засіданнях
✅ Захист від приховування активів

<i>Розділ майна — це складний процес. Без досвідченого адвоката можна втратити значну частину активів.</i>
""",
    
    'D': """
🌍 <b>Ваш випадок: МІЖНАРОДНЕ РОЗЛУЧЕННЯ</b>

Ваш випадок має свої особливості, але це не перешкода!

💰 <b>Орієнтовна вартість:</b> {cost}
⏱ <b>Орієнтовні строки:</b> {time}

<b>Що входить:</b>
✅ Розлучення БЕЗ вашої присутності в суді
✅ Всі документи онлайн
✅ Представництво на всіх засіданнях
✅ Отримання рішення суду
✅ Доставка документів за кордон

<i>Ви можете розлучитися навіть перебуваючи за кордоном. Ми все зробимо за вас.</i>
"""
}

# 📝 ТЕКСТ: Перший оффер (зі знижкою)
TEXT_FIRST_OFFER = """
🎁 <b>СПЕЦІАЛЬНА ПРОПОЗИЦІЯ</b> (діє 24 години)

<b>Консультація з адвокатом зі знижкою 50%</b>
<s>2000 грн</s> → <b>990 грн</b>

На консультації ви:
✅ Отримаєте покроковий план дій
✅ Дізнаєтесь про ризики та як їх уникнути
✅ Зможете задати всі питання адвокату

<b>Бонус:</b> Якщо вирішите працювати з нами, 990 грн повністю зараховуються в оплату послуг!

⏰ <i>Пропозиція діє лише 24 години після отримання результату.</i>
"""

# 📝 ТЕКСТ: Підтвердження запису на консультацію
TEXT_CONSULTATION_BOOKED = """
✅ <b>Чудово! Запит прийнято.</b>

Наш адвокат зв'яжеться з вами <b>протягом 5-15 хвилин</b>, щоб узгодити зручний час консультації.

<i>Очікуйте дзвінок на номер:</i> <code>{phone}</code>

Якщо не зможемо дотелефонуватись, напишемо вам сюди в Telegram.

<b>Дякуємо за довіру!</b> 🙏
"""

# 📝 ТЕКСТ: Якщо користувач пише щось не до речі
TEXT_UNKNOWN_MESSAGE = "Вибачте, не розумію 🤔\n\nНатисніть /start, щоб почати розрахунок."

# 📝 ТЕКСТ: Нагадування поділитися номером
TEXT_PHONE_REMINDER = """
👋 Здається, ви не натиснули кнопку...

Щоб отримати ваш персональний розрахунок, будь ласка, натисніть кнопку «📱 Поділитися номером».

Це абсолютно безпечно і потрібно лише для того, щоб відправити вам результат.
"""

# 📝 ТЕКСТ: Нагадування про незавершений квіз
TEXT_QUIZ_REMINDER = """
👋 Здається, ви відволіклися...

Ми зупинилися на півдорозі до розрахунку вартості. Бажаєте продовжити?

Просто натисніть /start, щоб почати заново (це швидко!), або дайте відповідь на останнє запитання, якщо воно ще на екрані.
"""

# =====================================================
# ОБРОБНИКИ КОМАНД
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start - початок квізу"""
    
    user = update.effective_user

    await remove_quiz_reminder(context, user.id)
    
    # Зберігаємо користувача в базу "All Users" (ВСІХ хто натиснув /start)
    await save_all_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Логуємо подію
    await log_event(user.id, user.username, "/start", "Користувач почав взаємодію")
    
    # Ініціалізуємо дані користувача
    context.user_data.clear()
    context.user_data['telegram_id'] = user.id
    context.user_data['username'] = user.username or ''
    context.user_data['started_at'] = datetime.now().isoformat()
    
    keyboard = [[InlineKeyboardButton("✅ Так, почнемо!", callback_data='start_quiz')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        TEXT_WELCOME,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# =====================================================
# ОБРОБНИКИ КВІЗУ
# =====================================================

async def question_1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q1: Чи є діти?"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    await log_event(user_id, username, "quiz_started", "Користувач почав квіз")
    
    keyboard = [
        [InlineKeyboardButton("Так", callback_data='q1_yes')],
        [InlineKeyboardButton("Ні", callback_data='q1_no')]
    ]
    
    await query.edit_message_text(
        TEXT_Q1,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await schedule_quiz_reminder(context, user_id, query.message.chat_id)

async def question_2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q2: Згода супруга"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    # Зберігаємо відповідь
    context.user_data['has_children'] = 'yes' if query.data == 'q1_yes' else 'no'
    
    await log_event(user_id, username, "q1_answered", f"has_children={context.user_data['has_children']}")
    
    keyboard = [
        [InlineKeyboardButton("Так, згоден", callback_data='q2_yes')],
        [InlineKeyboardButton("Ні, проти", callback_data='q2_no')],
        [InlineKeyboardButton("Не знаю", callback_data='q2_unknown')]
    ]
    
    await query.edit_message_text(
        TEXT_Q2,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await schedule_quiz_reminder(context, user_id, query.message.chat_id)

async def question_3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q3: Розділ майна"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    context.user_data['spouse_consent'] = query.data.replace('q2_', '')
    
    await log_event(user_id, username, "q2_answered", f"spouse_consent={context.user_data['spouse_consent']}")
    
    keyboard = [
        [InlineKeyboardButton("Так, є майно", callback_data='q3_yes')],
        [InlineKeyboardButton("Ні", callback_data='q3_no')],
        [InlineKeyboardButton("Не впевнений", callback_data='q3_unsure')]
    ]
    
    await query.edit_message_text(
        TEXT_Q3,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await schedule_quiz_reminder(context, user_id, query.message.chat_id)

async def question_4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q4: Місце супруга"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    context.user_data['property_dispute'] = query.data.replace('q3_', '')
    
    await log_event(user_id, username, "q3_answered", f"property_dispute={context.user_data['property_dispute']}")
    
    keyboard = [
        [InlineKeyboardButton("В Україні", callback_data='q4_ukraine')],
        [InlineKeyboardButton("За кордоном", callback_data='q4_abroad')],
        [InlineKeyboardButton("Не знаю адреси", callback_data='q4_unknown')]
    ]
    
    await query.edit_message_text(
        TEXT_Q4,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await schedule_quiz_reminder(context, user_id, query.message.chat_id)

async def question_5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q5: Терміновість"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    context.user_data['spouse_location'] = query.data.replace('q4_', '')
    
    await log_event(user_id, username, "q4_answered", f"spouse_location={context.user_data['spouse_location']}")
    
    keyboard = [
        [InlineKeyboardButton("Хочу швидко (2-3 міс)", callback_data='q5_high')],
        [InlineKeyboardButton("Не поспішаю (4-6 міс)", callback_data='q5_medium')],
        [InlineKeyboardButton("Без різниці", callback_data='q5_low')]
    ]
    
    await query.edit_message_text(
        TEXT_Q5,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    await schedule_quiz_reminder(context, user_id, query.message.chat_id)

async def question_6_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q6: Запит номера телефону (останнє питання)"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    context.user_data['urgency'] = query.data.replace('q5_', '')
    
    await log_event(user_id, username, "q5_answered", f"urgency={context.user_data['urgency']}")

    await remove_quiz_reminder(context, user_id)
    
    from telegram import KeyboardButton, ReplyKeyboardMarkup
    
    keyboard = [[KeyboardButton("📱 Поділитися номером", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await query.edit_message_text(TEXT_Q6_PHONE, parse_mode='HTML')
    
    # Відправляємо окреме повідомлення з кнопкою
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="👇 Натисніть кнопку нижче:",
        reply_markup=reply_markup
    )

    chat_id = query.message.chat_id
    
    # Запускаємо таймер на 60 секунд
    context.job_queue.run_once(
        phone_reminder_callback,  # Функція, яку треба викликати
        60,                       # Через скільки секунд
        chat_id=chat_id,          # ID чату
        user_id=user_id,          # ID юзера
    )

async def process_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка номера телефону та завершення квізу"""
    
    contact = update.message.contact
    user = update.effective_user
    
    # Отримуємо ім'я з contact (не питаємо окремо!)
    first_name = contact.first_name or user.first_name or "Клієнт"
    last_name = contact.last_name or user.last_name or ""
    
    context.user_data['first_name'] = first_name
    context.user_data['last_name'] = last_name
    context.user_data['phone_number'] = contact.phone_number
    context.user_data['completed_at'] = datetime.now().isoformat()
    
    user_id = user.id
    username = user.username
    
    await log_event(user_id, username, "phone_shared", f"{first_name} - {contact.phone_number}")
    
    # Оновлюємо статус в All_Users
    if SHEETS_ALL_USERS:
        try:
            cell = SHEETS_ALL_USERS.find(str(user_id), in_column=2)
            if cell:
                SHEETS_ALL_USERS.update_cell(cell.row, 6, "Так")  # Завершив квіз
        except:
            pass
    
    # Визначаємо сегмент
    segment, cost, time = determine_segment(context.user_data)
    context.user_data['segment'] = segment
    context.user_data['cost_estimate'] = cost
    context.user_data['time_estimate'] = time
    context.user_data['status'] = 'new'
    
    logger.info(f"📊 Новий лід: {first_name} ({segment})")
    
    # Зберігаємо в Google Sheets (Leads)
    await save_to_sheets(context.user_data)
    
    # Відправляємо webhook в Make.com
    await send_to_make(context.user_data)
    
    # Відправляємо результат
    await send_result(update, context, segment, cost, time)
    
    # Відправляємо перший оффер
    await send_first_offer(update, context)

async def save_to_sheets(user_data):
    """Зберігає дані ліда в Google Sheets (Leads)"""
    
    if SHEETS_LEADS is None:
        logger.warning("⚠️ Google Sheets не підключено. Дані не збережено.")
        return
    
    try:
        row = [
            user_data.get('completed_at', ''),
            str(user_data.get('telegram_id', '')),
            user_data.get('username', ''),
            user_data.get('first_name', ''),
            user_data.get('phone_number', ''),
            user_data.get('has_children', ''),
            user_data.get('spouse_consent', ''),
            user_data.get('property_dispute', ''),
            user_data.get('spouse_location', ''),
            user_data.get('urgency', ''),
            user_data.get('segment', ''),
            user_data.get('cost_estimate', ''),
            user_data.get('time_estimate', ''),
            user_data.get('status', 'new')
        ]
        
        SHEETS_LEADS.append_row(row)
        logger.info(f"✅ Лід збережено в Google Sheets: {user_data.get('first_name')}")
        
    except Exception as e:
        logger.error(f"❌ Помилка збереження в Google Sheets: {e}")

async def send_to_make(user_data):
    """Відправляє webhook в Make.com"""
    
    if not MAKE_WEBHOOK_URL:
        logger.info("ℹ️ Make.com webhook не налаштовано")
        return
    
    try:
        payload = {
            'event': 'new_lead',
            'telegram_id': user_data.get('telegram_id'),
            'first_name': user_data.get('first_name'),
            'phone_number': user_data.get('phone_number'),
            'segment': user_data.get('segment'),
            'cost_estimate': user_data.get('cost_estimate'),
            'time_estimate': user_data.get('time_estimate'),
            'completed_at': user_data.get('completed_at')
        }
        
        response = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=5)
        
        if response.status_code == 200:
            logger.info("✅ Webhook відправлено в Make.com")
        else:
            logger.warning(f"⚠️ Make.com webhook повернув код {response.status_code}")
            
    except Exception as e:
        logger.error(f"❌ Помилка відправки webhook: {e}")

async def send_result(update: Update, context: ContextTypes.DEFAULT_TYPE, segment, cost, time):
    """Відправляє персоналізований результат"""
    
    from telegram import ReplyKeyboardRemove
    
    message_template = SEGMENT_MESSAGES.get(segment, SEGMENT_MESSAGES['B'])
    result_text = message_template.format(cost=cost, time=time)
    
    await update.message.reply_text(
        result_text,
        parse_mode='HTML',
        reply_markup=ReplyKeyboardRemove()
    )

async def send_first_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Відправляє перший оффер зі знижкою"""
    
    keyboard = [
        [InlineKeyboardButton("📅 Записатися на консультацію", callback_data='book_consultation')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        TEXT_FIRST_OFFER,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def book_consultation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка запису на консультацію"""
    
    query = update.callback_query
    await query.answer()
    
    user_data = context.user_data
    user_id = update.effective_user.id
    username = update.effective_user.username
    
    logger.info(f"🔥 ГАРЯЧИЙ ЛІД! {user_data.get('first_name')} хоче консультацію!")
    
    await log_event(user_id, username, "consultation_booked", "Клієнт записався на консультацію!")
    
    # Оновлюємо статус в All_Users
    if SHEETS_ALL_USERS:
        try:
            cell = SHEETS_ALL_USERS.find(str(user_id), in_column=2)
            if cell:
                SHEETS_ALL_USERS.update_cell(cell.row, 7, "scheduled")  # Статус
        except:
            pass
    
    # Відправляємо сповіщення в Make.com
    if MAKE_WEBHOOK_URL:
        try:
            payload = {
                'event': 'consultation_request',
                'telegram_id': user_data.get('telegram_id'),
                'first_name': user_data.get('first_name'),
                'phone_number': user_data.get('phone_number'),
                'segment': user_data.get('segment')
            }
            response = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=5)
            
            if response.status_code == 200:
                logger.info("✅ Сповіщення про запис відправлено в Make.com")
        except:
            pass
    
    text = TEXT_CONSULTATION_BOOKED.format(phone=user_data.get('phone_number'))
    
    await query.edit_message_text(text, parse_mode='HTML')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка текстових повідомлень"""
    
    await update.message.reply_text(TEXT_UNKNOWN_MESSAGE)

# =====================================================
# ХЕЛПЕРИ ДЛЯ НАГАДУВАНЬ КВІЗУ
# =====================================================

def get_quiz_job_name(user_id: int) -> str:
    """Повертає унікальне ім'я для задачі нагадування про квіз"""
    return f"quiz_reminder_{user_id}"

async def schedule_quiz_reminder(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int):
    """
    Планує нагадування про квіз через 15 хвилин.
    Спочатку видаляє всі попередні нагадування для цього юзера.
    """
    job_name = get_quiz_job_name(user_id)
    
    # 1. Видаляємо старі задачі (якщо є)
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()
            logger.info(f"⏰ [JobQueue] Cкасовано старе нагадування {job_name}")

    # 2. Ставимо нову задачу
    context.job_queue.run_once(
        quiz_reminder_callback,
        900,  # 900 секунд = 15 хвилин. (Можеш змінити на 600 = 10 хв)
        chat_id=chat_id,
        user_id=user_id,
        name=job_name
    )
    logger.info(f"⏰ [JobQueue] Заплановано нагадування {job_name} через 15 хв")

async def remove_quiz_reminder(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Повністю видаляє нагадування про квіз (коли квіз завершено)"""
    job_name = get_quiz_job_name(user_id)
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()
        logger.info(f"⏰ [JobQueue] Квіз завершено. Видаляю нагадування {job_name}")

async def phone_reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    """
    Відправляє нагадування, якщо користувач не поділився номером
    """
    job = context.job
    user_id = job.user_id
    
    logger.info(f"⏰ [JobQueue] ЗАВДАННЯ-НАГАДУВАННЯ СПРАЦЮВАЛО для user_id: {user_id}")

    # Отримуємо user_data
    user_data = context.application.user_data.get(user_id)

    if not user_data:
        logger.warning(f"⏰ [JobQueue] Не вдалося знайти user_data для {user_id}. Можливо, бот перезапускався.")
        # Навіть якщо даних немає, номера теж немає. Тож відправляємо.
    
    # Перевіряємо наявність номера
    phone_exists = user_data and 'phone_number' in user_data
    
    # --- ДЕТАЛЬНІ ЛОГИ ---
    logger.info(f"⏰ [JobQueue] Вміст user_data для {user_id}: {user_data}")
    logger.info(f"⏰ [JobQueue] Перевірка: 'phone_number' існує? {phone_exists}")
    # --- КІНЕЦЬ ЛОГІВ ---

    if phone_exists:
        logger.info(f"⏰ [JobQueue] Нагадування для {user_id} скасовано (вже є номер).")
        return # Користувач вже відповів, нічого не робимо

    # Якщо номера ще немає - відправляємо нагадування
    logger.info(f"⏰ [JobQueue] ВІДПРАВЛЯЮ нагадування про номер для {user_id}")
    
    # Створюємо кнопку знову
    from telegram import KeyboardButton, ReplyKeyboardMarkup
    keyboard = [[KeyboardButton("📱 Поділитися номером", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await context.bot.send_message(
        chat_id=job.chat_id,
        text=TEXT_PHONE_REMINDER, # Використовуємо новий текст
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def quiz_reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    """
    Відправляє нагадування, якщо користувач "застряг" на квізі
    """
    job = context.job
    user_id = job.user_id
    
    # Перевіряємо, чи юзер вже закінчив квіз (чи є в нього номер)
    user_data = context.application.user_data.get(user_id, {})
    if 'phone_number' in user_data:
        logger.info(f"⏰ [JobQueue] Нагадування {job.name} скасовано (квіз вже пройдено)")
        return

    # Якщо квіз не пройдено - відправляємо нагадування
    logger.info(f"⏰ [JobQueue] ВІДПРАВЛЯЮ нагадування про квіз для {user_id}")
    await context.bot.send_message(
        chat_id=job.chat_id,
        text=TEXT_QUIZ_REMINDER,
        parse_mode='HTML'
    )

# =====================================================
# ГОЛОВНА ФУНКЦІЯ
# =====================================================

def main():
    """Запуск бота"""
    
    logger.info("=" * 60)
    logger.info("🤖 ЗАПУСК TELEGRAM БОТА v3.0 ULTIMATE")
    logger.info("=" * 60)
    
    # Запускаємо Flask в окремому потоці (для Render)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask web-server запущено")
    
    # Створюємо Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Реєструємо обробники
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(question_1, pattern='^start_quiz$'))
    application.add_handler(CallbackQueryHandler(question_2, pattern='^q1_'))
    application.add_handler(CallbackQueryHandler(question_3, pattern='^q2_'))
    application.add_handler(CallbackQueryHandler(question_4, pattern='^q3_'))
    application.add_handler(CallbackQueryHandler(question_5, pattern='^q4_'))
    application.add_handler(CallbackQueryHandler(question_6_phone, pattern='^q5_'))
    application.add_handler(CallbackQueryHandler(book_consultation, pattern='^book_consultation$'))
    application.add_handler(MessageHandler(filters.CONTACT, process_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаємо бота
    logger.info("🚀 Бот запущено!")
    logger.info("=" * 60)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
