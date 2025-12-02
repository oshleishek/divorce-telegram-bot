"""
Telegram Bot v4.0 "SCOOTER" (MVP)
Логіка: Лінійна стріла (Квіз -> Хук -> Телефон -> Таблиця)
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

# =====================================================
# НАЛАШТУВАННЯ
# =====================================================

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
GOOGLE_SHEET_URL = os.environ.get('GOOGLE_SHEET_URL')

# =====================================================
# ТЕКСТИ (УКРАЇНСЬКА)
# =====================================================

TXT_WELCOME = """
👋 <b>Калькулятор розлучення</b>

Дайте відповідь на 3 прості питання, і я розрахую:
1. Чи можна розлучитися без суду?
2. Скільки це займе часу?
3. Чи потрібна ваша присутність?

<i>Це займе 30 секунд.</i>

Натисніть кнопку нижче ⬇️
"""

TXT_Q1 = "<b>Питання 1/3:</b>\n\nЧи є у вас спільні неповнолітні діти?"
TXT_Q2 = "<b>Питання 2/3:</b>\n\nЧи є згода чоловіка/дружини на розлучення?"
TXT_Q3 = "<b>Питання 3/3:</b>\n\nДе ви знаходитесь територіально?"

TXT_HOOK = """
✅ <b>Розрахунок готовий!</b>

Виходячи з ваших відповідей:
🚀 <b>Прогноз:</b> Можливо вирішити за 2-3 місяці.
🌍 <b>Присутність:</b> Можна повністю дистанційно (без візитів до суду).

Щоб отримати <b>покроковий план дій</b> та точний кошторис витрат — залиште свій номер.

<i>Наш адвокат зв'яжеться з вами протягом 15 хвилин.</i>
"""

TXT_FINAL = """
✅ <b>Дякую! Вашу заявку прийнято.</b>

Ми вже аналізуємо вашу ситуацію.
Очікуйте дзвінок з номера: <code>{phone}</code> найближчим часом.

Гарного дня!
"""

# =====================================================
# GOOGLE SHEETS
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
        return spreadsheet.worksheet("Leads")
    except Exception as e:
        logger.error(f"❌ Sheets Error: {e}")
        return None

SHEET = init_google_sheets()

# =====================================================
# ЛОГІКА БОТА
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт: Показує кнопку початку"""
    context.user_data.clear()
    
    keyboard = [[InlineKeyboardButton("🚀 Розрахувати строки та вартість", callback_data='start_quiz')]]
    await update.message.reply_text(TXT_WELCOME, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def quiz_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє натискання кнопок в квізі"""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Питання 1: Діти
    if data == 'start_quiz':
        keyboard = [
            [InlineKeyboardButton("👶 Так, є діти", callback_data='q1_yes')],
            [InlineKeyboardButton("❌ Ні, немає дітей", callback_data='q1_no')]
        ]
        await query.edit_message_text(TXT_Q1, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # Питання 2: Згода
    elif data.startswith('q1_'):
        context.user_data['children'] = "Є діти" if data == 'q1_yes' else "Немає дітей"
        
        keyboard = [
            [InlineKeyboardButton("✅ Так, є згода", callback_data='q2_yes')],
            [InlineKeyboardButton("⛔️ Ні, проти / не знаю", callback_data='q2_no')]
        ]
        await query.edit_message_text(TXT_Q2, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # Питання 3: Місце
    elif data.startswith('q2_'):
        context.user_data['consent'] = "Є згода" if data == 'q2_yes' else "Немає згоди"
        
        keyboard = [
            [InlineKeyboardButton("🇺🇦 В Україні", callback_data='q3_ukr')],
            [InlineKeyboardButton("🌍 За кордоном", callback_data='q3_world')]
        ]
        await query.edit_message_text(TXT_Q3, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

    # Фінал: Хук + Запит телефону
    elif data.startswith('q3_'):
        context.user_data['location'] = "Україна" if data == 'q3_ukr' else "За кордоном"
        
        # Видаляємо старе повідомлення з кнопками, щоб було красиво
        await query.delete_message()

        # Кнопка телефону (Reply Keyboard)
        btn_phone = [[KeyboardButton("📱 Отримати план дій (Поділитися номером)", request_contact=True)]]
        markup = ReplyKeyboardMarkup(btn_phone, one_time_keyboard=True, resize_keyboard=True)

        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=TXT_HOOK,
            parse_mode='HTML',
            reply_markup=markup
        )

async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отримує контакт і зберігає в таблицю"""
    contact = update.message.contact
    user = update.effective_user
    
    phone = contact.phone_number
    first_name = contact.first_name or user.first_name or "Клієнт"
    
    # Дані з квізу
    children = context.user_data.get('children', '-')
    consent = context.user_data.get('consent', '-')
    location = context.user_data.get('location', '-')

    # Збереження в Google Sheets
    if SHEET:
        try:
            SHEET.append_row([
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                str(user.id),
                f"@{user.username}" if user.username else "",
                first_name,
                phone,
                children,
                consent,
                location,
                "New Lead"
            ])
            logger.info(f"✅ Лід збережено: {phone}")
        except Exception as e:
            logger.error(f"❌ Помилка запису в таблицю: {e}")

    # Фінальне повідомлення (прибираємо кнопку телефону)
    await update.message.reply_text(
        TXT_FINAL.format(phone=phone),
        parse_mode='HTML',
        reply_markup=ReplyKeyboardRemove()
    )

    # Оповіщення тобі (опціонально, розкоментуй і встав свій ID, якщо хочеш бачити ліди в ПП)
    # await context.bot.send_message(chat_id=YOUR_ADMIN_ID, text=f"🔥 НОВИЙ ЛІД!\n{phone}\n{children}, {consent}")

# =====================================================
# SERVER & MAIN
# =====================================================

app = Flask(__name__)
@app.route('/')
def index(): return "Bot is running", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(quiz_handler)) # Один хендлер на всі кнопки
    application.add_handler(MessageHandler(filters.CONTACT, contact_handler))

    application.run_polling()

if __name__ == '__main__':
    main()
