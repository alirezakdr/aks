# bot.py
# python-telegram-bot==20.x

import os
import json
from typing import List, Dict
from collections import defaultdict
from pathlib import Path
import unicodedata

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# --- تنظیمات ---
TOKEN = "8238881010:AAG5wygcMY9m34ikiZQBBfw8l5_s9_nzoq4"  # NOTE: برای تست؛ بعداً بهتره از ENV بگیری و توکن رو rotate کنی
PRODUCTS_PATH = "products.json"
BASE_DIR = Path(__file__).resolve().parent

# --- ابزارهای کمکی مسیر و یونیکد ---
def normalize_unicode(s: str) -> str:
    # یکپارچه‌سازی ی و ک عربی + NFC
    return unicodedata.normalize("NFC", s.replace("\u064a", "\u06cc").replace("\u0643", "\u06a9"))

def resolve_image_path(image_ref: str):
    """
    عکس را از کنار پروژه به صورت مطلق resolve می‌کند.
    اگر فایلی با نام دقیق نبود، به صورت هوشمند داخل همان فولدر
    دنبال 'Untitled design.*' می‌گردد.
    """
    ref = normalize_unicode((image_ref or "").strip().replace("\\", "/"))
    p = Path(ref)
    if not p.is_absolute():
        p = BASE_DIR / p
    if p.is_file():
        return p
    folder = p.parent
    if folder.is_dir():
        # تلاش برای نام استاندارد
        for ext in ["png","PNG","jpg","JPG","jpeg","JPEG","webp","WEBP"]:
            cand = folder / f"Untitled design.{ext}"
            if cand.is_file():
                return cand
        # هر فایلی که با Untitled design شروع شود
        cands = sorted([c for c in folder.glob("Untitled design*") if c.is_file()])
        if cands:
            return cands[0]
    return None

# --- بارگذاری محصولات ---
def load_products() -> List[Dict]:
    try:
        with open(BASE_DIR / PRODUCTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = []
        for item in data:
            out.append({
                "brand": item.get("brand", "").strip(),
                "name": item.get("name", "").strip(),
                "image": item.get("image", "").strip(),
                "caption": (item.get("caption") or item.get("name") or "").strip()
            })
        return [p for p in out if p["brand"] and p["name"] and p["image"]]
    except Exception as e:
        print(f"Failed to load products: {e}")
        return []

PRODUCTS = load_products()

# --- ساخت منوها ---
def group_by_brand(products: List[Dict]) -> Dict[str, List[Dict]]:
    g = defaultdict(list)
    for p in products:
        g[p["brand"]].append(p)
    return dict(g)

def chunk(items: List, n: int):
    for i in range(0, len(items), n):
        yield items[i:i+n]

def brand_keyboard() -> InlineKeyboardMarkup:
    brands = list(group_by_brand(PRODUCTS).keys())
    rows = []
    for row in chunk(brands, 2):
        rows.append([InlineKeyboardButton(text=b, callback_data=f"brand::{b}") for b in row])
    return InlineKeyboardMarkup(rows)

def products_keyboard(brand: str) -> InlineKeyboardMarkup:
    items = [p["name"] for p in PRODUCTS if p["brand"] == brand]
    rows = []
    for row in chunk(items, 2):
        rows.append([InlineKeyboardButton(text=name, callback_data=f"item::{brand}::{name}") for name in row])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت به برندها", callback_data="back::brands")])
    return InlineKeyboardMarkup(rows)

# --- دستورات ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "سلام! ابتدا **برند** را انتخاب کن ⬇️"
    # همیشه پیام جدید بفرست تا دکمه‌ها پایین چت بمانند
    if update.message:
        await update.message.reply_text(text, reply_markup=brand_keyboard(), parse_mode="Markdown")
    else:
        await update.callback_query.message.reply_text(text, reply_markup=brand_keyboard(), parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "از منوی برندها شروع کن و بعد محصول را انتخاب کن تا عکس ارسال شود.\n/refresh برای بارگذاری مجدد."
    await update.message.reply_text(msg, reply_markup=brand_keyboard())

async def where_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"cwd: {os.getcwd()}\nbase: {BASE_DIR}")

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PRODUCTS
    PRODUCTS = load_products()
    await update.message.reply_text("لیست محصولات بروزرسانی شد ✅", reply_markup=brand_keyboard())

# --- هندلر دکمه‌ها ---
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # انتخاب برند → همیشه پیام جدید با منوی محصولات همان برند
    if data.startswith("brand::"):
        brand = data.split("::", 1)[1]
        await query.message.reply_text(
            f"برند **{brand}** را انتخاب کردی. حالا یکی از محصولات زیر را بزن:",
            reply_markup=products_keyboard(brand),
            parse_mode="Markdown"
        )
        return

    # انتخاب محصول → ارسال عکس + منوی همان برند زیر عکس
    if data.startswith("item::"):
        _, brand, name = data.split("::", 2)
        product = next((p for p in PRODUCTS if p["brand"] == brand and p["name"] == name), None)
        if not product:
            await query.message.reply_text("محصول پیدا نشد. /refresh را بزن.")
            return
        image_ref = product["image"]
        caption = product.get("caption") or product["name"]

        if image_ref.lower().startswith("http://") or image_ref.lower().startswith("https://"):
            await query.message.reply_photo(photo=image_ref, caption=caption, reply_markup=products_keyboard(brand))
        else:
            resolved = resolve_image_path(image_ref)
            if not resolved:
                await query.message.reply_text(
                    f"عکس پیدا نشد. مسیر بررسی‌شده: {(BASE_DIR / image_ref).resolve()}",
                    reply_markup=products_keyboard(brand)
                )
            else:
                with open(resolved, "rb") as f:
                    await query.message.reply_photo(photo=InputFile(f), caption=caption, reply_markup=products_keyboard(brand))
        return

    # بازگشت → همیشه پیام جدید با منوی برندها (نه edit)
    if data == "back::brands":
        await query.message.reply_text("یک برند را انتخاب کن ⬇️", reply_markup=brand_keyboard(), parse_mode="Markdown")
        return

# --- اگر کاربر اسم محصول را تایپ کند ---
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    product = next((p for p in PRODUCTS if p["name"].lower() == text.lower()), None)
    if product:
        image_ref = product["image"]
        caption = product.get("caption") or product["name"]
        brand = product["brand"]

        if image_ref.lower().startswith("http://") or image_ref.lower().startswith("https://"):
            await update.message.reply_photo(photo=image_ref, caption=caption, reply_markup=products_keyboard(brand))
        else:
            resolved = resolve_image_path(image_ref)
            if not resolved:
                await update.message.reply_text(
                    f"عکس پیدا نشد. مسیر بررسی‌شده: {(BASE_DIR / image_ref).resolve()}",
                    reply_markup=products_keyboard(brand)
                )
            else:
                with open(resolved, "rb") as f:
                    await update.message.reply_photo(photo=f, caption=caption, reply_markup=products_keyboard(brand))
        return

    # اگر متن چیز دیگری بود، منوی برندها را بده
    await update.message.reply_text("ابتدا برند را انتخاب کن:", reply_markup=brand_keyboard())

# --- اجرا ---
def build_app():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("where", where_cmd))
    app.add_handler(CommandHandler("refresh", refresh))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app

if __name__ == "__main__":
    app = build_app()
    print("Bot is up. Press Ctrl+C to stop.")
    app.run_polling(close_loop=False)
