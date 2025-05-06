import json
import os
import requests
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from fetch_cases import fetch_cs2_cases
import asyncio

# .env dosyasını yükle
load_dotenv()

ALARM_FILE = "data/alarms.json"
CASE_LIST_FILE = "data/cases.json"

price_history = {}

# Kasa listesine verileri çek
def load_case_data():
    try:
        cases = fetch_cs2_cases()
        with open(CASE_LIST_FILE, "w", encoding="utf-8") as f:
            json.dump(cases, f, ensure_ascii=False, indent=2)
        return cases
    except Exception as e:
        print(f"Hata oluştu: {e}")
        if os.path.exists(CASE_LIST_FILE):
            with open(CASE_LIST_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

cases = load_case_data()

# Fiyat grafiği oluştur
def fiyat_grafigi(gecmis_fiyatlar, kasa_adi):
    plt.figure()
    plt.plot(gecmis_fiyatlar, marker='o')
    plt.title(f"{kasa_adi} Fiyat Grafiği")
    plt.xlabel("Zaman")
    plt.ylabel("Fiyat ($)")
    plt.grid(True)
    os.makedirs("grafikler", exist_ok=True)
    path = f"grafikler/{kasa_adi.replace(' ', '_')}.png"
    plt.savefig(path)
    plt.close()
    return path

# Alarm verilerini yükle
def load_alarms():
    if not os.path.exists(ALARM_FILE):
        return {}
    with open(ALARM_FILE, 'r') as f:
        return json.load(f)

# Alarm verilerini kaydet
def save_alarms(data):
    with open(ALARM_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# Steam fiyatını al
def get_steam_price(item_name):
    url = f"https://steamcommunity.com/market/priceoverview/?currency=1&appid=730&market_hash_name={item_name.replace(' ', '%20')}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data.get("success") and data.get("lowest_price"):
            price_str = data["lowest_price"].replace("$", "").replace(",", "")
            return float(price_str)
    return None

# /start komutu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_cases = sorted(cases)
    keyboard = [[InlineKeyboardButton(case, callback_data=case)] for case in sorted_cases[:30]]  # İlk 30 kasa
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("CS2 Kasaları:", reply_markup=reply_markup)

# Seçilen kasa detayları
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    case_name = query.data
    price = get_steam_price(case_name)
    if case_name not in price_history:
        price_history[case_name] = []
    price_history[case_name].append(price)

    grafik_path = fiyat_grafigi(price_history[case_name], case_name)

    # Alarm kurma tuşu ekle
    keyboard = [[InlineKeyboardButton("Alarm Kur", callback_data=f"alarm|{case_name}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_photo(chat_id=query.message.chat_id, photo=open(grafik_path, 'rb'))
    await query.edit_message_text(text=f"{case_name} fiyatı: ${price:.2f}", reply_markup=reply_markup)

# Alarm kurma
async def handle_alarm_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, case_name = query.data.split("|")
    context.user_data['selected_case'] = case_name
    await query.message.reply_text(f"{case_name} için kaç dolara düştüğünde uyarı alacaksın?")

# Alarm fiyatı belirleme
async def set_alarm_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    case_name = context.user_data.get('selected_case')
    if case_name:
        try:
            price = float(update.message.text)
            alarms = load_alarms()
            user_id = str(update.message.from_user.id)
            if user_id not in alarms:
                alarms[user_id] = {}
            alarms[user_id][case_name] = price
            save_alarms(alarms)
            await update.message.reply_text(f"{case_name} için ${price:.2f} fiyatına alarm kuruldu.")
        except ValueError:
            await update.message.reply_text("Lütfen geçerli bir fiyat gir.")

# Alarm kontrolü
async def check_alarms(application):
    while True:
        alarms = load_alarms()
        for user_id, user_alarms in alarms.items():
            for case_name, target_price in user_alarms.items():
                price = get_steam_price(case_name)
                if price is not None and price <= target_price:
                    await application.bot.send_message(chat_id=user_id, text=f"{case_name} ${price:.2f} fiyatına düştü!")
        await asyncio.sleep(600)  # 10 dakika bekle

# Uygulama başlatma
if __name__ == "__main__":
    # .env dosyasından token'ı al
    bot_token = os.getenv("BOT_TOKEN")
    if bot_token is None:
        raise ValueError("BOT_TOKEN çevresel değişkeni .env dosyasından alınamadı.")

    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(CallbackQueryHandler(handle_alarm_setup, pattern="^alarm\\|"))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), set_alarm_price))
    app.job_queue.run_once(lambda c: asyncio.create_task(check_alarms(app)), when=0)
    app.run_polling()
