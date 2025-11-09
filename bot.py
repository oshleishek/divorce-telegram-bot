"""
Telegram Bot для лідогенерації адвокатів (Розлучення)
Версія: 2.0 (з покращеною діагностикою)
Автор: Стас + Claude
"""

import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import json

# Налаштування логування (більш детальне)
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
GOOGLE_SHEET_NAME = os.environ.get('GOOGLE_SHEET_NAME', 'Leads - Divorce Bot')

# =====================================================
# ДЕТАЛЬНА ДІАГНОСТИКА GOOGLE SHEETS
# =====================================================

def diagnose_google_sheets():
    """Детальна діагностика підключення до Google Sheets"""
    
    logger.info("=" * 60)
    logger.info("🔍 ДІАГНОСТИКА GOOGLE SHEETS")
    logger.info("=" * 60)
    
    # Крок 1: Перевірка змінних
    required_vars = {
        'GOOGLE_PROJECT_ID': os.environ.get('GOOGLE_PROJECT_ID'),
        'GOOGLE_PRIVATE_KEY_ID': os.environ.get('GOOGLE_PRIVATE_KEY_ID'),
        'GOOGLE_PRIVATE_KEY': os.environ.get('GOOGLE_PRIVATE_KEY'),
        'GOOGLE_CLIENT_EMAIL': os.environ.get('GOOGLE_CLIENT_EMAIL'),
        'GOOGLE_CLIENT_ID': os.environ.get('GOOGLE_CLIENT_ID'),
        'GOOGLE_CERT_URL': os.environ.get('GOOGLE_CERT_URL')
    }
    
    logger.info("📋 Перевірка Environment Variables:")
    all_present = True
    for var_name, var_value in required_vars.items():
        if var_value:
            if 'KEY' in var_name and var_name != 'GOOGLE_PRIVATE_KEY_ID':
                logger.info(f"  ✅ {var_name}: присутня (довжина {len(var_value)})")
            elif 'EMAIL' in var_name:
                logger.info(f"  ✅ {var_name}: {var_value}")
            else:
                logger.info(f"  ✅ {var_name}: присутня")
        else:
            logger.error(f"  ❌ {var_name}: ВІДСУТНЯ!")
            all_present = False
    
    if not all_present:
        logger.error("❌ Відсутні деякі Environment Variables!")
        return None
    
    # Крок 2: Формування credentials
    logger.info("🔑 Формування credentials...")
    try:
        private_key = required_vars['GOOGLE_PRIVATE_KEY'].replace('\\n', '\n')
        
        # Перевіряємо формат private key
        if private_key.startswith('-----BEGIN PRIVATE KEY-----'):
            logger.info("  ✅ Private key правильно відформатований")
        else:
            logger.warning(f"  ⚠️  Private key може бути неправильно відформатований")
            logger.warning(f"  Початок: {private_key[:50]}...")
        
        creds_dict = {
            "type": "service_account",
            "project_id": required_vars['GOOGLE_PROJECT_ID'],
            "private_key_id": required_vars['GOOGLE_PRIVATE_KEY_ID'],
            "private_key": private_key,
            "client_email": required_vars['GOOGLE_CLIENT_EMAIL'],
            "client_id": required_vars['GOOGLE_CLIENT_ID'],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": required_vars['GOOGLE_CERT_URL']
        }
        
        logger.info("  ✅ Credentials dictionary створено")
        
    except Exception as e:
        logger.error(f"❌ Помилка при створенні credentials: {e}")
        return None
    
    # Крок 3: Авторизація
    logger.info("🔐 Авторизація в Google...")
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        logger.info("  ✅ Service Account credentials створено")
        
        client = gspread.authorize(creds)
        logger.info("  ✅ Авторизація успішна!")
        
    except Exception as e:
        logger.error(f"❌ Помилка авторизації: {type(e).__name__}: {e}")
        logger.error("Можливі причини:")
        logger.error("  1. Private key неправильно відформатований")
        logger.error("  2. Service Account не існує")
        logger.error("  3. Google API не ввімкнено")
        return None
    
    # Крок 4: Відкриття таблиці
    logger.info(f"📊 Відкриття таблиці '{GOOGLE_SHEET_NAME}'...")
    try:
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        logger.info(f"  ✅ Таблиця успішно відкрита!")
        
        # Перевіряємо заголовки
        try:
            headers = sheet.row_values(1)
            if headers:
                logger.info(f"  📋 Заголовки таблиці ({len(headers)} колонок):")
                for i, header in enumerate(headers[:5], 1):  # Показуємо перші 5
                    logger.info(f"     {i}. {header}")
                if len(headers) > 5:
                    logger.info(f"     ... та ще {len(headers) - 5} колонок")
            else:
                logger.warning("  ⚠️  Таблиця порожня (немає заголовків)")
        except:
            pass
        
        logger.info("=" * 60)
        logger.info("✅ ДІАГНОСТИКА ЗАВЕРШЕНА УСПІШНО!")
        logger.info("=" * 60)
        
        return sheet
        
    except gspread.SpreadsheetNotFound:
        logger.error(f"❌ ТАБЛИЦЯ НЕ ЗНАЙДЕНА: '{GOOGLE_SHEET_NAME}'")
        logger.error("")
        logger.error("Можливі причини:")
        logger.error("  1. Назва таблиці неправильна (перевірте регістр і пробіли)")
        logger.error("  2. Таблиця НЕ поділена з Service Account")
        logger.error("")
        logger.error(f"🔑 Service Account Email: {required_vars['GOOGLE_CLIENT_EMAIL']}")
        logger.error("")
        logger.error("Як поділитися таблицею:")
        logger.error("  1. Відкрийте таблицю в Google Sheets")
        logger.error("  2. Натисніть 'Share' (Поділитися)")
        logger.error(f"  3. Додайте email: {required_vars['GOOGLE_CLIENT_EMAIL']}")
        logger.error("  4. Виберіть права: 'Editor' (Редактор)")
        logger.error("  5. Зніміть галочку 'Notify people'")
        logger.error("  6. Натисніть 'Share'")
        logger.error("=" * 60)
        return None
        
    except Exception as e:
        logger.error(f"❌ Помилка відкриття таблиці: {type(e).__name__}: {e}")
        return None

def init_google_sheets():
    """Ініціалізація Google Sheets з діагностикою"""
    
    # Перевіряємо чи є всі необхідні змінні
    required_vars = ['GOOGLE_PROJECT_ID', 'GOOGLE_PRIVATE_KEY', 'GOOGLE_CLIENT_EMAIL']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        logger.warning(f"⚠️  Google Sheets не налаштовано")
        logger.warning(f"Відсутні змінні: {', '.join(missing_vars)}")
        logger.warning("Бот працюватиме, але дані не збережуться в Google Sheets")
        return None
    
    # Запускаємо детальну діагностику
    return diagnose_google_sheets()

# Ініціалізуємо sheets
SHEETS = init_google_sheets()

# =====================================================
# ЛОГІКА СЕГМЕНТАЦІЇ
# =====================================================

def determine_segment(user_data):
    """Визначає сегмент користувача"""
    has_children = user_data.get('has_children') == 'yes'
    spouse_consent = user_data.get('spouse_consent')
    property_dispute = user_data.get('property_dispute') == 'yes'
    spouse_location = user_data.get('spouse_location')
    budget = user_data.get('budget')
    
    # СЕГМЕНТ A: "Швидкий і дешевий" (30%)
    if (not has_children and 
        spouse_consent == 'yes' and 
        not property_dispute):
        return ('A', '3500-5000 грн', '2-3 місяці')
    
    # СЕГМЕНТ D: "Міжнародний" (10%)
    if spouse_location in ['abroad', 'unknown']:
        return ('D', '10000-15000 грн', '3-4 місяці (онлайн)')
    
    # СЕГМЕНТ C: "Складний розділ" (20%)
    if property_dispute and budget == 'high':
        return ('C', '15000-30000 грн', '6-12 місяців')
    
    # СЕГМЕНТ B: "Захист від агресора" (40%) - дефолтний
    return ('B', '12000 грн', '4-6 місяців')

# =====================================================
# ПЕРСОНАЛІЗОВАНІ ПОВІДОМЛЕННЯ
# =====================================================

SEGMENT_MESSAGES = {
    'A': """
🎯 <b>Ваш випадок: ШВИДКЕ РОЗЛУЧЕННЯ</b>

Чудові новини! Ваш розлучення може пройти швидко і без зайвих витрат.

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

# =====================================================
# ОБРОБНИКИ КВІЗУ (скорочено для читабельності)
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start"""
    user = update.effective_user
    context.user_data.clear()
    context.user_data['telegram_id'] = user.id
    context.user_data['username'] = user.username or ''
    context.user_data['started_at'] = datetime.now().isoformat()
    
    welcome_text = """
👋 <b>Привіт! Я допоможу розрахувати вартість і строки вашого розлучення.</b>

Це займе <b>2 хвилини</b> та абсолютно <b>безкоштовно</b>.

Відповідайте чесно — так я зможу дати точний прогноз для вашої ситуації.

Готові почати?
"""
    
    keyboard = [[InlineKeyboardButton("✅ Так, почнемо!", callback_data='start_quiz')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, parse_mode='HTML', reply_markup=reply_markup)

async def question_1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q1: Чи є діти?"""
    query = update.callback_query
    await query.answer()
    
    text = "❓ <b>Питання 1 з 8:</b>\n\nЧи є у вас спільні діти?"
    keyboard = [
        [InlineKeyboardButton("Так", callback_data='q1_yes')],
        [InlineKeyboardButton("Ні", callback_data='q1_no')]
    ]
    
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def question_2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q2: Згода супруга"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['has_children'] = 'yes' if query.data == 'q1_yes' else 'no'
    
    text = "❓ <b>Питання 2 з 8:</b>\n\nЧи згоден ваш чоловік/дружина на розлучення?"
    keyboard = [
        [InlineKeyboardButton("Так, згоден", callback_data='q2_yes')],
        [InlineKeyboardButton("Ні, проти", callback_data='q2_no')],
        [InlineKeyboardButton("Не знаю", callback_data='q2_unknown')]
    ]
    
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def question_3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q3: Розділ майна"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['spouse_consent'] = query.data.replace('q2_', '')
    
    text = "❓ <b>Питання 3 з 8:</b>\n\nЧи є спір про розділ майна (квартира, машина, інше)?"
    keyboard = [
        [InlineKeyboardButton("Так, є майно", callback_data='q3_yes')],
        [InlineKeyboardButton("Ні", callback_data='q3_no')],
        [InlineKeyboardButton("Не впевнений", callback_data='q3_unsure')]
    ]
    
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def question_4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q4: Місце супруга"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['property_dispute'] = query.data.replace('q3_', '')
    
    text = "❓ <b>Питання 4 з 8:</b>\n\nДе зараз знаходиться ваш чоловік/дружина?"
    keyboard = [
        [InlineKeyboardButton("В Україні", callback_data='q4_ukraine')],
        [InlineKeyboardButton("За кордоном", callback_data='q4_abroad')],
        [InlineKeyboardButton("Не знаю адреси", callback_data='q4_unknown')]
    ]
    
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def question_5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q5: Терміновість"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['spouse_location'] = query.data.replace('q4_', '')
    
    text = "❓ <b>Питання 5 з 8:</b>\n\nСкільки часу у вас є на процес?"
    keyboard = [
        [InlineKeyboardButton("Хочу швидко (2-3 міс)", callback_data='q5_high')],
        [InlineKeyboardButton("Не поспішаю (4-6 міс)", callback_data='q5_medium')],
        [InlineKeyboardButton("Без різниці", callback_data='q5_low')]
    ]
    
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def question_6(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q6: Бюджет"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['urgency'] = query.data.replace('q5_', '')
    
    text = "❓ <b>Питання 6 з 8:</b>\n\nЯкий бюджет ви готові виділити на послуги адвоката?"
    keyboard = [
        [InlineKeyboardButton("До 5000 грн", callback_data='q6_low')],
        [InlineKeyboardButton("5000-10000 грн", callback_data='q6_medium')],
        [InlineKeyboardButton("10000+ грн", callback_data='q6_high')],
        [InlineKeyboardButton("Не знаю", callback_data='q6_unknown')]
    ]
    
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def question_7(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q7: Ім'я"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['budget'] = query.data.replace('q6_', '')
    context.user_data['waiting_for_name'] = True
    
    text = "❓ <b>Питання 7 з 8:</b>\n\nЯк вас звати?\n\n<i>Напишіть своє ім'я текстовим повідомленням</i>"
    
    await query.edit_message_text(text, parse_mode='HTML')

async def question_8(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Q8: Номер телефону"""
    
    context.user_data['first_name'] = update.message.text
    context.user_data['waiting_for_name'] = False
    
    text = f"""
✅ Дякую, <b>{update.message.text}</b>!

❓ <b>Останнє питання 8 з 8:</b>

Поділіться номером телефону, щоб я міг відправити вам детальний розрахунок.

<i>Натисніть кнопку нижче ⬇️</i>
"""
    
    from telegram import KeyboardButton, ReplyKeyboardMarkup
    
    keyboard = [[KeyboardButton("📱 Поділитися номером", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(text, parse_mode='HTML', reply_markup=reply_markup)

async def process_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка номера телефону та завершення квізу"""
    
    contact = update.message.contact
    context.user_data['phone_number'] = contact.phone_number
    context.user_data['completed_at'] = datetime.now().isoformat()
    
    # Визначаємо сегмент
    segment, cost, time = determine_segment(context.user_data)
    context.user_data['segment'] = segment
    context.user_data['cost_estimate'] = cost
    context.user_data['time_estimate'] = time
    context.user_data['status'] = 'new'
    
    logger.info(f"📊 Новий лід: {context.user_data.get('first_name')} ({segment})")
    
    # Зберігаємо в Google Sheets
    await save_to_sheets(context.user_data)
    
    # Відправляємо webhook в Make.com
    await send_to_make(context.user_data)
    
    # Відправляємо результат
    await send_result(update, context, segment, cost, time)
    
    # Відправляємо перший оффер
    await send_first_offer(update, context)

async def save_to_sheets(user_data):
    """Зберігає дані в Google Sheets"""
    
    if SHEETS is None:
        logger.warning("⚠️  Google Sheets не підключено. Дані не збережено.")
        logger.warning(f"Дані ліда: {user_data.get('first_name')} - {user_data.get('phone_number')}")
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
            user_data.get('budget', ''),
            user_data.get('segment', ''),
            user_data.get('cost_estimate', ''),
            user_data.get('time_estimate', ''),
            user_data.get('status', 'new')
        ]
        
        SHEETS.append_row(row)
        logger.info(f"✅ Лід збережено в Google Sheets: {user_data.get('first_name')}")
        
    except Exception as e:
        logger.error(f"❌ Помилка збереження в Google Sheets: {type(e).__name__}: {e}")
        logger.error(f"Дані ліда: {json.dumps(user_data, ensure_ascii=False)}")

async def send_to_make(user_data):
    """Відправляє webhook в Make.com"""
    
    if not MAKE_WEBHOOK_URL:
        logger.info("ℹ️  Make.com webhook не налаштовано (MAKE_WEBHOOK_URL порожній)")
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
            logger.info("✅ Webhook успішно відправлено в Make.com")
        elif response.status_code == 410:
            logger.error("❌ Make.com webhook повернув 410 (Gone)")
            logger.error("Webhook був видалений або деактивований.")
            logger.error("Створи новий webhook в Make.com і оновити MAKE_WEBHOOK_URL")
        else:
            logger.warning(f"⚠️  Make.com webhook повернув код {response.status_code}")
            logger.warning(f"Response: {response.text}")
            
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout при відправці webhook в Make.com")
    except requests.exceptions.ConnectionError:
        logger.error("❌ Помилка з'єднання з Make.com")
    except Exception as e:
        logger.error(f"❌ Помилка відправки webhook: {type(e).__name__}: {e}")

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
    """Відправляє перший оффер"""
    
    offer_text = """
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
    
    keyboard = [
        [InlineKeyboardButton("📅 Записатися на консультацію", callback_data='book_consultation')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(offer_text, parse_mode='HTML', reply_markup=reply_markup)

async def book_consultation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка запису на консультацію"""
    
    query = update.callback_query
    await query.answer()
    
    user_data = context.user_data
    
    logger.info(f"🔥 ГАРЯЧИЙ ЛІД! {user_data.get('first_name')} хоче консультацію!")
    
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
            else:
                logger.warning(f"⚠️  Make.com повернув код {response.status_code}")
        except:
            logger.error("❌ Помилка відправки сповіщення про запис")
    
    text = """
✅ <b>Чудово! Запит прийнято.</b>

Наш адвокат зв'яжеться з вами <b>протягом 5-15 хвилин</b>, щоб узгодити зручний час консультації.

<i>Очікуйте дзвінок на номер:</i> <code>{phone}</code>

Якщо не зможемо дотелефонуватись, напишемо вам сюди в Telegram.

<b>Дякуємо за довіру!</b> 🙏
""".format(phone=user_data.get('phone_number'))
    
    await query.edit_message_text(text, parse_mode='HTML')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка текстових повідомлень"""
    
    if context.user_data.get('waiting_for_name'):
        await question_8(update, context)
    else:
        await update.message.reply_text(
            "Вибачте, не розумію 🤔\n\nНатисніть /start, щоб почати розрахунок."
        )

# =====================================================
# ГОЛОВНА ФУНКЦІЯ
# =====================================================

def main():
    """Запуск бота"""
    
    logger.info("=" * 60)
    logger.info("🤖 ЗАПУСК TELEGRAM БОТА")
    logger.info("=" * 60)
    
    # Створюємо Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Реєструємо обробники
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(question_1, pattern='^start_quiz$'))
    application.add_handler(CallbackQueryHandler(question_2, pattern='^q1_'))
    application.add_handler(CallbackQueryHandler(question_3, pattern='^q2_'))
    application.add_handler(CallbackQueryHandler(question_4, pattern='^q3_'))
    application.add_handler(CallbackQueryHandler(question_5, pattern='^q4_'))
    application.add_handler(CallbackQueryHandler(question_6, pattern='^q5_'))
    application.add_handler(CallbackQueryHandler(question_7, pattern='^q6_'))
    application.add_handler(CallbackQueryHandler(book_consultation, pattern='^book_consultation$'))
    application.add_handler(MessageHandler(filters.CONTACT, process_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаємо бота
    logger.info("🚀 Бот запущено!")
    logger.info("=" * 60)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
