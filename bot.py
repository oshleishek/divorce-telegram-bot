"""
Telegram Bot для лідогенерації адвокатів (Розлучення)
Автор: Стас + Claude
Версія: 1.0
"""

import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =====================================================
# КОНСТАНТИ (змінюй тут свої значення)
# =====================================================

# Токен бота (отримай від @BotFather)
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# Webhook для Make.com (для сповіщень про нові ліди)
MAKE_WEBHOOK_URL = os.environ.get('MAKE_WEBHOOK_URL', '')

# Google Sheets налаштування
GOOGLE_SHEET_NAME = os.environ.get('GOOGLE_SHEET_NAME', 'Leads - Divorce Bot')

# =====================================================
# ПІДКЛЮЧЕННЯ ДО GOOGLE SHEETS
# =====================================================

def init_google_sheets():
    """Ініціалізація підключення до Google Sheets"""
    try:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        
        # Credentials з environment variables (для безпеки)
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
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open(GOOGLE_SHEET_NAME).sheet1
        
        logger.info("✅ Google Sheets підключено успішно")
        return sheet
    except Exception as e:
        logger.error(f"❌ Помилка підключення до Google Sheets: {e}")
        return None

# Ініціалізуємо sheets (або None якщо не налаштовано)
SHEETS = init_google_sheets()

# =====================================================
# ЛОГІКА СЕГМЕНТАЦІЇ
# =====================================================

def determine_segment(user_data):
    """
    Визначає сегмент користувача на основі відповідей
    Повертає: ('A'|'B'|'C'|'D', вартість, строки)
    """
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
    if has_children and spouse_consent == 'no':
        return ('B', '12000 грн', '4-6 місяців')
    
    # Дефолтний сегмент якщо не підпало під жодну категорію
    return ('B', '12000 грн', '4-6 місяців')

# =====================================================
# ПЕРСОНАЛІЗОВАНІ ПОВІДОМЛЕННЯ ДЛЯ РЕЗУЛЬТАТУ
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
# ОБРОБНИКИ КОМАНД
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробник команди /start - початок квізу"""
    
    user = update.effective_user
    
    # Ініціалізуємо дані користувача
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
    
    keyboard = [
        [InlineKeyboardButton("✅ Так, почнемо!", callback_data='start_quiz')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text, 
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def question_1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Питання 1: Чи є діти?"""
    
    query = update.callback_query
    await query.answer()
    
    text = """
❓ <b>Питання 1 з 8</b>

Чи є у вас спільні діти?
"""
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Так", callback_data='q1_yes'),
            InlineKeyboardButton("❌ Ні", callback_data='q1_no')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def question_2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Питання 2: Згода супруга"""
    
    query = update.callback_query
    await query.answer()
    
    # Зберігаємо відповідь на Q1
    answer = 'yes' if 'yes' in query.data else 'no'
    context.user_data['has_children'] = answer
    
    text = """
❓ <b>Питання 2 з 8</b>

Чи згоден чоловік/дружина на розлучення?
"""
    
    keyboard = [
        [InlineKeyboardButton("✅ Так, згоден/на", callback_data='q2_yes')],
        [InlineKeyboardButton("❌ Ні, проти", callback_data='q2_no')],
        [InlineKeyboardButton("🤷 Не знаю", callback_data='q2_unknown')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def question_3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Питання 3: Розділ майна"""
    
    query = update.callback_query
    await query.answer()
    
    # Зберігаємо відповідь на Q2
    if 'yes' in query.data:
        context.user_data['spouse_consent'] = 'yes'
    elif 'no' in query.data:
        context.user_data['spouse_consent'] = 'no'
    else:
        context.user_data['spouse_consent'] = 'unknown'
    
    text = """
❓ <b>Питання 3 з 8</b>

Чи є спір про розділ майна?
(квартира, будинок, автомобіль, бізнес тощо)
"""
    
    keyboard = [
        [InlineKeyboardButton("✅ Так, є майно", callback_data='q3_yes')],
        [InlineKeyboardButton("❌ Ні", callback_data='q3_no')],
        [InlineKeyboardButton("🤷 Не впевнений/на", callback_data='q3_unsure')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def question_4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Питання 4: Місцезнаходження супруга"""
    
    query = update.callback_query
    await query.answer()
    
    # Зберігаємо відповідь на Q3
    if 'yes' in query.data:
        context.user_data['property_dispute'] = 'yes'
    elif 'no' in query.data:
        context.user_data['property_dispute'] = 'no'
    else:
        context.user_data['property_dispute'] = 'unsure'
    
    text = """
❓ <b>Питання 4 з 8</b>

Де зараз знаходиться ваш чоловік/дружина?
"""
    
    keyboard = [
        [InlineKeyboardButton("🇺🇦 В Україні", callback_data='q4_ukraine')],
        [InlineKeyboardButton("✈️ За кордоном", callback_data='q4_abroad')],
        [InlineKeyboardButton("❓ Не знаю адреси", callback_data='q4_unknown')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def question_5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Питання 5: Терміновість"""
    
    query = update.callback_query
    await query.answer()
    
    # Зберігаємо відповідь на Q4
    if 'ukraine' in query.data:
        context.user_data['spouse_location'] = 'ukraine'
    elif 'abroad' in query.data:
        context.user_data['spouse_location'] = 'abroad'
    else:
        context.user_data['spouse_location'] = 'unknown'
    
    text = """
❓ <b>Питання 5 з 8</b>

Скільки часу у вас є на процес розлучення?
"""
    
    keyboard = [
        [InlineKeyboardButton("⚡️ Хочу швидко (2-3 міс)", callback_data='q5_high')],
        [InlineKeyboardButton("⏳ Не поспішаю (4-6 міс)", callback_data='q5_medium')],
        [InlineKeyboardButton("🤷 Без різниці", callback_data='q5_low')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def question_6(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Питання 6: Бюджет"""
    
    query = update.callback_query
    await query.answer()
    
    # Зберігаємо відповідь на Q5
    if 'high' in query.data:
        context.user_data['urgency'] = 'high'
    elif 'medium' in query.data:
        context.user_data['urgency'] = 'medium'
    else:
        context.user_data['urgency'] = 'low'
    
    text = """
❓ <b>Питання 6 з 8</b>

Який бюджет ви готові виділити на послуги адвоката?
"""
    
    keyboard = [
        [InlineKeyboardButton("💵 До 5000 грн", callback_data='q6_low')],
        [InlineKeyboardButton("💰 5000-10000 грн", callback_data='q6_medium')],
        [InlineKeyboardButton("💎 10000+ грн", callback_data='q6_high')],
        [InlineKeyboardButton("🤷 Не знаю", callback_data='q6_unknown')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def question_7(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Питання 7: Ім'я"""
    
    query = update.callback_query
    await query.answer()
    
    # Зберігаємо відповідь на Q6
    if 'low' in query.data:
        context.user_data['budget'] = 'low'
    elif 'medium' in query.data:
        context.user_data['budget'] = 'medium'
    elif 'high' in query.data:
        context.user_data['budget'] = 'high'
    else:
        context.user_data['budget'] = 'unknown'
    
    text = """
❓ <b>Питання 7 з 8</b>

Як вас звати?

<i>Просто напишіть своє ім'я у відповідь на це повідомлення.</i>
"""
    
    # Зберігаємо, що чекаємо на ім'я
    context.user_data['waiting_for_name'] = True
    
    await query.edit_message_text(text, parse_mode='HTML')

async def question_8(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Питання 8: Номер телефону"""
    
    # Зберігаємо ім'я
    context.user_data['first_name'] = update.message.text.strip()
    context.user_data['waiting_for_name'] = False
    
    text = f"""
❓ <b>Останнє питання (8 з 8)</b>

Дякую, <b>{context.user_data['first_name']}</b>!

Поділіться номером телефону, щоб отримати результат розрахунку.

<i>Натисніть кнопку нижче, щоб поділитися номером 👇</i>
"""
    
    from telegram import KeyboardButton, ReplyKeyboardMarkup
    
    keyboard = [
        [KeyboardButton("📱 Поділитися номером", request_contact=True)]
    ]
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
    
    # Зберігаємо в Google Sheets
    await save_to_sheets(context.user_data)
    
    # Відправляємо webhook в Make.com (для сповіщення)
    await send_to_make(context.user_data)
    
    # Відправляємо результат
    await send_result(update, context, segment, cost, time)
    
    # Відправляємо перший оффер
    await send_first_offer(update, context)

async def save_to_sheets(user_data):
    """Зберігає дані ліда в Google Sheets"""
    
    if SHEETS is None:
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
            user_data.get('budget', ''),
            user_data.get('segment', ''),
            user_data.get('cost_estimate', ''),
            user_data.get('time_estimate', ''),
            user_data.get('status', 'new')
        ]
        
        SHEETS.append_row(row)
        logger.info(f"✅ Лід збережено в Google Sheets: {user_data.get('first_name')}")
        
    except Exception as e:
        logger.error(f"❌ Помилка збереження в Google Sheets: {e}")

async def send_to_make(user_data):
    """Відправляє webhook в Make.com для тригеру сценаріїв"""
    
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
        logger.error(f"❌ Помилка відправки webhook в Make.com: {e}")

async def send_result(update: Update, context: ContextTypes.DEFAULT_TYPE, segment, cost, time):
    """Відправляє персоналізований результат"""
    
    from telegram import ReplyKeyboardRemove
    
    # Отримуємо персоналізоване повідомлення
    message_template = SEGMENT_MESSAGES.get(segment, SEGMENT_MESSAGES['B'])
    result_text = message_template.format(cost=cost, time=time)
    
    await update.message.reply_text(
        result_text,
        parse_mode='HTML',
        reply_markup=ReplyKeyboardRemove()
    )

async def send_first_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Відправляє перший оффер зі знижкою"""
    
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
    
    await update.message.reply_text(
        offer_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

async def book_consultation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка запису на консультацію"""
    
    query = update.callback_query
    await query.answer()
    
    user_data = context.user_data
    
    # Відправляємо сповіщення в Make.com (для дзвінка Стасу)
    if MAKE_WEBHOOK_URL:
        try:
            payload = {
                'event': 'consultation_request',
                'telegram_id': user_data.get('telegram_id'),
                'first_name': user_data.get('first_name'),
                'phone_number': user_data.get('phone_number'),
                'segment': user_data.get('segment')
            }
            requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=5)
            logger.info("✅ Сповіщення про запис відправлено в Make.com")
        except:
            pass
    
    text = """
✅ <b>Чудово! Запит прийнято.</b>

Наш адвокат зв'яжеться з вами <b>протягом 5-15 хвилин</b>, щоб узгодити зручний час консультації.

<i>Очікуйте дзвінок на номер:</i> <code>{phone}</code>

Якщо не зможемо дотелефонуватись, напишемо вам сюди в Telegram.

<b>Дякуємо за довіру!</b> 🙏
""".format(phone=user_data.get('phone_number'))
    
    await query.edit_message_text(text, parse_mode='HTML')
    
    # Оновлюємо статус в Google Sheets
    user_data['status'] = 'scheduled'
    # TODO: оновити в sheets (потрібна окрема функція)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробка текстових повідомлень (для Q7 - ім'я)"""
    
    if context.user_data.get('waiting_for_name'):
        await question_8(update, context)
    else:
        # Якщо користувач пише щось не до речі
        await update.message.reply_text(
            "Вибачте, не розумію 🤔\n\nНатисніть /start, щоб почати розрахунок."
        )

# =====================================================
# ГОЛОВНА ФУНКЦІЯ
# =====================================================

def main():
    """Запуск бота"""
    
    # Створюємо Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Реєструємо обробники
    application.add_handler(CommandHandler("start", start))
    
    # Квіз
    application.add_handler(CallbackQueryHandler(question_1, pattern='^start_quiz$'))
    application.add_handler(CallbackQueryHandler(question_2, pattern='^q1_'))
    application.add_handler(CallbackQueryHandler(question_3, pattern='^q2_'))
    application.add_handler(CallbackQueryHandler(question_4, pattern='^q3_'))
    application.add_handler(CallbackQueryHandler(question_5, pattern='^q4_'))
    application.add_handler(CallbackQueryHandler(question_6, pattern='^q5_'))
    application.add_handler(CallbackQueryHandler(question_7, pattern='^q6_'))
    
    # Запис на консультацію
    application.add_handler(CallbackQueryHandler(book_consultation, pattern='^book_consultation$'))
    
    # Обробка контакту (номер телефону)
    application.add_handler(MessageHandler(filters.CONTACT, process_contact))
    
    # Обробка текстових повідомлень
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Запускаємо бота
    logger.info("🚀 Бот запущено!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
