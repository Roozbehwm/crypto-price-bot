# bot.py
import logging
import json
import os
import time
import threading
import asyncio
from flask import Flask

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
import requests
import schedule

# --- تنظیمات ---
import os
TOKEN = os.environ.get('TOKEN')
if not TOKEN:
    raise ValueError("TOKEN not found in environment variables!")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ایموجی‌ها ---
TICK = "Checkmark"
CROSS = "Cross"
COIN = "Coin"
EDIT = "Pencil"
ALERT = "Bell"
DELETE = "Trash"
BACK = "Back"
SEARCH = "Magnifying Glass"
CANCEL = "Cancel"

# --- ارزهای معروف ---
POPULAR_COINS = {
    'BTC': ('bitcoin', 'Bitcoin'),
    'ETH': ('ethereum', 'Ethereum'),
    'BNB': ('binancecoin', 'BNB'),
    'SOL': ('solana', 'Solana'),
    'XRP': ('ripple', 'XRP'),
    'TON': ('the-open-network', 'Toncoin'),
    'FET': ('fetch-ai', 'Fetch.AI'),
    'SUI': ('sui', 'Sui'),
    'CAKE': ('pancakeswap', 'PancakeSwap'),
    'VET': ('vechain', 'VeChain'),
    'AAVE': ('aave', 'Aave'),
    'TAO': ('bittensor', 'Bittensor'),
    'LINK': ('chainlink', 'Chainlink'),
    'GALA': ('gala', 'Gala')
}

# --- همه ارزها ---
ALL_COINS = {
    'BTC': 'bitcoin', 'ETH': 'ethereum', 'USDT': 'tether', 'BNB': 'binancecoin',
    'SOL': 'solana', 'USDC': 'usd-coin', 'XRP': 'ripple', 'TON': 'the-open-network',
    'DOGE': 'dogecoin', 'ADA': 'cardano', 'TRX': 'tron', 'AVAX': 'avalanche-2',
    'SHIB': 'shiba-inu', 'WBTC': 'wrapped-bitcoin', 'LINK': 'chainlink', 'DOT': 'polkadot',
    'BCH': 'bitcoin-cash', 'NEAR': 'near', 'LTC': 'litecoin', 'MATIC': 'matic-network',
    'UNI': 'uniswap', 'ICP': 'internet-computer', 'LEO': 'unus-sed-leo', 'PEPE': 'pepe',
    'KAS': 'kaspa', 'ETC': 'ethereum-classic', 'XMR': 'monero', 'ATOM': 'cosmos',
    'STX': 'blockstack', 'OKB': 'okb', 'FDUSD': 'first-digital-usd', 'HBAR': 'hedera-hashgraph',
    'FIL': 'filecoin', 'INJ': 'injective-protocol', 'ARB': 'arbitrum', 'OP': 'optimism',
    'CRO': 'crypto-com-chain', 'IMX': 'immutable-x', 'VET': 'vechain', 'MKR': 'maker',
    'GRT': 'the-graph', 'LDO': 'lido-dao', 'AR': 'arweave', 'FLOKI': 'floki',
    'THETA': 'theta-token', 'RUNE': 'thorchain', 'JASMY': 'jasmycoin', 'JUP': 'jupiter-ag',
    'FET': 'fetch-ai', 'SUI': 'sui', 'BONK': 'bonk', 'WIF': 'dogwifcoin',
    'CAKE': 'pancakeswap', 'TAO': 'bittensor', 'AAVE': 'aave', 'BEAM': 'beam',
    'ONDO': 'ondo-finance', 'WLD': 'worldcoin', 'FTM': 'fantom', 'HNT': 'helium',
    'SEI': 'sei-network', 'BGB': 'bitget-token', 'PYTH': 'pyth-network', 'BRETT': 'brett',
    'CORE': 'core-dao', 'ALGO': 'algorand', 'FLOW': 'flow', 'EOS': 'eos',
    'XTZ': 'tezos', 'KSM': 'kusama', 'MIOTA': 'iota', 'FTT': 'ftx-token',
    'ZEC': 'zcash', 'DASH': 'dash', 'WAVES': 'waves', 'COMP': 'compound-governance-token',
    'ENJ': 'enjincoin', 'CHZ': 'chiliz', 'BAT': 'basic-attention-token', 'MANA': 'decentraland',
    'SAND': 'the-sandbox', 'GALA': 'gala', 'AXS': 'axie-infinity', 'CRV': 'curve-dao-token',
    '1INCH': '1inch', 'LRC': 'loopring', 'CELO': 'celo', 'KAVA': 'kava',
    'ROSE': 'oasis-network', 'KDA': 'kadena', 'XDC': 'xinfin-network', 'ONE': 'harmony',
    'IOST': 'iostoken', 'WAXP': 'wax', 'ICX': 'icon', 'ONT': 'ontology',
    'ZIL': 'zilliqa', 'QTUM': 'qtum', 'BTG': 'bitcoin-gold', 'RVN': 'ravencoin',
    'SC': 'siacoin', 'DGB': 'digibyte', 'XEM': 'nem', 'ZEN': 'horizen', 'SYS': 'syscoin'
}

MAX_COINS = 20
TIME_OPTIONS = [
    (8 * 60, "۸ ساعت"),
    (12 * 60, "۱۲ ساعت"),
    (24 * 60, "۲۴ ساعت"),
    (36 * 60, "۳۶ ساعت"),
    (7 * 24 * 60, "هفته‌ای یکبار")
]

# --- ذخیره دائمی ---
DATA_FILE = 'user_data.json'
user_data = {}

def load_data():
    global user_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
            for uid in user_data:
                for item in user_data[uid]:
                    if 'last_sent' not in item or item['last_sent'] == 0:
                        item['last_sent'] = time.time() - 900
        except Exception as e:
            logger.error(f"Load error: {e}")
            user_data = {}
    else:
        user_data = {}

def save_data():
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")

load_data()

# --- Flask برای /ping ---
flask_app = Flask(__name__)

@flask_app.route('/ping')
def ping():
    return "Bot is alive!", 200

# --- قیمت ---
def get_price(cg_id):
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
        response = requests.get(url, timeout=10)
        return response.json().get(cg_id, {}).get('usd')
    except Exception as e:
        logger.error(f"Price error: {e}")
        return None

# --- چک قیمت ---
def check_prices():
    async def send_message(user_id, text):
        try:
            await app.bot.send_message(chat_id=user_id, text=text, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Send error to {user_id}: {e}")

    async def run_checks():
        tasks = []
        current_time = time.time()

        for user_id, settings in list(user_data.items()):
            for item in settings[:]:
                price = get_price(item['cg_id'])
                if price is None:
                    continue

                last_sent = item.get('last_sent', 0)
                period_seconds = item['period'] * 60
                time_passed = current_time - last_sent >= period_seconds

                if 'alert' not in item:
                    if time_passed:
                        message = (
                            f"{COIN} قیمت لحظه‌ای\n\n"
                            f"**نام ارز:** `{item['symbol']}`\n"
                            f"**قیمت:** `${price:,.2f}`"
                        )
                        tasks.append(send_message(user_id, message))
                        item['last_sent'] = current_time

                else:
                    op = item['alert']['op']
                    target = item['alert']['price']
                    condition_met = (op == '>=' and price >= target) or (op == '<=' and price <= target)

                    if condition_met and time_passed:
                        op_text = "بیشتر یا مساوی با" if op == '>=' else "کمتر یا مساوی با"
                        message = (
                            f"{ALERT} هشدار قیمت!\n\n"
                            f"**نام ارز:** `{item['symbol']}`\n"
                            f"**قیمت لحظه‌ای:** `${price:,.2f}`\n\n"
                            f"**شرط فعال شده:** {op_text} `${target:,.2f}`"
                        )
                        tasks.append(send_message(user_id, message))
                        item['last_sent'] = current_time

        if tasks:
            await asyncio.gather(*tasks)

    asyncio.run(run_checks())

# --- scheduler ---
def run_scheduler():
    schedule.every(1).minutes.do(check_prices)
    while True:
        schedule.run_pending()
        time.sleep(1)

# --- منو ---
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{COIN} اضافه کردن ارز", callback_data='add_coin')],
        [InlineKeyboardButton(f"{SEARCH} لیست ارزها", callback_data='list_coins')],
        [InlineKeyboardButton("راهنما کامل", callback_data='help')]
    ])

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data:
        user_data[user_id] = []
        save_data()
    context.user_data.clear()

    await update.message.reply_text(
        f"**به ربات استعلام قیمت ارز خوش اومدی!**\n\n\n"
        f"{COIN} ارزهای معروف رو با **دکمه** انتخاب کن\n\n"
        f"{SEARCH} یا **نام/نماد** رو تایپ کن\n\n"
        f"{TICK} بعد از اضافه کردن، **قیمت فوری** میاد\n\n"
        f"هر **۱۵ دقیقه** قیمت میاد (قابل تغییر)\n\n"
        f"{ALERT} می‌تونی **هشدار قیمت** بذاری\n\n"
        f"حداکثر **{MAX_COINS} ارز** می‌تونی داشته باشی\n\n\n"
        f"همه چیز با دکمه — راحت و بدون خطا!",
        reply_markup=main_menu(),
        parse_mode='Markdown'
    )

# --- /menu ---
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(f"{BACK} منوی اصلی:", reply_markup=main_menu())

# --- اضافه کردن ---
async def add_coin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    keyboard = []
    row = []
    for symbol, (_, name) in POPULAR_COINS.items():
        row.append(InlineKeyboardButton(f"{symbol} {name}", callback_data=f"select_pop_{symbol}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton(f"{SEARCH} جستجوی پیشرفته", callback_data='search_coin')])
    keyboard.append([InlineKeyboardButton(f"{BACK} برگشت", callback_data='back')])
    await query.edit_message_text("ارز رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))

async def select_popular(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    symbol = query.data.split('_')[2]
    cg_id, _ = POPULAR_COINS[symbol]
    await add_coin_logic(user_id, symbol, cg_id, query)
    context.user_data.clear()

async def search_coin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['state'] = 'search'
    keyboard = [[InlineKeyboardButton(f"{CANCEL} لغو", callback_data='cancel')]]
    await query.edit_message_text(
        f"{SEARCH} نام یا نماد ارز رو بنویس (مثلاً `BTC` یا `solana`):\n\n"
        f"یا دکمه زیر رو بزن تا لغو کنی:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def search_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    query = update.message.text.strip().lower()
    results = []
    for symbol, cg_id in ALL_COINS.items():
        if query in symbol.lower() or query in cg_id.lower():
            results.append((symbol, cg_id))
        if len(results) >= 10:
            break
    if not results:
        await update.message.reply_text(f"{CROSS} ارزی پیدا نشد! دوباره امتحان کن.", reply_markup=main_menu())
        context.user_data.clear()
        return
    keyboard = []
    for symbol, cg_id in results:
        keyboard.append([InlineKeyboardButton(f"{symbol}", callback_data=f"select_search|{cg_id}|{symbol}")])
    keyboard.append([InlineKeyboardButton(f"{CANCEL} لغو", callback_data='cancel')])
    await update.message.reply_text(f"نتایج برای `{query}`:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    context.user_data['state'] = 'awaiting_selection'

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(f"{CANCEL} عملیات لغو شد.", reply_markup=main_menu())

async def select_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split('|')
    if len(parts) != 3:
        await query.answer("خطا در پردازش", show_alert=True)
        return
    _, cg_id, symbol = parts
    await add_coin_logic(user_id, symbol, cg_id, query)
    context.user_data.clear()

async def add_coin_logic(user_id, symbol, cg_id, query_or_msg):
    if user_id not in user_data:
        user_data[user_id] = []

    if any(c['cg_id'] == cg_id for c in user_data[user_id]):
        price = get_price(cg_id)
        if price:
            await app.bot.send_message(
                chat_id=user_id,
                text=f"{COIN} قیمت لحظه‌ای\n\n**نام ارز:** `{symbol}`\n**قیمت:** `${price:,.2f}`",
                parse_mode='Markdown'
            )
        else:
            await app.bot.send_message(chat_id=user_id, text=f"{CROSS} قیمت **{symbol}** موقتاً در دسترس نیست.")
        if hasattr(query_or_msg, 'edit_message_text'):
            await query_or_msg.edit_message_text(f"{TICK} **{symbol}** قبلاً اضافه شده!")
        await app.bot.send_message(chat_id=user_id, text=f"{BACK} منوی اصلی:", reply_markup=main_menu())
        return

    if len(user_data[user_id]) >= MAX_COINS:
        if hasattr(query_or_msg, 'edit_message_text'):
            await query_or_msg.edit_message_text(
                f"{CROSS} **حداکثر {MAX_COINS} ارز می‌تونی داشته باشی!**\n"
                f"اول یکی رو با {DELETE} پاک کن، بعد اضافه کن.",
                reply_markup=main_menu()
            )
        else:
            await query_or_msg.reply_text(
                f"{CROSS} **حداکثر {MAX_COINS} ارز!**\nاول یکی رو پاک کن.",
                reply_markup=main_menu()
            )
        return

    user_data[user_id].append({
        'symbol': symbol,
        'cg_id': cg_id,
        'period': 15,
        'last_sent': time.time()
    })
    save_data()

    confirm_msg = f"{TICK} **{symbol}** با موفقیت اضافه شد!\nهر **۱۵ دقیقه** قیمت برات میاد.\n{EDIT} می‌تونی زمان یا {ALERT} هشدار بذاری."
    if hasattr(query_or_msg, 'edit_message_text'):
        await query_or_msg.edit_message_text(confirm_msg, parse_mode='Markdown')
    else:
        await query_or_msg.reply_text(confirm_msg, parse_mode='Markdown')

    price = get_price(cg_id)
    if price:
        await app.bot.send_message(
            chat_id=user_id,
            text=f"{COIN} قیمت لحظه‌ای\n\n**نام ارز:** `{symbol}`\n**قیمت:** `${price:,.2f}`",
            parse_mode='Markdown'
        )

    await app.bot.send_message(chat_id=user_id, text=f"{BACK} منوی اصلی:", reply_markup=main_menu())

# --- لیست ارزها ---
async def list_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    context.user_data.clear()
    if user_id not in user_data or not user_data[user_id]:
        await query.edit_message_text(f"{CROSS} هیچ ارزی نداری! از منو اضافه کن.", reply_markup=main_menu())
        return
    keyboard = []
    for item in user_data[user_id]:
        symbol = item['symbol']
        cg_id = item['cg_id']
        mins = item['period']
        time_text = next((t[1] for t in TIME_OPTIONS if t[0] == mins), f"هر {mins} دقیقه")
        status = time_text
        if 'alert' in item:
            op_text = "بیشتر یا مساوی با" if item['alert']['op'] == '>=' else "کمتر یا مساوی با"
            status += f" | هشدار: {op_text} ${item['alert']['price']:,.2f}"
        keyboard.append([
            InlineKeyboardButton(f"{EDIT} {symbol} - {status}", callback_data=f"edit_{cg_id}"),
            InlineKeyboardButton(f"{DELETE}", callback_data=f"remove_{cg_id}")
        ])
    keyboard.append([InlineKeyboardButton(f"{BACK} برگشت", callback_data='back')])
    await query.edit_message_text(f"{SEARCH} ارزهایت ({len(user_data[user_id])}/{MAX_COINS}):", reply_markup=InlineKeyboardMarkup(keyboard))

# --- ویرایش ---
async def edit_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cg_id = query.data.split('_')[1]
    item = next((i for i in user_data.get(user_id, []) if i['cg_id'] == cg_id), None)
    if not item:
        await query.edit_message_text(f"{CROSS} خطا: ارز پیدا نشد!", reply_markup=main_menu())
        return
    symbol = item['symbol']
    keyboard = [
        [InlineKeyboardButton(f"{EDIT} تغییر زمان", callback_data=f"time_{cg_id}")],
        [InlineKeyboardButton(f"{ALERT} تنظیم هشدار", callback_data=f"alert_{cg_id}")],
        [InlineKeyboardButton(f"{CROSS} حذف هشدار", callback_data=f"clearalert_{cg_id}")],
        [InlineKeyboardButton(f"{BACK} برگشت", callback_data='list_coins')]
    ]
    await query.edit_message_text(f"{EDIT} ویرایش `{symbol}`:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- تنظیم زمان ---
async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cg_id = query.data.split('_')[1]
    item = next((i for i in user_data.get(query.from_user.id, []) if i['cg_id'] == cg_id), None)
    symbol = item['symbol'] if item else "؟"
    keyboard = []
    for mins, label in TIME_OPTIONS:
        keyboard.append([InlineKeyboardButton(label, callback_data=f"settime_{cg_id}_{mins}")])
    keyboard.append([InlineKeyboardButton(f"{BACK} برگشت", callback_data=f"edit_{cg_id}")])
    await query.edit_message_text(f"{EDIT} زمان `{symbol}`:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- ذخیره زمان ---
async def save_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    _, cg_id, mins = query.data.split('_')
    mins = int(mins)
    for item in user_data[user_id]:
        if item['cg_id'] == cg_id:
            item['period'] = mins
            item['last_sent'] = time.time()
            break
    save_data()
    time_label = next((t[1] for t in TIME_OPTIONS if t[0] == mins), f"هر {mins} دقیقه")
    await query.edit_message_text(f"{TICK} زمان `{item['symbol']}` به **{time_label}** تغییر کرد.", reply_markup=main_menu(), parse_mode='Markdown')

# --- تنظیم هشدار ---
async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cg_id = query.data.split('_')[1]
    item = next((i for i in user_data.get(query.from_user.id, []) if i['cg_id'] == cg_id), None)
    symbol = item['symbol'] if item else "؟"
    keyboard = [
        [InlineKeyboardButton("بیشتر از (≥)", callback_data=f"alertop_{cg_id}_>=")],
        [InlineKeyboardButton("کمتر از (≤)", callback_data=f"alertop_{cg_id}_<=")],
        [InlineKeyboardButton(f"{CANCEL} لغو", callback_data='cancel')]
    ]
    await query.edit_message_text(f"{ALERT} هشدار `{symbol}`:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# --- انتخاب عملگر ---
async def select_alert_op(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    _, cg_id, op = query.data.split('_')
    context.user_data['temp_alert'] = {'cg_id': cg_id, 'op': op}
    context.user_data['state'] = 'alert_price'
    keyboard = [[InlineKeyboardButton(f"{CANCEL} لغو", callback_data='cancel')]]
    await app.bot.send_message(
        chat_id=user_id,
        text=f"{ALERT} مبلغ مورد نظر را به صورت عددی وارد کنید (مثلاً 10000 یا 10000.50):\n\n`{op}` X\n\n"
             f"یا دکمه زیر رو بزن تا لغو کنی:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# --- ذخیره هشدار ---
async def save_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip().replace(',', '')
    try:
        price = float(text)
    except ValueError:
        keyboard = [[InlineKeyboardButton(f"{CANCEL} لغو", callback_data='cancel')]]
        await update.message.reply_text(f"{CROSS} فقط عدد معتبر وارد کنید (مثلاً 10000 یا 10000.50)!",
                                        reply_markup=InlineKeyboardMarkup(keyboard))
        return

    temp = context.user_data.get('temp_alert')
    if not temp:
        await update.message.reply_text(f"{CROSS} خطا!")
        return

    cg_id = temp['cg_id']
    op = temp['op']
    op_text = "بیشتر یا مساوی با" if op == '>=' else "کمتر یا مساوی با"
    for item in user_data[user_id]:
        if item['cg_id'] == cg_id:
            item['alert'] = {'op': op, 'price': price}
            symbol = item['symbol']
            break
    save_data()
    context.user_data.clear()
    await update.message.reply_text(
        f"{TICK} هشدار `{symbol}` تنظیم شد:\n{op_text} **${price:,.2f}**",
        reply_markup=main_menu(),
        parse_mode='Markdown'
    )

# --- حذف هشدار ---
async def clear_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cg_id = query.data.split('_')[1]
    for item in user_data[user_id]:
        if item['cg_id'] == cg_id and 'alert' in item:
            del item['alert']
            break
    save_data()
    await query.edit_message_text(f"{CROSS} هشدار `{item['symbol']}` حذف شد.", reply_markup=main_menu(), parse_mode='Markdown')

# --- حذف ---
async def remove_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cg_id = query.data.split('_')[1]
    removed_symbol = next((c['symbol'] for c in user_data[user_id] if c['cg_id'] == cg_id), "؟")
    user_data[user_id] = [c for c in user_data[user_id] if c['cg_id'] != cg_id]
    save_data()
    await query.edit_message_text(f"{DELETE} `{removed_symbol}` حذف شد.", reply_markup=main_menu(), parse_mode='Markdown')

# --- راهنما ---
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(
        f"**راهنمای کامل**\n\n"
        f"{COIN} **دکمه‌های معروف**: BTC, ETH, ...\n"
        f"{SEARCH} **جستجو**: هر ارزی رو تایپ کن\n"
        f"{TICK} **قیمت فوری**: بعد از اضافه کردن\n"
        f"هر **۱۵ دقیقه** قیمت میاد\n"
        f"{EDIT} **ویرایش**: زمان + هشدار\n"
        f"حداکثر **{MAX_COINS} ارز**\n"
        f"ساده و حرفه‌ای",
        reply_markup=main_menu(),
        parse_mode='Markdown'
    )

# --- برگشت ---
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(f"{BACK} منوی اصلی:", reply_markup=main_menu())

# --- هندلر متن ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = context.user_data.get('state')
    if state == 'alert_price':
        await save_alert(update, context)
    elif state == 'search':
        await search_coin(update, context)
    elif state == 'awaiting_selection':
        await update.message.reply_text(f"{CROSS} لطفاً از دکمه‌های پیشنهادی استفاده کن.", reply_markup=main_menu())
        context.user_data.clear()
    else:
        await search_coin(update, context)

# --- post_init ---
async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "شروع ربات و منوی اصلی"),
        BotCommand("menu", "نمایش منوی اصلی")
    ]
    await application.bot.set_my_commands(commands)

# --- اجرا ---
if __name__ == '__main__':
    app = Application.builder().token(TOKEN).build()
    app.post_init = post_init

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CallbackQueryHandler(add_coin_menu, pattern='^add_coin$'))
    app.add_handler(CallbackQueryHandler(select_popular, pattern='^select_pop_'))
    app.add_handler(CallbackQueryHandler(search_coin_start, pattern='^search_coin$'))
    app.add_handler(CallbackQueryHandler(cancel, pattern='^cancel$'))
    app.add_handler(CallbackQueryHandler(select_search, pattern='^select_search\|'))
    app.add_handler(CallbackQueryHandler(list_coins, pattern='^list_coins$'))
    app.add_handler(CallbackQueryHandler(edit_coin, pattern='^edit_'))
    app.add_handler(CallbackQueryHandler(set_time, pattern='^time_'))
    app.add_handler(CallbackQueryHandler(save_time, pattern='^settime_'))
    app.add_handler(CallbackQueryHandler(set_alert, pattern='^alert_'))
    app.add_handler(CallbackQueryHandler(select_alert_op, pattern='^alertop_'))
    app.add_handler(CallbackQueryHandler(clear_alert, pattern='^clearalert_'))
    app.add_handler(CallbackQueryHandler(remove_coin, pattern='^remove_'))
    app.add_handler(CallbackQueryHandler(help_cmd, pattern='^help$'))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    threading.Thread(target=run_scheduler, daemon=True).start()

    import os
    PORT = int(os.environ.get('PORT', 8443))
    DOMAIN = os.environ.get('RAILWAY_STATIC_URL', 'localhost')
    WEBHOOK_URL = f"https://{DOMAIN}/{TOKEN}"

    print(f"ربات در حال اجراست: {WEBHOOK_URL}")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL,
        flask_app=flask_app
    )

