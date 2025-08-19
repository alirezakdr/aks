
import os
import json
from typing import List, Dict
from collections import defaultdict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

TOKEN = "8238881010:AAG5wygcMY9m34ikiZQBBfw8l5_s9_nzoq4"  # WARNING: hardcoded for convenience; rotate token & move to env in production
PRODUCTS_PATH = os.getenv("PRODUCTS_JSON", "products.json")

def load_products() -> List[Dict]:
    try:
        with open(PRODUCTS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = []
        for item in data:
            out.append({
                "brand": item.get("brand", "").strip(),
                "name": item.get("name", "").strip(),
                "image": item.get("image", "").strip(),
                "caption": item.get("caption", "").strip() or item.get("name", "").strip()
            })
        # remove incomplete
        return [p for p in out if p["brand"] and p["name"] and p["image"]]
    except Exception as e:
        print(f"Failed to load products: {e}")
        return []

PRODUCTS = load_products()

def group_by_brand(products: List[Dict]) -> Dict[str, List[Dict]]:
    g = defaultdict(list)
    for p in products:
        g[p["brand"]].append(p)
    # keep insertion order where possible
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
    # back button
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت به برندها", callback_data="back::brands")])
    return InlineKeyboardMarkup(rows)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "سلام! ابتدا **برند** را انتخاب کن ⬇️"
    if update.message:
        await update.message.reply_text(text, reply_markup=brand_keyboard(), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=brand_keyboard(), parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "از منوی برندها شروع کن و بعد محصول را انتخاب کن تا عکس ارسال شود.\nدستور مفید: /refresh برای بارگذاری مجدد محصولات."
    await update.message.reply_text(msg, reply_markup=brand_keyboard())

async def refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PRODUCTS
    PRODUCTS = load_products()
    await update.message.reply_text("لیست محصولات بروزرسانی شد ✅", reply_markup=brand_keyboard())

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data.startswith("brand::"):
        brand = data.split("::", 1)[1]
        await query.edit_message_text(f"برند **{brand}** را انتخاب کردی. حالا یکی از محصولات زیر را بزن:", reply_markup=products_keyboard(brand), parse_mode="Markdown")
        return

    if data.startswith("item::"):
        _, brand, name = data.split("::", 2)
        product = next((p for p in PRODUCTS if p["brand"] == brand and p["name"] == name), None)
        if not product:
            await query.edit_message_text("محصول پیدا نشد. /refresh را بزنید.")
            return
        image_ref = product["image"]
        caption = product.get("caption") or product["name"]
        if image_ref.lower().startswith("http://") or image_ref.lower().startswith("https://"):
            await query.message.reply_photo(photo=image_ref, caption=caption)
        else:
            if not os.path.isfile(image_ref):
                await query.message.reply_text(f"عکس پیدا نشد: {image_ref}")
            else:
                with open(image_ref, "rb") as f:
                    await query.message.reply_photo(
    photo=InputFile(f),
    caption=caption,
    reply_markup=products_keyboard(brand)   # منوی محصولات همون برند دوباره زیر عکس
)

        return

    if data == "back::brands":
        await start(update, context)
        return

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # If user types a product name directly (any brand), send its photo
    text = (update.message.text or "").strip()
    product = next((p for p in PRODUCTS if p["name"].lower() == text.lower()), None)
    if product:
        image_ref = product["image"]
        caption = product.get("caption") or product["name"]
        if image_ref.lower().startswith("http://") or image_ref.lower().startswith("https://"):
            await update.message.reply_photo(photo=image_ref, caption=caption)
        else:
            if not os.path.isfile(image_ref):
                await update.message.reply_text(f"عکس پیدا نشد: {image_ref}")
            else:
                with open(image_ref, "rb") as f:
                    await update.message.reply_photo(
    photo=f,
    caption=caption,
    reply_markup=products_keyboard(product["brand"])   # منوی برند هم همراه عکس بیاد
)

        return
    await update.message.reply_text("ابتدا برند را انتخاب کن:", reply_markup=brand_keyboard())

def build_app():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("refresh", refresh))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    return app

if __name__ == "__main__":
    app = build_app()
    print("Bot is up. Press Ctrl+C to stop.")
    app.run_polling(close_loop=False)
