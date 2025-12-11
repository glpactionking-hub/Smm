TELEGRAM_TOKEN = "PUT_YOUR_TELEGRAM_TOKEN_HERE"  # <-- यहाँ अपना Telegram bot token डालें
SMM_API_URL = "https://fampage.in/order"   # <-- आपका SMM panel API URL
SMM_API_KEY = "ZcRAMPJZfMiugE8OCDsViupGQXb7gzJ6FHCsPfq1YDdNMBo9xLm5n8Nq4FJD"  # <-- आप जो दिया था
ADMIN_IDS = [8013912448]  # <-- अपना Telegram user id (int). Multiple admins: [111,222]
MERCHANT_QR_URL = "upi://pay?pa=ajgorviphacksell@axl&pn=Ajgor%20Ali&mc=0000&mode=02&purpose=00"  # <-- आपके merchant QR की image URL या local path
DB_PATH = "smm_bot.db"
# --------------------------------------------------------

if TELEGRAM_TOKEN.startswith("8219608540:AAE9vOFgQMH-FfjuEWEOQY0M5ig4tsZdA2w"):
    raise RuntimeError("Please set TELEGRAM_TOKEN in the script before running.")

# ---------- Logging ----------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- DB ----------
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, telegram_id INTEGER UNIQUE, created_at TEXT)""")
cur.execute("""CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY, telegram_id INTEGER, amount REAL, type TEXT, note TEXT, created_at TEXT)""")
cur.execute("""CREATE TABLE IF NOT EXISTS payments (id TEXT PRIMARY KEY, telegram_id INTEGER, amount REAL, status TEXT, proof_file_id TEXT, created_at TEXT)""")
conn.commit()

# ---------- helpers ----------
def admin_only(func):
    @wraps(func)
    async def inner(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            try:
                await update.message.reply_text("आप admin नहीं हैं।")
            except Exception:
                pass
            return
        return await func(update, context, *args, **kwargs)
    return inner

# ---------- SMM API wrappers ----------
def smm_api_get(params: dict):
    params = params.copy()
    params["key"] = SMM_API_KEY
    try:
        r = requests.get(SMM_API_URL, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.exception("SMM API GET failed")
        return {"error": str(e)}

# ---------- Bot handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cur.execute("INSERT OR IGNORE INTO users (telegram_id, created_at) VALUES (?,?)", (user.id, datetime.utcnow().isoformat()))
    conn.commit()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Show QR (pay)", callback_data="show_qr")]])
    await update.message.reply_text(f"Hi {user.first_name}! Use /services to see services and /addfund to request adding money.", reply_markup=kb)

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "show_qr":
        if MERCHANT_QR_URL.startswith("http"):
            await q.message.reply_photo(MERCHANT_QR_URL, caption="Scan this QR to pay")
        else:
            with open(MERCHANT_QR_URL, "rb") as f:
                await q.message.reply_photo(f, caption="Scan this QR to pay")

async def services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Fetching services...")
    res = smm_api_get({"action": "services"})
    if not res or "error" in res:
        await msg.edit_text(f"Failed: {res.get('error') if isinstance(res, dict) else res}")
        return
    text_lines = ["Available services:"]
    services_map = {}
    idx = 1
    try:
        items = res.get("services") if isinstance(res, dict) and "services" in res else res
        for s in items:
            sid = s.get("service") or s.get("id") or s.get("service_id")
            name = s.get("name") or s.get("title") or str(sid)
            price = s.get("rate") or s.get("price") or ""
            text_lines.append(f"{idx}. {sid} — {name} — price: {price}")
            services_map[str(idx)] = sid
            idx += 1
    except Exception:
        await msg.edit_text("Unexpected services format from panel.")
        return
    context.user_data["services_map"] = services_map
    await msg.edit_text("
".join(text_lines) + "

To order: /order <number_or_id> <quantity> [target]")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Checking balance...")
    res = smm_api_get({"action": "balance"})
    if not res or "error" in res:
        await msg.edit_text(f"Failed: {res.get('error') if isinstance(res, dict) else res}")
        return
    bal = None
    if isinstance(res, dict):
        bal = res.get("balance") or res.get("credit")
    await msg.edit_text(f"Panel balance: {bal}")

async def order_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /order <service_number_or_id> <quantity> [target]")
        return
    service_ref = args[0]
    quantity = args[1]
    target = args[2] if len(args) >= 3 else ""
    services_map = context.user_data.get("services_map") or {}
    service_id = services_map.get(service_ref, service_ref)
    await update.message.reply_text(f"Placing order: service={service_id}, quantity={quantity}, target={target}")
    payload = {"action": "add", "service": str(service_id), "quantity": str(quantity)}
    if target:
        payload["link"] = target
    res = smm_api_get(payload)
    if not res or "error" in res:
        await update.message.reply_text(f"Order failed: {res.get('error') if isinstance(res, dict) else res}")
        return
    await update.message.reply_text(f"Order response: {json.dumps(res)}")

async def addfund(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /addfund <amount>")
        return
    try:
        amount = float(args[0])
    except Exception:
        await update.message.reply_text("Enter a valid numeric amount.")
        return
    pid = str(uuid.uuid4())[:8]
    cur.execute("INSERT INTO payments (id, telegram_id, amount, status, created_at) VALUES (?,?,?,?,?)", (pid, update.effective_user.id, amount, "pending", datetime.utcnow().isoformat()))
    conn.commit()
    await update.message.reply_text(f"Payment request created. ID: {pid}
Amount: {amount}
Pay using the QR and then send proof with /payproof {pid}")

async def mypending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cur.execute("SELECT id, amount, status, created_at FROM payments WHERE telegram_id=? ORDER BY created_at DESC", (uid,))
    rows = cur.fetchall()
    if not rows:
        await update.message.reply_text("No pending payments.")
        return
    lines = [f"{r[0]} — {r[1]} — status: {r[2]} — {r[3]}" for r in rows]
    await update.message.reply_text("
".join(lines))

async def payproof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = update.message.caption or ""
    args = context.args
    pid = args[0] if args else caption.strip()
    if not pid:
        await update.message.reply_text("Send the proof photo with caption as the payment ID, or use /payproof <id> while attaching a photo.")
        return
    if not update.message.photo:
        await update.message.reply_text("Attach a photo of the payment proof.")
        return
    file_id = update.message.photo[-1].file_id
    cur.execute("SELECT id FROM payments WHERE id=? AND telegram_id=?", (pid, update.effective_user.id))
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("Payment id not found for you.")
        return
    cur.execute("UPDATE payments SET proof_file_id=?, status=? WHERE id=?", (file_id, "awaiting_confirmation", pid))
    conn.commit()
    for a in ADMIN_IDS:
        try:
            await context.bot.send_photo(chat_id=a, photo=file_id, caption=f"Payment proof for {pid} from {update.effective_user.id}")
            await context.bot.send_message(chat_id=a, text=f"Confirm with /confirm {pid} or reject with /reject {pid}")
        except Exception:
            logger.exception("Failed to notify admin")
    await update.message.reply_text("Proof uploaded. Admins have been notified.")

@admin_only
async def confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /confirm <payment_id>")
        return
    pid = args[0]
    cur.execute("SELECT telegram_id, amount, status FROM payments WHERE id=?", (pid,))
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("Payment id not found.")
        return
    if row[2] == "confirmed":
        await update.message.reply_text("Already confirmed.")
        return
    uid, amount, _ = row
    cur.execute("UPDATE payments SET status=? WHERE id=?", ("confirmed", pid))
    cur.execute("INSERT INTO ledger (telegram_id, amount, type, note, created_at) VALUES (?,?,?,?,?)", (uid, amount, "credit", f"Payment {pid} confirmed", datetime.utcnow().isoformat()))
    conn.commit()
    await update.message.reply_text(f"Payment {pid} confirmed. Credited {amount} to user {uid}.")
    try:
        await context.bot.send_message(chat_id=uid, text=f"Your payment {pid} of amount {amount} has been confirmed by admin.")
    except Exception:
        logger.exception("Failed to message user after confirm")

@admin_only
async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /reject <payment_id>")
        return
    pid = args[0]
    cur.execute("SELECT telegram_id, amount FROM payments WHERE id=?", (pid,))
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("Payment id not found.")
        return
    cur.execute("UPDATE payments SET status=? WHERE id=?", ("rejected", pid))
    conn.commit()
    await update.message.reply_text(f"Payment {pid} rejected.")
    try:
        await context.bot.send_message(chat_id=row[0], text=f"Your payment {pid} was rejected by admin. Please try again or contact support.")
    except Exception:
        logger.exception("Failed to message user after reject")

async def ledger_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cur.execute("SELECT amount, type, note, created_at FROM ledger WHERE telegram_id=? ORDER BY created_at DESC LIMIT 20", (uid,))
    rows = cur.fetchall()
    if not rows:
        await update.message.reply_text("No ledger entries.")
        return
    lines = [f"{r[3]} — {r[1]} {r[0]} — {r[2]}" for r in rows]
    await update.message.reply_text("
".join(lines))

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. Use /help")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", lambda u,c: u.message.reply_text("Commands: /services /balance /order /addfund /mypending /ledger")))
    app.add_handler(CommandHandler("services", services))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("order", order_cmd))
    app.add_handler(CommandHandler("addfund", addfund))
    app.add_handler(CommandHandler("mypending", mypending))
    app.add_handler(CommandHandler("payproof", payproof))
    app.add_handler(CommandHandler("confirm", confirm_payment))
    app.add_handler(CommandHandler("reject", reject_payment))
    app.add_handler(CommandHandler("ledger", ledger_cmd))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.PHOTO & filters.CaptionRegex(r"^[A-Za-z0-9_-]{4,}$"), payproof))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    logger.info("Starting bot...")
    app.run_polling()

if __name__ == "__main__":
    main()