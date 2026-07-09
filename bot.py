import os
import re
import json
import random
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from codes import CODES

# ── Keep-alive server ─────────────────────────────────────────────────────────

class _KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot ishlayapti!")

    def log_message(self, *args):
        pass  # serverning har bir so'rovini loglarga chiqarmaymiz


def start_keep_alive():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), _KeepAliveHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Keep-alive server port {port} da ishga tushdi")


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN muhit o'zgaruvchisi o'rnatilmagan!")

_raw_admin = os.environ.get("ADMIN_TELEGRAM_ID", "")
ADMIN_ID: int = 0
ADMIN_USERNAME: str = ""
if _raw_admin.lstrip("@").isdigit():
    ADMIN_ID = int(_raw_admin.lstrip("@"))
else:
    ADMIN_USERNAME = _raw_admin.lstrip("@").lower()

CHANNEL_USERNAME = os.environ.get("CHANNEL_USERNAME", "").lstrip("@").lower()

VIEWS_FILE = os.path.join(os.path.dirname(__file__), "views.json")
VIDEOS_FILE = os.path.join(os.path.dirname(__file__), "video_ids.json")


# ── Ma'lumotlarni yuklash / saqlash ──────────────────────────────────────────

def load_views() -> dict:
    if os.path.exists(VIEWS_FILE):
        with open(VIEWS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {code: 0 for code in CODES}


def save_views(views: dict):
    with open(VIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(views, f, ensure_ascii=False, indent=2)


def add_view(code: str):
    views = load_views()
    views[code] = views.get(code, 0) + 1
    save_views(views)


def load_videos() -> dict:
    if os.path.exists(VIDEOS_FILE):
        with open(VIDEOS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_videos(videos: dict):
    with open(VIDEOS_FILE, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)


def is_admin(user) -> bool:
    if ADMIN_ID and user.id == ADMIN_ID:
        return True
    if ADMIN_USERNAME and (user.username or "").lower() == ADMIN_USERNAME:
        return True
    return False


# ── Klaviatura ────────────────────────────────────────────────────────────────

def main_keyboard():
    keyboard = [
        [KeyboardButton("📋 Dramalar ro'yxati")],
        [KeyboardButton("🎲 Random drama"), KeyboardButton("🔥 Eng ko'p ko'rilgan")],
        [KeyboardButton("📩 Aloqa / Taklif")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ── Yordamchi: video saqlash ──────────────────────────────────────────────────

async def _save_video_with_code(msg, code: str, file_id: str):
    """file_id ni kodga bog'lab saqlaydi va javob yuboradi."""
    videos = load_videos()
    videos[code] = file_id
    save_videos(videos)
    await msg.reply_text(
        f"✅ {code} — {CODES[code]}\nVideo saqlandi!",
    )
    logger.info(f"Video saqlandi: {code} → {file_id}")


# ── Drama yuborish ────────────────────────────────────────────────────────────

def get_episode_codes(base_code: str) -> list:
    """Asosiy kod (A001, B002 ...) uchun barcha qism kodlarini tartiblangan holda qaytaradi."""
    import re as _re
    episodes = []
    for code in CODES:
        if code != base_code and code.startswith(base_code):
            # Faqat raqam bilan tugaydigan kodlar (A0011, B00212 ...)
            suffix = code[len(base_code):]
            if suffix.isdigit():
                episodes.append((int(suffix), code))
    episodes.sort(key=lambda x: x[0])
    return [code for _, code in episodes]


async def send_drama(update: Update, code: str):
    name = CODES[code]
    videos = load_videos()
    add_view(code)

    # To'plam kodi yuborilsa — barcha qismlarni yuborish
    episodes = get_episode_codes(code)
    if episodes:
        loaded = [c for c in episodes if c in videos]
        if not loaded:
            await update.message.reply_text(
                f"🎬 *{name.replace(' — barcha qismlar', '')}*\n\n"
                f"⏳ Qismlar hali yuklanmagan.",
                parse_mode="Markdown",
                reply_markup=main_keyboard(),
            )
            return

        short_name = name.replace(" — barcha qismlar", "")
        await update.message.reply_text(
            f"🎬 *{short_name}* — barcha qismlar yuborilmoqda ({len(loaded)} ta)...",
            parse_mode="Markdown",
        )
        for ep_code in loaded:
            ep_name = CODES[ep_code]
            await update.message.reply_video(
                video=videos[ep_code],
                caption=f"🎬 {ep_name}",
            )
        await update.message.reply_text(
            f"✅ *{short_name}* — barcha qismlar yuborildi!",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )
        return

    # Alohida qism kodi
    if code in videos:
        await update.message.reply_video(
            video=videos[code],
            caption=f"🎬 *{name}*",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )
    else:
        await update.message.reply_text(
            f"🎬 *{name}*\n\n⏳ Video hali yuklanmagan.",
            parse_mode="Markdown",
            reply_markup=main_keyboard(),
        )


# ── Foydalanuvchi handlerlari ─────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Assalomu alaykum!\n\n"
        "Quyidagi tugmalardan foydalaning yoki drama kodini yuboring:",
        reply_markup=main_keyboard(),
    )


async def dramas_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    videos = load_videos()

    # Faqat asosiy (to'plam) kodlar — qisqa kod formatda: A001, B001, C001 ...
    main_codes = {c: n for c, n in CODES.items() if len(c) <= 4}

    a_lines = ["⚔️ *Urush / Jang:*"]
    b_lines = ["💕 *Romantik:*"]
    c_lines = ["🏫 *Maktab:*"]

    for code, name in sorted(main_codes.items()):
        icon = "✅" if code in videos else "⏳"
        short_name = name.replace(" — barcha qismlar", "")
        line = f"{icon} `{code}` — {short_name}"
        if code.startswith("A"):
            a_lines.append(line)
        elif code.startswith("B"):
            b_lines.append(line)
        elif code.startswith("C"):
            c_lines.append(line)

    text = "📋 *Dramalar ro'yxati:*\n\n"
    text += "\n".join(a_lines) + "\n\n"
    text += "\n".join(b_lines) + "\n\n"
    text += "\n".join(c_lines)
    text += "\n\n✏️ Kodni yuboring va dramani oling!\n_Alohida qismlar uchun: A0011, B0011 ..._"

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def random_drama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Faqat asosiy seriallar (to'plam kodlar: A001, B001 kabi)
    main_codes = [c for c in CODES if len(c) <= 4]
    code = random.choice(main_codes)
    name = CODES[code].replace(" — barcha qismlar", "")

    if code.startswith("A"):
        category = "⚔️ Urush / Jang"
    elif code.startswith("B"):
        category = "💕 Romantik"
    else:
        category = "🏫 Maktab"

    videos = load_videos()
    has_video = "✅ Mavjud" if code in videos else "⏳ Yuklanmoqda"

    await update.message.reply_text(
        f"🎲 *Tasodifiy drama:*\n\n"
        f"🎬 *{name}*\n"
        f"🏷 Kod: `{code}`\n"
        f"📂 Janr: {category}\n"
        f"📹 Holat: {has_video}\n\n"
        f"_Yuqoridagi kodni yuboring va tomosha qiling!_",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def top_drama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    views = load_views()
    if not any(v > 0 for v in views.values()):
        await update.message.reply_text(
            "📊 Hali hech qaysi drama ko'rilmagan.",
            reply_markup=main_keyboard(),
        )
        return

    sorted_dramas = sorted(
        [(code, CODES[code], views.get(code, 0)) for code in CODES],
        key=lambda x: x[2],
        reverse=True,
    )
    lines = ["🔥 *Eng ko'p ko'rilgan dramalar:*\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (code, name, count) in enumerate(sorted_dramas[:5]):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} `{code}` — {name}  _(👁 {count})_")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📩 Shikoyat yoki taklifingiz bo'lsa, adminga yozing:\n\n"
        "👤 @kumushnora",
        reply_markup=main_keyboard(),
    )


async def check_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()

    # Admin pending video uchun kod kutilayotgan bo'lsa
    if is_admin(update.effective_user) and "pending_video" in context.user_data:
        file_id = context.user_data.pop("pending_video")
        if text in CODES:
            await _save_video_with_code(update.message, text, file_id)
        else:
            await update.message.reply_text(
                f"❌ `{text}` kodi topilmadi. Video saqlanmadi.",
                parse_mode="Markdown",
            )
        return

    # Oddiy foydalanuvchi kod tekshiruvi
    if text in CODES:
        await send_drama(update, text)
    else:
        await update.message.reply_text(
            "❌ Kod topilmadi.\nIltimos, to'g'ri kodni yuboring yoki ro'yxatni ko'ring.",
            reply_markup=main_keyboard(),
        )


# ── Kanal post handleri ───────────────────────────────────────────────────────

async def channel_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanaldan kelgan video postlarni ushlaydi va file_id saqlaydi."""
    post = update.channel_post
    if not post or not post.video:
        return

    chat_username = (post.chat.username or "").lower()
    if CHANNEL_USERNAME and chat_username != CHANNEL_USERNAME:
        return

    caption = (post.caption or "").strip().upper()
    if not caption or caption not in CODES:
        return

    file_id = post.video.file_id
    videos = load_videos()
    videos[caption] = file_id
    save_videos(videos)
    logger.info(f"Kanaldan video saqlandi: {caption} → {file_id}")


# ── Admin handlerlari ─────────────────────────────────────────────────────────

def extract_code_from_text(text: str) -> str | None:
    """Matndan kodlardan birini qidiradi (masalan A001, A0011 va h.k.)"""
    upper = text.upper()
    # Avval aniq to'liq so'z sifatida qidirish
    for code in sorted(CODES.keys(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(code)}\b", upper):
            return code
    return None


async def admin_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin video yuborsa yoki forward qilsa → file_id saqlaydi.
    Caption dan kod avtomatik topiladi yoki kod so'raladi.
    """
    if not is_admin(update.effective_user):
        return

    msg = update.message
    file_id = msg.video.file_id
    caption = (msg.caption or "").strip()

    if caption:
        code = extract_code_from_text(caption)
        if code:
            await _save_video_with_code(msg, code, file_id)
        else:
            # Captiondan kod topilmadi — kod so'raymiz
            context.user_data["pending_video"] = file_id
            await msg.reply_text(
                f"📥 Video qabul qilindi!\n\nCaption dan kod topilmadi.\nQaysi kod? (masalan: `A001`)",
                parse_mode="Markdown",
            )
    else:
        # Caption yo'q — kod kutamiz
        context.user_data["pending_video"] = file_id
        codes_list = "\n".join(f"`{c}`" for c in sorted(CODES.keys()))
        await msg.reply_text(
            f"📥 Video qabul qilindi!\n\nQaysi kod? Quyidagilardan birini yuboring:\n{codes_list}",
            parse_mode="Markdown",
        )


async def admin_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin /status buyrug'i — qaysi kodlarda video bor."""
    if not is_admin(update.effective_user):
        return

    videos = load_videos()
    lines = ["📊 *Video holati:*\n"]
    for code in sorted(CODES.keys()):
        icon = "✅" if code in videos else "❌"
        lines.append(f"{icon} `{code}` — {CODES[code]}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Asosiy ────────────────────────────────────────────────────────────────────

def main():
    start_keep_alive()
    application = Application.builder().token(TOKEN).build()

    # Foydalanuvchi handlerlari
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.Regex("^📋 Dramalar ro'yxati$"), dramas_list)
    )
    application.add_handler(
        MessageHandler(filters.Regex("^🎲 Random drama$"), random_drama)
    )
    application.add_handler(
        MessageHandler(filters.Regex("^🔥 Eng ko'p ko'rilgan$"), top_drama)
    )
    application.add_handler(
        MessageHandler(filters.Regex("^📩 Aloqa / Taklif$"), contact)
    )

    # Kanal post handleri
    application.add_handler(
        MessageHandler(filters.ChatType.CHANNEL & filters.VIDEO, channel_video)
    )

    # Admin handlerlari
    application.add_handler(CommandHandler("status", admin_status))
    application.add_handler(MessageHandler(filters.VIDEO, admin_video))

    # Kod tekshirish (oxirgi)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, check_code)
    )

    logger.info("Bot ishga tushmoqda...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
