import telebot
from telebot import types
import threading
import pandas as pd
import os
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from mt5_client import connect_mt5, disconnect_mt5
from analyzer import run_analysis 

# Botni ulash
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Pastki menyu tugmalarini yaratish
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_status = types.KeyboardButton("📊 Status")
    btn_analyze = types.KeyboardButton("📈 Tahlil qilish")
    btn_stats = types.KeyboardButton("📋 Statistika") # Yangi tugma qo'shildi
    markup.add(btn_status, btn_analyze, btn_stats)
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if str(message.chat.id) != str(TELEGRAM_CHAT_ID):
        return
    
    bot.reply_to(
        message, 
        "🤖 <b>GOLD TRADING PRO</b> ishga tushdi!\n\nQuyidagi tugmalardan birini tanlang:", 
        parse_mode="HTML", 
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(commands=['status'])
@bot.message_handler(func=lambda message: message.text == "📊 Status")
def handle_status(message):
    if str(message.chat.id) != str(TELEGRAM_CHAT_ID):
        return
    
    text = (
        "🤖 <b>GOLD TRADING PRO - STATUS</b>\n\n"
        "✅ Tizim faol va bozor kuzatilmoqda.\n"
        "⏰ Tahlil avtomatik ravishda amalga oshirilmoqda."
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=['analyze'])
@bot.message_handler(func=lambda message: message.text == "📈 Tahlil qilish")
def handle_analyze(message):
    if str(message.chat.id) != str(TELEGRAM_CHAT_ID):
        return
    
    bot.reply_to(message, "⏳ XAUUSD holati zudlik bilan tahlil qilinmoqda, kuting...")
    
    try:
        if connect_mt5():
            run_analysis() 
            bot.send_message(
                message.chat.id, 
                "✅ Tahlil yakunlandi! Agar tayyor setup bo'lsa, hozir signal keladi (yo'qsa pinhona jurnallandi)."
            )
            disconnect_mt5()
        else:
            bot.reply_to(message, "❌ MT5 terminaliga ulanib bo'lmadi. Terminal ochiqligini tekshiring.")
    except Exception as e:
        bot.reply_to(message, f"❌ Xatolik yuz berdi: {e}")

# YANGI QISM: Statistika hisoblash
@bot.message_handler(commands=['stats'])
@bot.message_handler(func=lambda message: message.text == "📋 Statistika")
def handle_stats(message):
    if str(message.chat.id) != str(TELEGRAM_CHAT_ID):
        return
    
    csv_path = "logs/signal_journal.csv"
    
    if not os.path.exists(csv_path):
        bot.reply_to(message, "❌ Hali signallar jurnali (signal_journal.csv) yaratilmagan. Natijalar yo'q.")
        return
        
    try:
        # Faylni pandas yordamida o'qiymiz
        df = pd.read_csv(csv_path)
        
        if 'outcome' not in df.columns:
            bot.reply_to(message, "⚠️ Jurnalda 'outcome' ustuni topilmadi. Hali savdo natijalari to'liq yozilmagan bo'lishi mumkin.")
            return
            
        # Natijalarni hisoblash
        total = len(df)
        wins = len(df[df['outcome'] == 'WIN'])
        losses = len(df[df['outcome'] == 'LOSS'])
        
        # WinRate (Aniqlik foizi) hisoblash
        winrate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        
        # Matnni chiroyli qilib tayyorlash
        text = (
            "📋 <b>GOLD TRADING PRO - STATISTIKA</b>\n\n"
            f"🔢 <b>Jami yozib olingan signallar:</b> {total} ta\n"
            f"✅ <b>WIN (Foyda):</b> {wins} ta\n"
            f"❌ <b>LOSS (Zarar):</b> {losses} ta\n"
            f"🎯 <b>WinRate (Aniqlik):</b> {winrate:.1f}%\n"
            "\n<i>Eslatma: Bu natijalar 'outcome_tracker.py' ishlaganda avtomatik yangilanib boradi. ML (XGBoost) modelini yoqish uchun kamida 10 ta WIN va 10 ta LOSS yig'ilishi kerak!</i>"
        )
        
        bot.reply_to(message, text, parse_mode="HTML")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Statistika o'qishda xatolik yuz berdi: {e}")

def start_telegram_listener():
    thread = threading.Thread(target=bot.infinity_polling, daemon=True)
    thread.start()
    print("✅ Telegram Interaktiv Bot (Tugmalar va Statistika) ishga tushdi!")

def send_telegram_alert(result):
    """Faqat matnli xabar yuborish (agar rasm chizishda xato bo'lsa)"""
    from config import ENABLE_TELEGRAM_NOTIFICATIONS
    if not ENABLE_TELEGRAM_NOTIFICATIONS:
        return
    
    text = f"🚨 <b>{result['final_signal']} SIGNAL DETECTED</b>\n\n"
    text += f"📊 Symbol: {result['symbol']}\n"
    text += f"💰 Entry: {result['suggested_entry']}\n"
    text += f"🛑 SL: {result['suggested_sl']}\n"
    text += f"🎯 TP: {result['suggested_tp']}"
    
    try:
        bot.send_message(TELEGRAM_CHAT_ID, text, parse_mode="HTML")
    except Exception as e:
        print(f"Telegram xabar yuborishda xato: {e}")

def send_telegram_photo(photo_path, caption):
    """Rasm va matnni birga yuborish"""
    from config import ENABLE_TELEGRAM_NOTIFICATIONS
    if not ENABLE_TELEGRAM_NOTIFICATIONS:
        return
        
    try:
        if os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo:
                bot.send_photo(TELEGRAM_CHAT_ID, photo, caption=caption, parse_mode="HTML")
        else:
            print(f"Rasm topilmadi: {photo_path}")
    except Exception as e:
        print(f"Telegram rasm yuborishda xato: {e}")