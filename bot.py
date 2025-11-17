import os
import logging
import json
import time
import asyncio
import requests
import redis
import threading
import asyncio
from threading import Thread
from asyncio import run_coroutine_threadsafe
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

main_loop = None  
# --- تنظیمات ---
TOKEN = os.environ["TOKEN"]
UPSTASH_REDIS_URL = os.environ["UPSTASH_REDIS_URL"]
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

# --- لاگ ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- چک URL ---
if not RENDER_EXTERNAL_URL:
    logger.error("RENDER_EXTERNAL_URL تنظیم نشده!")
    raise ValueError("RENDER_EXTERNAL_URL is required!")
if not RENDER_EXTERNAL_URL.startswith("http"):
    RENDER_EXTERNAL_URL = "https://" + RENDER_EXTERNAL_URL

WEBHOOK_URL = f"{RENDER_EXTERNAL_URL}/{TOKEN}"
logger.info(f"Webhook URL: {WEBHOOK_URL}")

# --- اتصال به Redis ---
r = redis.from_url(
    UPSTASH_REDIS_URL,
    decode_responses=True,
    ssl_cert_reqs=None
)
r.ping()
logger.info("Redis متصل شد!")

# --- توابع Redis ---
def get_user_data(user_id):
    data = r.get(f"user:{user_id}")
    return json.loads(data) if data else []

def set_user_data(user_id, data):
    r.set(f"user:{user_id}", json.dumps(data, ensure_ascii=False))

# --- کش قیمت ---
def get_price(cg_id):
    cache_key = f"price:{cg_id}"
    try:
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)['price']
    except:
        pass

    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
        headers = {"User-Agent": "CryptoBot/1.0"}
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 429:
            cached = r.get(cache_key)
            if cached:
                return json.loads(cached)['price']
            return None
        price = resp.json().get(cg_id, {}).get("usd")
        if price is not None:
            r.setex(cache_key, 55, json.dumps({"price": price, "timestamp": time.time()}))
            return price
    except:
        pass

    try:
        cached = r.get(cache_key)
        if cached:
            return json.loads(cached)['price']
    except:
        pass
    return None

# --- چک قیمت دوره‌ای ---
async def safe_check_prices(context: ContextTypes.DEFAULT_TYPE):
    bot = context.application.bot
    while True:
        try:
            current_time = time.time()
            keys = r.keys("user:*")
            unique_cg_ids = set()
            all_settings = {}

            for key in keys:
                try:
                    user_id = int(key.split(":")[1])
                    settings = get_user_data(user_id)
                    all_settings[user_id] = settings
                    for item in settings:
                        unique_cg_ids.add(item['cg_id'])
                except:
                    continue

            # Batch fetch
            if unique_cg_ids:
                try:
                    ids = ','.join(unique_cg_ids)
                    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=usd"
                    headers = {"User-Agent": "CryptoBot/1.0"}
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.status_code != 429:
                        data = resp.json()
                        for cg_id in unique_cg_ids:
                            price = data.get(cg_id, {}).get("usd")
                            if price is not None:
                                r.setex(f"price:{cg_id}", 55, json.dumps({"price": price}))
                except:
                    pass

            # پردازش کاربران
            for user_id, settings in all_settings.items():
                if not settings:
                    continue
                for item in settings[:]:
                    price = get_price(item['cg_id'])
                    if price is None:
                        continue
                    last_sent = item.get('last_sent', 0)
                    if current_time - last_sent < item['period'] * 60:
                        continue
                    if 'alert' in item:
                        op = item['alert']['op']
                        target = item['alert']['price']
                        if (op == '>=' and price < target) or (op == '<=' and price > target):
                            continue
                        op_text = "بیشتر یا مساوی با" if op == '>=' else "کمتر یا مساوی با"
                        message = f"هشدار قیمت!\n\n**{item['symbol']}**: `${price:,.2f}`\n**شرط:** {op_text} `${target:,.2f}`"
                    else:
                        message = f"قیمت لحظه‌ای\n**{item['symbol']}**: `${price:,.2f}`"

                    try:
                        await bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
                        item['last_sent'] = current_time
                    except:
                        pass
                set_user_data(user_id, settings)
        except Exception as e:
            logger.error(f"Price checker error: {e}")
        await asyncio.sleep(60)

# --- ایموجی‌ها ---
TICK = "✅"
CROSS = "❌"
COIN = "💰"
EDIT = "✏️"
ALERT = "🔔"
DELETE = "🗑️"
BACK = "🔙"
SEARCH = "🔍"
CANCEL = "❌"

# --- ارزهای معروف ---
POPULAR_COINS = {
    'BTC': ('bitcoin', 'Bitcoin'), 'ETH': ('ethereum', 'Ethereum'), 'BNB': ('binancecoin', 'BNB'),
    'SOL': ('solana', 'Solana'), 'XRP': ('ripple', 'XRP'), 'TON': ('the-open-network', 'Toncoin'),
    'FET': ('fetch-ai', 'Fetch.AI'), 'SUI': ('sui', 'Sui'), 'CAKE': ('pancakeswap', 'PancakeSwap'),
    'VET': ('vechain', 'VeChain'), 'AAVE': ('aave', 'Aave'), 'TAO': ('bittensor', 'Bittensor'),
    'LINK': ('chainlink', 'Chainlink'), 'GALA': ('gala', 'Gala')
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
    (8 * 60, "۸ ساعت"), (12 * 60, "۱۲ ساعت"), (24 * 60, "۲۴ ساعت"),
    (36 * 60, "۳۶ ساعت"), (7 * 24 * 60, "هفته‌ای یکبار")
]

# --- منو ---
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{COIN} اضافه کردن ارز", callback_data='add_coin')],
        [InlineKeyboardButton(f"{SEARCH} لیست ارزها", callback_data='list_coins')],
        [InlineKeyboardButton("راهنما کامل", callback_data='help')]
    ])

# --- هندلرها ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not r.exists(f"user:{user_id}"):
        set_user_data(user_id, [])
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

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.clear()
    text = f"{BACK} منوی اصلی:"
    if update.message:
        await update.message.reply_text(text, reply_markup=main_menu())
    else:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu())

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
    await query.edit_message_text(
        text="ارز رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def select_popular(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    symbol = query.data.split('_')[2]
    cg_id, _ = POPULAR_COINS[symbol]
    await query.edit_message_text(f"{TICK} در حال اضافه کردن **{symbol}**...", parse_mode='Markdown')
    await add_coin_logic(user_id, symbol, cg_id, query, context)

async def search_coin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['state'] = 'search'
    keyboard = [[InlineKeyboardButton(f"{CANCEL} لغو", callback_data='cancel')]]
    await query.edit_message_text(
        f"{SEARCH} نام یا نماد ارز رو بنویس (مثلاً `BTC` یا `solana`):\n\nیا دکمه زیر رو بزن تا لغو کنی:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def search_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    query_text = update.message.text.strip().lower()
    results = []
    for symbol, cg_id in ALL_COINS.items():
        if query_text in symbol.lower() or query_text in cg_id.lower():
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
    await update.message.reply_text(f"نتایج برای `{query_text}`:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
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
    await query.edit_message_text(f"{TICK} در حال اضافه کردن **{symbol}**...", parse_mode='Markdown')
    await add_coin_logic(user_id, symbol, cg_id, query, context)

async def add_coin_logic(user_id, symbol, cg_id, query_or_msg, context: ContextTypes.DEFAULT_TYPE):
    settings = get_user_data(user_id)
    if any(c['cg_id'] == cg_id for c in settings):
        price = get_price(cg_id)
        if price:
            await context.application.bot.send_message(
                chat_id=user_id,
                text=f"{COIN} قیمت لحظه‌ای\n\n**نام ارز:** `{symbol}`\n**قیمت:** `${price:,.2f}`",
                parse_mode='Markdown'
            )
        if hasattr(query_or_msg, 'edit_message_text'):
            await query_or_msg.edit_message_text(f"{TICK} **{symbol}** قبلاً اضافه شده!")
        else:
            await query_or_msg.message.reply_text(f"{TICK} **{symbol}** قبلاً اضافه شده!", reply_markup=main_menu())
        return

    if len(settings) >= MAX_COINS:
        text = f"{CROSS} **حداکثر {MAX_COINS} ارز می‌تونی داشته باشی!**\nاول یکی رو با {DELETE} پاک کن."
        if hasattr(query_or_msg, 'edit_message_text'):
            await query_or_msg.edit_message_text(text, reply_markup=main_menu(), parse_mode='Markdown')
        else:
            await query_or_msg.message.reply_text(text, reply_markup=main_menu(), parse_mode='Markdown')
        return

    settings.append({
        'symbol': symbol,
        'cg_id': cg_id,
        'period': 15,
        'last_sent': time.time()
    })
    set_user_data(user_id, settings)

    if hasattr(query_or_msg, 'edit_message_text'):
        await query_or_msg.edit_message_text(f"{TICK} **{symbol}** با موفقیت اضافه شد!\nهر **۱۵ دقیقه** قیمت برات میاد.\n{EDIT} می‌تونی زمان یا {ALERT} هشدار بذاری.", parse_mode='Markdown')
    else:
        await query_or_msg.message.reply_text(f"{TICK} **{symbol}** با موفقیت اضافه شد!", parse_mode='Markdown')

    price = get_price(cg_id)
    if price:
        await context.application.bot.send_message(
            chat_id=user_id,
            text=f"{COIN} قیمت لحظه‌ای\n\n**نام ارز:** `{symbol}`\n**قیمت:** `${price:,.2f}`",
            parse_mode='Markdown'
        )
    await context.application.bot.send_message(chat_id=user_id, text=f"{BACK} منوی اصلی:", reply_markup=main_menu())

async def list_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    context.user_data.clear()
    settings = get_user_data(user_id)
    if not settings:
        await query.edit_message_text(f"{CROSS} هیچ ارزی نداری! از منو اضافه کن.", reply_markup=main_menu())
        return

    keyboard = []
    for item in settings:
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
    await query.edit_message_text(
        text=f"{SEARCH} ارزهایت ({len(settings)}/{MAX_COINS}):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def edit_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cg_id = query.data.split('_')[1]
    settings = get_user_data(user_id)
    item = next((i for i in settings if i['cg_id'] == cg_id), None)
    if not item:
        await query.edit_message_text(f"{CROSS} خطا: ارز پیدا نشد!", reply_markup=main_menu())
        return
    keyboard = [
        [InlineKeyboardButton(f"{EDIT} تغییر زمان", callback_data=f"time_{cg_id}")],
        [InlineKeyboardButton(f"{ALERT} تنظیم هشدار", callback_data=f"alert_{cg_id}")],
        [InlineKeyboardButton(f"{CROSS} حذف هشدار", callback_data=f"clearalert_{cg_id}") if 'alert' in item else InlineKeyboardButton(" ", callback_data='none')],
        [InlineKeyboardButton(f"{BACK} برگشت", callback_data='list_coins')]
    ]
    await query.edit_message_text(f"{EDIT} ویرایش `{item['symbol']}`:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cg_id = query.data.split('_')[1]
    settings = get_user_data(query.from_user.id)
    item = next((i for i in settings if i['cg_id'] == cg_id), None)
    symbol = item['symbol'] if item else "؟"
    keyboard = []
    for mins, label in TIME_OPTIONS:
        keyboard.append([InlineKeyboardButton(label, callback_data=f"settime_{cg_id}_{mins}")])
    keyboard.append([InlineKeyboardButton(f"{BACK} برگشت", callback_data=f"edit_{cg_id}")])
    await query.edit_message_text(f"{EDIT} زمان `{symbol}`:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def save_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split('_')
    cg_id = parts[1]
    mins = int(parts[2])
    settings = get_user_data(user_id)
    for i in settings:
        if i['cg_id'] == cg_id:
            i['period'] = mins
            i['last_sent'] = time.time()
            break
    set_user_data(user_id, settings)
    time_label = next((t[1] for t in TIME_OPTIONS if t[0] == mins), f"هر {mins} دقیقه")
    await query.edit_message_text(f"{TICK} زمان `{i['symbol']}` به **{time_label}** تغییر کرد.", reply_markup=main_menu(), parse_mode='Markdown')

async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cg_id = query.data.split('_')[1]
    settings = get_user_data(query.from_user.id)
    item = next((i for i in settings if i['cg_id'] == cg_id), None)
    symbol = item['symbol'] if item else "؟"
    keyboard = [
        [InlineKeyboardButton("بیشتر از (≥)", callback_data=f"alertop_{cg_id}_>=")],
        [InlineKeyboardButton("کمتر از (≤)", callback_data=f"alertop_{cg_id}_<=")],
        [InlineKeyboardButton(f"{CANCEL} لغو", callback_data='cancel')]
    ]
    await query.edit_message_text(f"{ALERT} هشدار `{symbol}`:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def select_alert_op(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    parts = query.data.split('_')
    cg_id = parts[1]
    op = parts[2]
    context.user_data['temp_alert'] = {'cg_id': cg_id, 'op': op}
    context.user_data['state'] = 'alert_price'
    keyboard = [[InlineKeyboardButton(f"{CANCEL} لغو", callback_data='cancel')]]
    await context.application.bot.send_message(
        chat_id=user_id,
        text=f"{ALERT} مبلغ مورد نظر را به صورت عددی وارد کنید (مثلاً 10000 یا 10000.50):\n\n`{op}` X\n\nیا دکمه زیر رو بزن تا لغو کنی:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def save_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip().replace(',', '')
    try:
        price = float(text)
    except ValueError:
        await update.message.reply_text(f"{CROSS} فقط عدد معتبر وارد کنید (مثلاً 10000 یا 10000.50)!")
        return
    temp = context.user_data.get('temp_alert')
    if not temp:
        await update.message.reply_text(f"{CROSS} خطا! دوباره امتحان کن.", reply_markup=main_menu())
        return
    cg_id = temp['cg_id']
    op = temp['op']
    op_text = "بیشتر یا مساوی با" if op == '>=' else "کمتر یا مساوی با"
    settings = get_user_data(user_id)
    for i in settings:
        if i['cg_id'] == cg_id:
            i['alert'] = {'op': op, 'price': price}
            break
    set_user_data(user_id, settings)
    context.user_data.clear()
    await update.message.reply_text(
        f"{TICK} هشدار `{i['symbol']}` تنظیم شد:\n{op_text} **${price:,.2f}**",
        reply_markup=main_menu(),
        parse_mode='Markdown'
    )

async def clear_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cg_id = query.data.split('_')[1]
    settings = get_user_data(user_id)
    for i in settings:
        if i['cg_id'] == cg_id and 'alert' in i:
            del i['alert']
            await query.edit_message_text(f"{CROSS} هشدار `{i['symbol']}` حذف شد.", reply_markup=main_menu(), parse_mode='Markdown')
            set_user_data(user_id, settings)
            return

async def remove_coin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    cg_id = query.data.split('_')[1]
    settings = get_user_data(user_id)
    removed_symbol = "؟"
    new_settings = [item for item in settings if item['cg_id'] != cg_id]
    for item in settings:
        if item['cg_id'] == cg_id:
            removed_symbol = item['symbol']
            break
    set_user_data(user_id, new_settings)
    await query.edit_message_text(f"{DELETE} `{removed_symbol}` حذف شد.", reply_markup=main_menu(), parse_mode='Markdown')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(
        text=(
            f"**راهنمای کامل**\n\n"
            f"{COIN} **دکمه‌های معروف**: BTC, ETH, ...\n"
            f"{SEARCH} **جستجو**: هر ارزی رو تایپ کن\n"
            f"{TICK} **قیمت فوری**: بعد از اضافه کردن\n"
            f"هر **۱۵ دقیقه** قیمت میاد\n"
            f"{EDIT} **ویرایش**: زمان + هشدار\n"
            f"حداکثر **{MAX_COINS} ارز**\n"
            f"ساده و حرفه‌ای"
        ),
        reply_markup=main_menu(),
        parse_mode='Markdown'
    )

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(f"{BACK} منوی اصلی:", reply_markup=main_menu())

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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

# --- Flask App ---
flask_app = Flask(__name__)

@flask_app.route('/health', methods=['GET'])
def health_check():
    try:
        r.ping()
        return 'OK', 200
    except:
        return 'Redis Down', 500

@flask_app.route(f'/{TOKEN}', methods=['POST'])
def telegram_webhook():
    global main_loop
    try:
        update_json = request.get_json(force=True)
        if not update_json:
            return 'No JSON received', 400

        update = Update.de_json(update_json, application.bot)
        
        if main_loop is None:
            logger.error("main_loop هنوز آماده نیست!")
            return 'Loop not ready', 503

        # ارسال آپدیت به loop اصلی (همان loop ای که application داره)
        asyncio.run_coroutine_threadsafe(
            application.process_update(update),
            main_loop
        )
        
        return 'OK', 200

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return 'Error', 500


# یه route ساده برای تست زنده بودن سرور
@flask_app.route('/')
def index():
    return "ربات فعاله و وب‌هوک درست کار می‌کنه! 🚀", 200


@flask_app.route('/health')
def health_check():
    try:
        r.ping()
        return "OK - Redis Connected", 200
    except:
        return "Redis Down", 500

def run_flask():
    """اجرای Flask در ترد جدا، اما با دسترسی به همان loop اصلی"""
    global main_loop
    
    # صبر می‌کنیم تا main_loop مقدار بگیرد (حداکثر 10 ثانیه)
    import time
    timeout = 10
    start_time = time.time()
    while main_loop is None and time.time() - start_time < timeout:
        time.sleep(0.1)
    
    if main_loop is None:
        logger.error("main_loop هیچوقت مقدار نگرفت! Flask اجرا نمیشه.")
        return
    
    # حالا از همان loop اصلی استفاده می‌کنیم
    asyncio.set_event_loop(main_loop)
    
    flask_app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        use_reloader=False,
        threaded=True
    )

# --- اجرای اصلی ---
async def main():
    global application, main_loop
    
    # خیلی مهم: اول از همه loop اصلی رو می‌گیریم و ذخیره می‌کنیم
    main_loop = asyncio.get_running_loop()
    logger.info("main_loop با موفقیت گرفته شد")

    application = Application.builder().token(TOKEN).concurrent_updates(True).build()

    # تمام هندلرها (همون قبلی‌ها رو داری، فقط اینا رو اضافه/تغییر بده)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CallbackQueryHandler(add_coin_menu, pattern='^add_coin$'))
    application.add_handler(CallbackQueryHandler(select_popular, pattern='^select_pop_'))
    application.add_handler(CallbackQueryHandler(search_coin_start, pattern='^search_coin$'))
    application.add_handler(CallbackQueryHandler(cancel, pattern='^cancel$'))
    application.add_handler(CallbackQueryHandler(select_search, pattern=r'^select_search\|'))
    application.add_handler(CallbackQueryHandler(list_coins, pattern='^list_coins$'))
    application.add_handler(CallbackQueryHandler(edit_coin, pattern='^edit_'))
    application.add_handler(CallbackQueryHandler(set_time, pattern='^time_'))
    application.add_handler(CallbackQueryHandler(save_time, pattern='^settime_'))
    application.add_handler(CallbackQueryHandler(set_alert, pattern='^alert_'))
    application.add_handler(CallbackQueryHandler(select_alert_op, pattern='^alertop_'))
    application.add_handler(CallbackQueryHandler(clear_alert, pattern='^clearalert_'))
    application.add_handler(CallbackQueryHandler(remove_coin, pattern='^remove_'))
    application.add_handler(CallbackQueryHandler(help_cmd, pattern='^help$'))
    application.add_handler(CallbackQueryHandler(back_to_menu, pattern='^back$'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(error_handler)

    await application.initialize()
    await application.bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook تنظیم شد: {WEBHOOK_URL}")

    # اجرای Flask در ترد جدا
    Thread(target=run_flask, daemon=True).start()
    logger.info("Flask server در ترد جدا شروع شد")

    # چک قیمت هر ۶۰ ثانیه
    application.job_queue.run_repeating(
        callback=safe_check_prices,
        interval=60,
        first=10
    )
    logger.info("چک قیمت هر ۶۰ ثانیه فعال شد")

    logger.info("ربات کاملاً فعال شد و منتظر پیام‌هاست!")

    # نگه داشتن loop اصلی زنده (برای همیشه)
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    asyncio.run(main())



