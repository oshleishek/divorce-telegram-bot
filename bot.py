"""
Telegram Bot v4.1 "SMART SCOOTER" (MVP)
Логіка: Квіз (4 питання) -> Хук -> Телефон -> Таблиця + Make + Лог всіх юзерів
"""

import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask
import threading
import requests  # Для Make.com

# =====================================================
# НАЛАШТУВАННЯ
# =====================================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
GOOGLE_SHEET_URL = os.environ.get('GOOGLE_SHEET_URL')
MAKE_WEBHOOK_URL = os.environ.get('MAKE_WEBHOOK_URL') # Додай цей URL в змінні оточення!

# =====================================================
# ТЕКСТИ (УКРАЇНСЬКА)
# =====================================================

TXT_WELCOME = """
👋 <b>Калькулятор розлучення</b>

Дайте відповідь на 4 прості питання, і я розрахую:
1. Чи можна розлучитися без суду?
2. Скільки це займе часу?
3. Вартість процедури.

<i>Це займе 30 секунд.</i>

Натисніть кнопку нижче ⬇️
"""

TXT_Q1 = "<b>Питання 1/4:</b>\n\nЧи є у вас спільні неповнолітні діти?"
TXT_Q2 = "<b>Питання 2/4:</b>\n\nЧи є згода чоловіка/дружини на розлучення?"
TXT_Q3 = "<b>Питання 3/4:</b>\n\nЧи є спільне майно, яке потрібно ділити?" # НОВЕ
TXT_Q4 = "<b>Питання 4/4:</b>\n\nДе ви знаходитесь територіально?"

TXT_HOOK = """
✅ <b>Розрахунок готовий!</b>

Виходячи з ваших відповідей:
🚀 <b>Прогноз:</b> Можливо вирішити за 2-3 місяці.
🌍 <b>Присутність:</b> Можна повністю дистанційно (без візитів до суду).

Щоб отримати <b>покроковий план дій</b> та точний кошторис витрат — залиште свій номер.

<i>Адвокат Анастасія зв'яжеться з вами протягом 15 хвилин.</i>
"""

TXT_FINAL = """
✅ <b>Дякую! Вашу заявку прийнято.</b>

Ми вже аналізуємо вашу ситуацію.
Очікуйте дзвінок з номера: <code>{phone}</code> найближчим часом.

Гарного дня!
"""

# =====================================================
# GOOGLE SHEETS & MAKE
# =====================================================

def init_google_sheets():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
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
        spreadsheet = client.open_by_url(GOOGLE_SHEET_URL)
        
        # Повертаємо два листи: Ліди та Всі Юзери
        # Переконайся, що в таблиці створені вкладки "Leads" та "All_Users"
        return spreadsheet.worksheet("Leads"), spreadsheet.worksheet("All_Users")
    except Exception as e:
        logger.error(f"❌ Sheets Error: {e}")
        return None, None

SHEET_LEADS, SHEET_USERS = init_google_sheets()

def send_to_make(data):
    """Відправка даних на Make.com"""
    if not MAKE_WEBHOOK_URL:
        return
    try:
        requests.post(MAKE_WEBHOOK_URL, json=data)
        logger.info("✅ Webhook sent to Make")
    except Exception as e:
        logger.error(f"❌ Make Error: {e}")

# =====================================================
# ЛОГІКА БОТА
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт: Логує юзера і показує кнопку"""
    user = update.effective_user
    context.user_data.clear()
    
    # 1. Логуємо ВСІХ, хто натиснув старт (Для аналітики воронки)
    if SHEET_USERS:
        try:
            SHEET_USERS.append_row([
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                str(user.id),
                f"@{user.username}" if user.username else "No Username",
                user.first_name,
                "Started"
            ])
        except Exception as e:
            logger.error(f"Log User Error: {e}")

    keyboard = [[InlineKeyboardButton("🚀 Розрахувати вартість", callback_data='start_quiz')]]
    await update.message.reply_text(TXT_WELCOME, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def quiz_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє натискання кнопок в квізі"""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Q1: Діти
    if data == 'start_quiz':
        keyboard = [
            [InlineKeyboardButton("👶 Так, є діти", callback_data='q1_yes')],
            [InlineKeyboardButton("❌ Ні, немає дітей", callback_data='q1_no')]
        ]
        await query.edit_message_text(TXT_Q1, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # Q2: Згода
    elif data.startswith('q1_'):
        context.user_data['children'] = "Є діти" if data == 'q1_yes' else "Немає дітей"
        
        keyboard = [
            [InlineKeyboardButton("✅ Так, є згода", callback_data='q2_yes')],
            [InlineKeyboardButton("⛔️ Ні, проти / не знаю", callback_data='q2_no')]
        ]
        await query.edit_message_text(TXT_Q2, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # Q3: Майно (НОВЕ)
    elif data.startswith('q2_'):
        context.user_data['consent'] = "Є згода" if data == 'q2_yes' else "Немає згоди"
        
        keyboard = [
            [InlineKeyboardButton("🏠 Так, ділимо майно", callback_data='q3_yes')],
            [InlineKeyboardButton("❌ Ні, майна немає/домовились", callback_data='q3_no')]
        ]
        await query.edit_message_text(TXT_Q3, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # Q4: Місце
    elif data.startswith('q3_'):
        context.user_data['property'] = "Є майно" if data == 'q3_yes' else "Немає майна"
        
        keyboard = [
            [InlineKeyboardButton("🇺🇦 В Україні", callback_data='q4_ukr')],
            [InlineKeyboardButton("🌍 За кордоном", callback_data='q4_world')]
        ]
        await query.edit_message_text(TXT_Q4, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # Фінал: Хук + Запит телефону
    elif data.startswith('q4_'):
        context.user_data['location'] = "Україна" if data == 'q4_ukr' else "За кордоном"
        
        await query.delete_message()

        btn_phone = [[KeyboardButton("📱 Отримати план (Поділитися номером)", request_contact=True)]]
        markup = ReplyKeyboardMarkup(btn_phone, one_time_keyboard=True, resize_keyboard=True)

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=TXT_HOOK,
            parse_mode='HTML',
            reply_markup=markup
        )

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отримує контакт, зберігає в таблицю і шле в Make"""
    contact = update.message.contact
    user = update.effective_user
    
    phone = contact.phone_number
    first_name = contact.first_name or user.first_name or "Клієнт"
    
    # Збираємо всі дані
    lead_data = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "telegram_id": str(user.id),
        "username": f"@{user.username}" if user.username else "",
        "name": first_name,
        "phone": phone,
        "children": context.user_data.get('children', '-'),
        "consent": context.user_data.get('consent', '-'),
        "property": context.user_data.get('property', '-'), # НОВЕ
        "location": context.user_data.get('location', '-')
    }

    # 1. Збереження в Google Sheets (Leads)
    if SHEET_LEADS:
        try:
            SHEET_LEADS.append_row(list(lead_data.values()) + ["New Lead"])
            logger.info(f"✅ Лід збережено в таблицю: {phone}")
        except Exception as e:
            logger.error(f"❌ Sheets Error: {e}")

    # 2. Відправка в Make (для миттєвого повідомлення)
    if MAKE_WEBHOOK_URL:
        threading.Thread(target=send_to_make, args=(lead_data,)).start()

    # Фінальне повідомлення
    await update.message.reply_text(
        TXT_FINAL.format(phone=phone),
        parse_mode='HTML',
        reply_markup=ReplyKeyboardRemove()
    )

# =====================================================
# SERVER & MAIN
# =====================================================

app = Flask(__name__)
@app.route('/')
def index(): return "Bot v4.1 is running", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(quiz_handler))
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))

    application.run_polling()

if __name__ == '__main__':
    main()
