"""Telegram entry point: share a reel to the bot, get it back as something useful."""
import asyncio
import html
import os
import shutil
from datetime import date, datetime, time, timedelta
from pathlib import Path

import env  # noqa: F401  (loads .env)

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update  # noqa: E402
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,  # noqa: E402
                          ContextTypes, MessageHandler, filters)

import library  # noqa: E402
import pipeline  # noqa: E402
import vault  # noqa: E402

OWNER = os.getenv("OWNER_CHAT_ID", "")
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "5"))
KIND_LABEL = {"visual": "Referencia visual", "knowledge": "Para aprender",
              "place": "Lugar", "other": "Guardado"}


def card(item, signals):
    lines = [f"{KIND_LABEL[item['kind']]} · {item['title']}", "", item["summary"]]
    if item["kind"] == "visual" and item["what_stands_out"]:
        lines += ["", f"Qué destaca: {item['what_stands_out']}",
                  f"Qué te robas: {item['what_to_steal']}"]
    elif item["key_points"]:
        lines += [""] + [f"• {p}" for p in item["key_points"]]
    if item["kind"] == "place" and item["place_name"]:
        q = f"{item['place_name']} {item['place_city']}".strip().replace(" ", "+")
        lines += ["", f"Mapa: https://www.google.com/maps/search/?api=1&query={q}"]
    if item["action"]:
        lines += ["", f"Haz esto: {item['action']}"]
    if signals:
        lines += ["", "Tu patrón:"] + [f"→ {s}" for s in signals]
    text = html.escape("\n".join(lines))
    return text.replace(html.escape(lines[0]), f"<b>{html.escape(lines[0])}</b>", 1)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Mándame (compártele) un reel de Instagram. Lo veo, lo entiendo y te digo qué te llevas.\n"
        "Con el tiempo te muestro tu gusto: /gusto")


async def whoami(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Tu chat_id: {update.effective_chat.id}")


async def gusto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    p = library.profile(update.effective_chat.id)
    if not p["total"]:
        await update.message.reply_text("Aún no me has mandado reels.")
        return
    fmt = lambda pairs: "\n".join(f"• {t} ×{n}" + ("  ← patrón" if n >= 3 else "") for t, n in pairs[:8]) or "—"
    await update.message.reply_text(
        f"Has guardado {p['total']}.\n\nTu estilo visual:\n{fmt(p['styles'])}\n\n"
        f"Lo que estás aprendiendo:\n{fmt(p['themes'])}")


async def preguntar(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    question = " ".join(ctx.args)
    saved = [e for e in library.entries(update.effective_chat.id) if not e.get("seed")]
    if not question or not saved:
        await update.message.reply_text("Uso: /preguntar ¿cuál era el truco de TDAH que guardé?")
        return
    answer = await asyncio.to_thread(pipeline.ask, question, saved)
    await update.message.reply_text(answer, disable_web_page_preview=True)


async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id
    url = pipeline.clean_url(update.message.text or update.message.caption or "")
    if not url:
        await update.message.reply_text("Mándame el link de un reel de Instagram.")
        return
    is_owner = str(chat) == OWNER
    if not is_owner and library.count_today(chat) >= DAILY_LIMIT:
        await update.message.reply_text(f"Llegaste al límite de {DAILY_LIMIT} reels por hoy.")
        return

    status = await update.message.reply_text("Viendo el reel…")
    t0 = datetime.now()
    try:
        item = await asyncio.to_thread(pipeline.process, url, library.vocab(chat))
    except Exception as e:
        await status.edit_text(f"No pude procesarlo: {e}")
        return

    entry = {k: item[k] for k in ("url", "kind", "title", "summary", "key_points", "action",
                                   "what_stands_out", "what_to_steal", "style_tags", "themes",
                                   "place_name", "place_city")}
    entry.update(date=date.today().isoformat(), uploader=item["meta"].get("uploader"))
    library.add(chat, entry)
    signals = library.signals(chat, item)

    if is_owner:
        try:
            if item["kind"] == "visual":
                vault.write_visual(item, signals)
            else:
                vault.write_knowledge(item, signals)
            vault.write_profile(library.profile(chat))
        except Exception as e:
            print("vault write failed:", e)

    secs = (datetime.now() - t0).seconds
    buttons = None
    if item["action"]:
        ctx.bot_data[f"act-{status.message_id}"] = item["action"]
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton(
            "Recuérdamelo mañana 9:00", callback_data=f"remind:{status.message_id}")]])
    await status.edit_text(card(item, signals) + f"\n\n<i>{secs}s</i>", parse_mode="HTML",
                           reply_markup=buttons, disable_web_page_preview=True)
    shutil.rmtree(item["workdir"], ignore_errors=True)


async def on_remind(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    action = ctx.bot_data.get(f"act-{q.data.split(':')[1]}")
    await q.answer()
    if not action:
        return
    when = datetime.combine(date.today() + timedelta(days=1), time(9, 0)).astimezone()
    ctx.job_queue.run_once(lambda c: c.bot.send_message(q.message.chat.id, f"Recordatorio: {action}"),
                           when=when)
    await q.edit_message_reply_markup(None)
    await q.message.reply_text("Listo, mañana a las 9:00 te lo recuerdo.")


def main():
    app = Application.builder().token(os.environ["TELEGRAM_TOKEN"]).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("soyyo", whoami))
    app.add_handler(CommandHandler("gusto", gusto))
    app.add_handler(CommandHandler("preguntar", preguntar))
    app.add_handler(CallbackQueryHandler(on_remind, pattern="^remind:"))
    app.add_handler(MessageHandler(filters.TEXT | filters.CAPTION, on_message))
    app.run_polling()


if __name__ == "__main__":
    main()
