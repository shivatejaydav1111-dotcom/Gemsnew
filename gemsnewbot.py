"""
Gemsnewbot (@Gemsnew_bot) — Telegram earning bot starter
Python 3.10+ | python-telegram-bot 21.x | SQLite

IMPORTANT:
- Do not paste this file into a command Answer field.
- Run it on a Python host / Termux environment with the dependencies installed.
- Set BOT_TOKEN, ADMIN_IDS, OFFERWALL_URL and optional settings as environment variables.
- OfferWall rewards are NOT automatically credited by opening a link. Add the provider's
  documented signed postback/callback before enabling automatic offer rewards.
"""

import os
import sqlite3
import logging
from datetime import date
from urllib.parse import urlparse

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
)

# -------------------- CONFIGURATION --------------------

BOT_TOKEN = os.getenv(8707648646:AAFoNGsPq-zPCbnsexKjZ5Ew1Q3Wb6IZrLE
ADMIN_IDS = {@Gemsnew_bot
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
OFFERWALL_URL = os.getenv(7063ed49498dc0b89e97b95c87c20b04
VIDEO_URL = os.getenv(
    "VIDEO_URL",
    "https://1024tenbox.com/f/file/Rox9rn6pTLe0Yqi1gAsQKA"
)
VIDEO_REWARD = int(os.getenv("VIDEO_REWARD", "10"))
DAILY_REWARD = int(os.getenv("DAILY_REWARD", "5"))
REFERRAL_REWARD = int(os.getenv("REFERRAL_REWARD", "10"))
DB_PATH = os.getenv("DB_PATH", "gemsnewbot.sqlite3")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("gemsnewbot")


# -------------------- DATABASE --------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0,
            referred_by INTEGER,
            joined_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS daily_claims (
            user_id INTEGER NOT NULL,
            claim_date TEXT NOT NULL,
            PRIMARY KEY(user_id, claim_date)
        );
        CREATE TABLE IF NOT EXISTS video_tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            reward INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_by INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS video_submissions (
            submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            proof TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_by INTEGER,
            UNIQUE(task_id, user_id),
            FOREIGN KEY(task_id) REFERENCES video_tasks(task_id)
        );
        CREATE TABLE IF NOT EXISTS withdrawals (
            withdrawal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS promotions (
            promotion_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            target TEXT NOT NULL,
            budget INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            reviewed_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)


def ensure_user(tg_user, referrer_id=None):
    uid = tg_user.id
    with db() as con:
        row = con.execute("SELECT user_id FROM users WHERE user_id=?", (uid,)).fetchone()
        if row:
            con.execute(
                "UPDATE users SET username=?, first_name=? WHERE user_id=?",
                (tg_user.username or "", tg_user.first_name or "", uid),
            )
            return False, None

        valid_referrer = None
        if referrer_id and referrer_id != uid:
            exists = con.execute(
                "SELECT user_id FROM users WHERE user_id=?", (referrer_id,)
            ).fetchone()
            if exists:
                valid_referrer = referrer_id

        con.execute(
            """INSERT INTO users(user_id, username, first_name, balance, referred_by, joined_at)
               VALUES(?,?,?,?,?,?)""",
            (uid, tg_user.username or "", tg_user.first_name or "", 0,
             valid_referrer, date.today().isoformat()),
        )
        if valid_referrer:
            add_coins_in_connection(con, valid_referrer, REFERRAL_REWARD,
                                    f"Referral reward for user {uid}")
        return True, valid_referrer


def add_coins_in_connection(con, user_id, amount, reason):
    con.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, user_id))
    con.execute(
        "INSERT INTO transactions(user_id, amount, reason, created_at) VALUES(?,?,?,?)",
        (user_id, amount, reason, date.today().isoformat()),
    )


def add_coins(user_id, amount, reason):
    with db() as con:
        exists = con.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not exists:
            return False
        add_coins_in_connection(con, user_id, amount, reason)
        return True


def get_balance(user_id):
    with db() as con:
        row = con.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        return int(row["balance"]) if row else 0


def is_admin(user_id):
    return user_id in ADMIN_IDS


def valid_http_url(value):
    try:
        p = urlparse(value)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


async def require_admin(update: Update):
    if not update.effective_user or not is_admin(update.effective_user.id):
        if update.effective_message:
            await update.effective_message.reply_text("Sorry, this command is for the bot admin only.")
        return False
    return True


# -------------------- MENUS / COMMANDS --------------------

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Watch Ads & Earn", callback_data="watchads"),
         InlineKeyboardButton("🎬 Video Tasks", callback_data="videos")],
        [InlineKeyboardButton("💰 My Balance", callback_data="balance"),
         InlineKeyboardButton("🎁 Daily Bonus", callback_data="daily")],
        [InlineKeyboardButton("👥 Refer & Earn", callback_data="referral"),
         InlineKeyboardButton("💸 Withdraw", callback_data="withdraw_help")],
        [InlineKeyboardButton("📣 Promote", callback_data="promote_help"),
         InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_id = None
    if context.args:
        try:
            ref_id = int(context.args[0])
        except ValueError:
            pass
    is_new, referred_by = ensure_user(user, ref_id)
    if is_new and referred_by:
        try:
            await context.bot.send_message(
                referred_by,
                f"🎉 A new user joined through your referral. You received {REFERRAL_REWARD} coins."
            )
        except Exception:
            pass

    await update.effective_message.reply_text(
        f"Welcome to Gemsnewbot, {user.first_name or 'friend'}! 💎\n\n"
        "Earn coins by completing available tasks. Rewards for submitted video tasks "
        "are added only after admin approval.\n\nChoose an option below:",
        reply_markup=main_menu(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await update.effective_message.reply_text(
        "💎 Gemsnewbot Help\n\n"
        "/start — Main menu\n"
        "/watchads — Open the offerwall\n"
        "/balance — Check your coins\n"
        "/daily — Claim daily bonus\n"
        "/referral — Get your referral link\n"
        "/videos — View video tasks\n"
        "/submitvideo TASK_ID PROOF — Submit a video task for review\n"
        "/withdraw AMOUNT PAYMENT_DETAILS — Request withdrawal\n"
        "/promote KIND TARGET BUDGET — Request a promotion\n\n"
        "Never send your Telegram login code or password to anyone."
    )


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await update.effective_message.reply_text(
        f"💰 Your balance: {get_balance(update.effective_user.id)} coins"
    )


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    uid = update.effective_user.id
    today = date.today().isoformat()
    with db() as con:
        already = con.execute(
            "SELECT 1 FROM daily_claims WHERE user_id=? AND claim_date=?", (uid, today)
        ).fetchone()
        if already:
            await update.effective_message.reply_text("You have already claimed today's bonus. Come back tomorrow!")
            return
        con.execute("INSERT INTO daily_claims(user_id, claim_date) VALUES(?,?)", (uid, today))
        add_coins_in_connection(con, uid, DAILY_REWARD, "Daily bonus")
    await update.effective_message.reply_text(
        f"🎁 You received {DAILY_REWARD} coins!\nNew balance: {get_balance(uid)} coins"
    )


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    me = await context.bot.get_me()
    link = f"https://t.me/{me.username}?start={update.effective_user.id}"
    await update.effective_message.reply_text(
        "👥 Your referral link:\n"
        f"{link}\n\n"
        f"Reward: {REFERRAL_REWARD} coins for each new user who joins through your link.\n"
        "Only new Telegram users are counted."
    )


async def watchads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    if not valid_http_url(OFFERWALL_URL) or "PASTE_YOUR_" in OFFERWALL_URL:
        await update.effective_message.reply_text(
            "📺 The offerwall is not configured yet. The admin must add the OfferWall.GG PUBLIC link."
        )
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Open OfferWall.GG", url=OFFERWALL_URL)
    ]])
    await update.effective_message.reply_text(
        "📺 Open the offerwall and complete eligible offers.\n"
        "Coins are credited only when a valid completion callback or admin verification is configured. "
        "Opening the link alone does not earn coins.",
        reply_markup=keyboard,
    )


def list_video_tasks_text():
    with db() as con:
        rows = con.execute(
            "SELECT task_id, url, reward FROM video_tasks WHERE active=1 ORDER BY task_id DESC LIMIT 30"
        ).fetchall()
    if not rows:
        return "No video tasks are available right now."
    lines = ["🎬 Available video tasks:"]
    for row in rows:
        lines.append(f"\nID: {row['task_id']} | Reward: {row['reward']} coins\n{row['url']}")
        lines.append(f"Submit with: /submitvideo {row['task_id']} proof_or_note")
    return "\n".join(lines)


async def videos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await update.effective_message.reply_text(list_video_tasks_text())


async def submitvideo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Usage: /submitvideo TASK_ID PROOF\nExample: /submitvideo 1 I finished the task\n"
            "Send a real proof URL or clear note. Admin approval is required."
        )
        return
    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("TASK_ID must be a number. Use /videos to see task IDs.")
        return
    proof = " ".join(context.args[1:])[:1000]
    uid = update.effective_user.id
    with db() as con:
        task = con.execute(
            "SELECT task_id FROM video_tasks WHERE task_id=? AND active=1", (task_id,)
        ).fetchone()
        if not task:
            await update.effective_message.reply_text("That task does not exist or is inactive.")
            return
        try:
            cur = con.execute(
                """INSERT INTO video_submissions(task_id,user_id,proof,status,created_at)
                   VALUES(?,?,?,'pending',?)""",
                (task_id, uid, proof, date.today().isoformat()),
            )
            submission_id = cur.lastrowid
        except sqlite3.IntegrityError:
            await update.effective_message.reply_text("You have already submitted this task.")
            return

    await update.effective_message.reply_text(
        f"✅ Submission #{submission_id} received. It is pending admin review."
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🎬 Video task submission #{submission_id}\n"
                f"User: {uid}\nTask ID: {task_id}\nProof: {proof}\n\n"
                f"Approve: /approvesub {submission_id}\nReject: /rejectsub {submission_id}"
            )
        except Exception:
            log.exception("Could not notify admin %s", admin_id)


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Usage: /withdraw AMOUNT PAYMENT_DETAILS\nExample: /withdraw 500 UPI details\n"
            "Use only payment details needed for payout; do not send passwords or OTPs."
        )
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("Amount must be a whole number of coins.")
        return
    if amount <= 0:
        await update.effective_message.reply_text("Amount must be greater than zero.")
        return
    details = " ".join(context.args[1:])[:500]
    uid = update.effective_user.id
    with db() as con:
        row = con.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        if not row or row["balance"] < amount:
            await update.effective_message.reply_text("Insufficient coin balance.")
            return
        # Reserve/deduct coins when request is created to prevent duplicate spending.
        add_coins_in_connection(con, uid, -amount, f"Reserved for withdrawal request")
        cur = con.execute(
            """INSERT INTO withdrawals(user_id,amount,details,status,created_at)
               VALUES(?,?,?,'pending',?)""",
            (uid, amount, details, date.today().isoformat()),
        )
        wid = cur.lastrowid
    await update.effective_message.reply_text(
        f"💸 Withdrawal request #{wid} submitted for admin review. {amount} coins are reserved."
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"💸 Withdrawal #{wid}\nUser: {uid}\nAmount: {amount} coins\nDetails: {details}\n\n"
                f"Approve: /approvewithdraw {wid}\nReject/refund: /rejectwithdraw {wid}"
            )
        except Exception:
            log.exception("Could not notify admin %s", admin_id)


async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    if len(context.args) < 3:
        await update.effective_message.reply_text(
            "Usage: /promote KIND TARGET BUDGET\n"
            "KIND examples: channel, group, bot, post\n"
            "Example: /promote channel @mychannel 100\n"
            "The request is reviewed by an admin. Coins are reserved from your balance."
        )
        return
    kind = context.args[0].lower()
    target = context.args[1]
    try:
        budget = int(context.args[2])
    except ValueError:
        await update.effective_message.reply_text("Budget must be a whole number of coins.")
        return
    if kind not in {"channel", "group", "bot", "post"}:
        await update.effective_message.reply_text("Kind must be channel, group, bot, or post.")
        return
    if budget <= 0:
        await update.effective_message.reply_text("Budget must be greater than zero.")
        return
    uid = update.effective_user.id
    with db() as con:
        row = con.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        if not row or row["balance"] < budget:
            await update.effective_message.reply_text("Insufficient coin balance for this promotion.")
            return
        add_coins_in_connection(con, uid, -budget, "Reserved for promotion request")
        cur = con.execute(
            """INSERT INTO promotions(user_id,kind,target,budget,status,created_at)
               VALUES(?,?,?,?,'pending',?)""",
            (uid, kind, target, budget, date.today().isoformat()),
        )
        pid = cur.lastrowid
    await update.effective_message.reply_text(
        f"📣 Promotion request #{pid} submitted for admin review. {budget} coins are reserved."
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"📣 Promotion #{pid}\nUser: {uid}\nKind: {kind}\nTarget: {target}\nBudget: {budget}\n\n"
                f"Approve: /approvepromo {pid}\nReject/refund: /rejectpromo {pid}"
            )
        except Exception:
            log.exception("Could not notify admin %s", admin_id)


# -------------------- ADMIN COMMANDS --------------------

async def addvideo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if len(context.args) < 1:
        await update.effective_message.reply_text(
            "Usage: /addvideo URL [REWARD]\n"
            "Example: /addvideo https://example.com/video 10"
        )
        return
    url = context.args[0]
    if not valid_http_url(url):
        await update.effective_message.reply_text("Please provide a valid http:// or https:// video URL.")
        return
    reward = VIDEO_REWARD
    if len(context.args) >= 2:
        try:
            reward = int(context.args[1])
        except ValueError:
            await update.effective_message.reply_text("Reward must be a whole number.")
            return
    if reward <= 0:
        await update.effective_message.reply_text("Reward must be greater than zero.")
        return
    with db() as con:
        cur = con.execute(
            "INSERT INTO video_tasks(url,reward,active,created_by) VALUES(?,?,1,?)",
            (url, reward, update.effective_user.id),
        )
        task_id = cur.lastrowid
    await update.effective_message.reply_text(f"Video task #{task_id} added with reward {reward} coins.")


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    with db() as con:
        total = con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        pending_v = con.execute("SELECT COUNT(*) AS n FROM video_submissions WHERE status='pending'").fetchone()["n"]
        pending_w = con.execute("SELECT COUNT(*) AS n FROM withdrawals WHERE status='pending'").fetchone()["n"]
        pending_p = con.execute("SELECT COUNT(*) AS n FROM promotions WHERE status='pending'").fetchone()["n"]
    await update.effective_message.reply_text(
        f"Admin summary\nUsers: {total}\nPending video submissions: {pending_v}\n"
        f"Pending withdrawals: {pending_w}\nPending promotions: {pending_p}"
    )


async def addcoins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update):
        return
    if len(context.args) < 2:
        await update.effective_message.reply_text("Usage: /addcoins USER_ID AMOUNT")
        return
    try:
        uid, amount = int(context.args[0]), int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("USER_ID and AMOUNT must be numbers.")
        return
    if amount == 0:
        await update.effective_message.reply_text("Amount cannot be zero.")
        return
    if add_coins(uid, amount, f"Admin adjustment by {update.effective_user.id}"):
        await update.effective_message.reply_text(f"Updated user {uid} by {amount} coins.")
        try:
            await context.bot.send_message(uid, f"Your balance was adjusted by an admin: {amount} coins.")
        except Exception:
            pass
    else:
        await update.effective_message.reply_text("User not found. They must start the bot first.")


async def approve_submission(update, context, approve):
    if not await require_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /approvesub SUBMISSION_ID (or /rejectsub ID)")
        return
    sid = int(context.args[0])
    with db() as con:
        sub = con.execute(
            """SELECT s.*, t.reward FROM video_submissions s
               JOIN video_tasks t ON t.task_id=s.task_id WHERE s.submission_id=?""",
            (sid,),
        ).fetchone()
        if not sub or sub["status"] != "pending":
            await update.effective_message.reply_text("Submission not found or already reviewed.")
            return
        new_status = "approved" if approve else "rejected"
        con.execute(
            "UPDATE video_submissions SET status=?, reviewed_by=? WHERE submission_id=?",
            (new_status, update.effective_user.id, sid),
        )
        if approve:
            add_coins_in_connection(con, sub["user_id"], sub["reward"], f"Approved video task #{sub['task_id']}")
    await update.effective_message.reply_text(f"Submission #{sid} {new_status}.")
    try:
        message = (
            f"🎉 Your video task #{sub['task_id']} was approved. "
            f"You received {sub['reward']} coins."
            if approve else f"Your video task submission #{sid} was rejected. Contact the admin if you think this is a mistake."
        )
        await context.bot.send_message(sub["user_id"], message)
    except Exception:
        pass


async def approvesub_command(update, context):
    await approve_submission(update, context, True)


async def rejectsub_command(update, context):
    await approve_submission(update, context, False)


async def review_withdrawal(update, context, approve):
    if not await require_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /approvewithdraw ID or /rejectwithdraw ID")
        return
    wid = int(context.args[0])
    with db() as con:
        row = con.execute("SELECT * FROM withdrawals WHERE withdrawal_id=?", (wid,)).fetchone()
        if not row or row["status"] != "pending":
            await update.effective_message.reply_text("Withdrawal not found or already reviewed.")
            return
        status = "approved" if approve else "rejected"
        con.execute(
            "UPDATE withdrawals SET status=?, reviewed_by=? WHERE withdrawal_id=?",
            (status, update.effective_user.id, wid),
        )
        if not approve:
            add_coins_in_connection(con, row["user_id"], row["amount"], f"Refund rejected withdrawal #{wid}")
    await update.effective_message.reply_text(f"Withdrawal #{wid} marked {status}.")
    try:
        await context.bot.send_message(
            row["user_id"],
            f"Your withdrawal request #{wid} was {status}."
            + (f" {row['amount']} coins were returned to your balance." if not approve else
               " Admin approval is recorded; payout must be sent separately.")
        )
    except Exception:
        pass


async def approvewithdraw_command(update, context):
    await review_withdrawal(update, context, True)


async def rejectwithdraw_command(update, context):
    await review_withdrawal(update, context, False)


async def review_promotion(update, context, approve):
    if not await require_admin(update):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /approvepromo ID or /rejectpromo ID")
        return
    pid = int(context.args[0])
    with db() as con:
        row = con.execute("SELECT * FROM promotions WHERE promotion_id=?", (pid,)).fetchone()
        if not row or row["status"] != "pending":
            await update.effective_message.reply_text("Promotion not found or already reviewed.")
            return
        status = "approved" if approve else "rejected"
        con.execute(
            "UPDATE promotions SET status=?, reviewed_by=? WHERE promotion_id=?",
            (status, update.effective_user.id, pid),
        )
        if not approve:
            add_coins_in_connection(con, row["user_id"], row["budget"], f"Refund rejected promotion #{pid}")
    await update.effective_message.reply_text(f"Promotion #{pid} marked {status}.")
    try:
        await context.bot.send_message(
            row["user_id"],
            f"Your promotion request #{pid} was {status}."
            + (f" {row['budget']} coins were refunded." if not approve else
               " The admin must still arrange delivery of the promotion.")
        )
    except Exception:
        pass


async def approvepromo_command(update, context):
    await review_promotion(update, context, True)


async def rejectpromo_command(update, context):
    await review_promotion(update, context, False)


# -------------------- BUTTON HANDLER --------------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data
    uid = query.from_user.id
    ensure_user(query.from_user)
    if key == "watchads":
        if not valid_http_url(OFFERWALL_URL) or "PASTE_YOUR_" in OFFERWALL_URL:
            await query.message.reply_text("Offerwall not configured yet. Admin must set OFFERWALL_URL.")
        else:
            await query.message.reply_text(
                "Open the offerwall. Completing an offer is not automatically verified unless a valid provider callback is configured.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Open OfferWall.GG", url=OFFERWALL_URL)
                ]]),
            )
    elif key == "videos":
        await query.message.reply_text(list_video_tasks_text())
    elif key == "balance":
        await query.message.reply_text(f"💰 Your balance: {get_balance(uid)} coins")
    elif key == "daily":
        # Reuse command logic via a concise callback-safe implementation.
        today = date.today().isoformat()
        with db() as con:
            already = con.execute(
                "SELECT 1 FROM daily_claims WHERE user_id=? AND claim_date=?", (uid, today)
            ).fetchone()
            if already:
                await query.message.reply_text("You already claimed today's bonus. Come back tomorrow.")
            else:
                con.execute("INSERT INTO daily_claims(user_id,claim_date) VALUES(?,?)", (uid, today))
                add_coins_in_connection(con, uid, DAILY_REWARD, "Daily bonus")
                await query.message.reply_text(f"🎁 You received {DAILY_REWARD} coins!")
    elif key == "referral":
        me = await context.bot.get_me()
        await query.message.reply_text(
            f"Your referral link:\nhttps://t.me/{me.username}?start={uid}\n"
            f"Reward: {REFERRAL_REWARD} coins per new referred user."
        )
    elif key == "withdraw_help":
        await query.message.reply_text("Use /withdraw AMOUNT PAYMENT_DETAILS to submit a withdrawal request.")
    elif key == "promote_help":
        await query.message.reply_text(
            "Use /promote KIND TARGET BUDGET\nExample: /promote channel @mychannel 100\n"
            "Kinds: channel, group, bot, post."
        )
    elif key == "help":
        await query.message.reply_text(
            "/start /watchads /balance /daily /referral /videos /submitvideo /withdraw /promote /help"
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Unhandled bot error", exc_info=context.error)


def main():
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_BOTFATHER_TOKEN_HERE":
        raise SystemExit(
            "Set BOT_TOKEN to your BotFather token as an environment variable. "
            "Do not share your token in chats."
        )
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("daily", daily_command))
    app.add_handler(CommandHandler("referral", referral_command))
    app.add_handler(CommandHandler("watchads", watchads_command))
    app.add_handler(CommandHandler("videos", videos_command))
    app.add_handler(CommandHandler("submitvideo", submitvideo_command))
    app.add_handler(CommandHandler("withdraw", withdraw_command))
    app.add_handler(CommandHandler("promote", promote_command))

    app.add_handler(CommandHandler("addvideo", addvideo_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("addcoins", addcoins_command))
    app.add_handler(CommandHandler("approvesub", approvesub_command))
    app.add_handler(CommandHandler("rejectsub", rejectsub_command))
    app.add_handler(CommandHandler("approvewithdraw", approvewithdraw_command))
    app.add_handler(CommandHandler("rejectwithdraw", rejectwithdraw_command))
    app.add_handler(CommandHandler("approvepromo", approvepromo_command))
    app.add_handler(CommandHandler("rejectpromo", rejectpromo_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_error_handler(error_handler)

    log.info("Gemsnewbot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
