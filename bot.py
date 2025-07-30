#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram Visa Bot — minimal fixes to make the multi-step form not hang.
Python 3.10+, python-telegram-bot v20+ (async API).
"""

import logging
from typing import Dict, Any, Optional, Tuple

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputFile,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

# =========================
# Config (placeholders)
# =========================
BOT_TOKEN = "7826974293:AAFe4aSM8_Zx5gk0azvfLAlv2UQCimLjlPA"
ADMIN_CHAT_ID = 7782365882
ADMIN_USERNAME = "@Kseniia_mln"
PAYPAL_URL = "https://www.paypal.me/emiwayservices/125"
WEBSITE_URL = "http://emiway-visa-ae.tilda.ws/"
PDF_GUIDE_URL = "https://example.com/guide.pdf"  # заглушка

# =========================
# Logging
# =========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
# States (keep names)
# =========================
(
    FORM_NAME,
    FORM_DOB,
    FORM_NATIONALITY,
    FORM_PASSPORT_NUM,
    FORM_PHONE,
    FORM_EMAIL,
    FORM_PASSPORT,
    FORM_PHOTO,
) = range(8)

# A simple in-memory storage for submitted forms (per user)
# user_id -> dict with answers & file_ids
FORMS: Dict[int, Dict[str, Any]] = {}

# =========================
# Static texts (keep wording)
# =========================

START_TEXT = "Welcome! How can we help you today?"

APPLY_TEXT = (
    "Please choose an option below:\n\n"
    "• Check if your nationality is eligible for an e-visa.\n"
    "• Fill the application form to start processing.\n\n"
    "After submitting the form, proceed to payment to complete the request."
)

THANK_YOU_PAYMENT_TEXT = (
    "✅ Thank you! Your form was submitted. To complete the process, please proceed with payment. "
    "After payment, you will receive a PDF instruction and our team will contact you."
)

REQUIREMENTS_TEXT = (
    "📝 Visa Requirements:\n"
    "• Valid passport\n"
    "• Recent digital photo\n"
    "• Travel details\n\n"
    "Please note: processing times and additional documents may vary."
)

FAQ_TEXT = (
    "❓ FAQ:\n"
    "• How long does it take? — Usually 3–10 business days.\n"
    "• Is the fee refundable? — Payments are processed after document check.\n"
    "• How will I get updates? — We will contact you via Telegram or email."
)

ELIGIBLE_LIST = (
    # Используем список из ТЗ (как есть)
    "Andorra, Austria, Bahrain, Belgium, Bulgaria, Cambodia, China, Croatia, Cyprus, "
    "Czech Republic, Denmark, Estonia, Finland, France, Germany, Greece, Hungary, Iceland, "
    "India, Indonesia, Iran, Ireland, Italy, Japan, North Korea, Kuwait, Latvia, "
    "Liechtenstein, Lithuania, Luxembourg, Malaysia, Malta, Mexico, Monaco, Myanmar, "
    "Netherlands, North Macedonia, Norway, Oman, Philippines, Poland, Portugal, Romania, "
    "San Marino, Saudi Arabia, Serbia, Singapore, Slovakia, Slovenia, Spain, Sweden, "
    "Switzerland, Taiwan, Turkey, Vatican, Vietnam."
)

# Popular subset for inline nationality quick-choose (we also accept free text!)
POPULAR_NATIONALITIES = [
    "India",
    "China",
    "Germany",
    "France",
    "Italy",
    "Spain",
]


# =========================
# Keyboards
# =========================

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛂 Apply for Visa", callback_data="apply")],
        [InlineKeyboardButton("📝 Visa Requirements", callback_data="requirements")],
        [InlineKeyboardButton("❓ FAQ", callback_data="faq")],
        [InlineKeyboardButton("🌐 Go to Website", url=WEBSITE_URL)],
        [InlineKeyboardButton("📞 Contact Specialist", url="https://t.me/Kseniia_mln")],
    ])


def apply_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇷🇺 Eligible Nationalities", callback_data="eligible")],
        [InlineKeyboardButton("📋 Fill the Form", callback_data="fill_form")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")],
    ])


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")]])


def payment_kb() -> InlineKeyboardMarkup:
    # FIX-PAID: добавили кнопку "✅ I paid" и оставили только две кнопки в блоке оплаты
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pay $125 Now and get instruction for Russian travel", url=PAYPAL_URL)],
        [InlineKeyboardButton("✅ I paid", callback_data="user_paid")],  # FIX-PAID
    ])


def pdf_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Download PDF Guide", url=PDF_GUIDE_URL)],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_main")],
    ])


def nationality_kb() -> InlineKeyboardMarkup:
    # Popular quick-choose buttons + hint to type your own
    rows = []
    for nat in POPULAR_NATIONALITIES:
        rows.append([InlineKeyboardButton(nat, callback_data=f"set_nat:{nat}")])
    rows.append([InlineKeyboardButton("Other nationality? Type it in chat…", callback_data="nat_hint")])
    return InlineKeyboardMarkup(rows)


# =========================
# Helper functions
# =========================

def get_user_form(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Dict[str, Any]:
    # Use both user_data and our global FORMS to be safe
    if "form" not in context.user_data:
        context.user_data["form"] = {}
    FORMS.setdefault(user_id, context.user_data["form"])
    return context.user_data["form"]


async def safe_edit_or_send(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str,
                            reply_markup: Optional[InlineKeyboardMarkup] = None) -> None:
    """Edit message if this was a callback; otherwise send a new one."""
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup)
        except Exception:
            await update.callback_query.message.reply_text(text=text, reply_markup=reply_markup)
    else:
        await update.effective_chat.send_message(text=text, reply_markup=reply_markup)


# =========================
# Command handlers
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(START_TEXT, reply_markup=main_menu_kb())


# Admin command to mark a user as paid
async def mark_paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("Only admin can use this command.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /mark_paid <user_id>")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("User ID must be an integer.")
        return

    form = FORMS.get(target_user_id)
    if not form:
        await update.message.reply_text("No form data found for this user.")
        return

    # Send admin a summary with files
    summary = (
        "✅ PAYMENT CONFIRMED (manual)\n\n"
        f"User ID: {target_user_id}\n"
        f"Full name: {form.get('full_name')}\n"
        f"Date of birth: {form.get('dob')}\n"
        f"Nationality: {form.get('nationality')}\n"
        f"Passport number: {form.get('passport_number')}\n"
        f"Phone: {form.get('phone')}\n"
        f"Email: {form.get('email')}\n"
    )
    await update.message.reply_text(summary)

    # Attach files to admin
    if form.get("passport_file_id"):
        try:
            await context.bot.send_document(
                chat_id=ADMIN_CHAT_ID, document=form["passport_file_id"], caption="Passport scan"
            )
        except Exception:
            # If the stored file_id was photo, try send_photo
            try:
                await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=form["passport_file_id"], caption="Passport scan")
            except Exception as e:
                logger.exception("Failed to send passport file to admin: %s", e)

    if form.get("photo_file_id"):
        try:
            await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=form["photo_file_id"], caption="Digital photo")
        except Exception:
            # If stored as document
            try:
                await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=form["photo_file_id"], caption="Digital photo")
            except Exception as e:
                logger.exception("Failed to send photo file to admin: %s", e)

    # Notify user
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text="✅ Your application has been received. Our specialist will contact you shortly. PDF guide is attached below.",
            reply_markup=pdf_kb(),
        )
    except Exception as e:
        await update.message.reply_text(f"Failed to notify the user: {e}")

    await update.message.reply_text("Done. User has been notified and files were sent to admin.")


# =========================
# Callback navigation
# =========================

async def on_menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # FIX: always answer callback to prevent 'loading' hang

    data = query.data
    if data == "apply":
        await query.edit_message_text(APPLY_TEXT, reply_markup=apply_menu_kb())
    elif data == "requirements":
        await query.edit_message_text(REQUIREMENTS_TEXT, reply_markup=back_to_main_kb())
    elif data == "faq":
        await query.edit_message_text(FAQ_TEXT, reply_markup=back_to_main_kb())
    elif data == "back_main":
        await query.edit_message_text(START_TEXT, reply_markup=main_menu_kb())
    elif data == "eligible":
        text = "🇷🇺 Eligible Nationalities:\n" + ELIGIBLE_LIST
        await query.edit_message_text(text, reply_markup=apply_menu_kb())
    elif data == "nat_hint":
        # small hint
        await query.answer("Please type your nationality in chat.", show_alert=False)
    else:
        await query.answer("Unknown action", show_alert=False)


# =========================
# Conversation: Fill the Form
# =========================

# Entry point — from inline button "📋 Fill the Form"
async def form_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()  # FIX: ensure callback is answered to avoid hang
    # reset form storage
    get_user_form(context, update.effective_user.id).clear()
    await query.edit_message_text("1/8. Please enter your Full name:")
    return FORM_NAME  # FIX: explicit return of next state


# 1) Full name
async def form_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    form = get_user_form(context, update.effective_user.id)
    form["full_name"] = update.message.text.strip()
    await update.message.reply_text("2/8. Please enter your Date of birth (e.g., 1990-12-31):")
    return FORM_DOB  # FIX: return correct state


# 2) Date of birth
async def form_dob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    form = get_user_form(context, update.effective_user.id)
    form["dob"] = update.message.text.strip()
    await update.message.reply_text(
        "3/8. Nationality: choose from buttons below or type your nationality.",
        reply_markup=nationality_kb(),
    )
    return FORM_NATIONALITY  # FIX: return correct state


# 3) Nationality — via text
async def form_nationality_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # FIX: Accept text input for nationality in this state
    form = get_user_form(context, update.effective_user.id)
    form["nationality"] = update.message.text.strip()
    await update.message.reply_text("4/8. Please enter your Passport number:")
    return FORM_PASSPORT_NUM  # FIX: go to next state


# 3) Nationality — via inline button
async def form_nationality_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()  # FIX: answer callback
    _, nat = query.data.split("set_nat:", maxsplit=1)  # FIX: pattern-based parse
    form = get_user_form(context, update.effective_user.id)
    form["nationality"] = nat
    await query.edit_message_text("4/8. Please enter your Passport number:")
    return FORM_PASSPORT_NUM  # FIX: go to next state


# 4) Passport number
async def form_passport_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    form = get_user_form(context, update.effective_user.id)
    form["passport_number"] = update.message.text.strip()
    await update.message.reply_text("5/8. Please enter your Phone number (with country code):")
    return FORM_PHONE


# 5) Phone number
async def form_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    form = get_user_form(context, update.effective_user.id)
    form["phone"] = update.message.text.strip()
    await update.message.reply_text("6/8. Please enter your Email address:")
    return FORM_EMAIL


# 6) Email
async def form_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    form = get_user_form(context, update.effective_user.id)
    form["email"] = update.message.text.strip()
    await update.message.reply_text(
        "7/8. Upload passport scan (as document or photo)."
    )
    return FORM_PASSPORT


# 7) Upload passport (accept documents or photos)
async def form_passport_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    form = get_user_form(context, update.effective_user.id)

    file_id = None
    if update.message.document:
        file_id = update.message.document.file_id
    elif update.message.photo:
        # largest size
        file_id = update.message.photo[-1].file_id

    if not file_id:
        await update.message.reply_text("Please upload a document or a photo of your passport scan.")
        return FORM_PASSPORT

    form["passport_file_id"] = file_id
    await update.message.reply_text("8/8. Upload your digital photo (as document or photo).")
    return FORM_PHOTO


# 8) Upload photo (accept documents or photos)
async def form_photo_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    form = get_user_form(context, update.effective_user.id)

    file_id = None
    if update.message.document:
        file_id = update.message.document.file_id
    elif update.message.photo:
        file_id = update.message.photo[-1].file_id

    if not file_id:
        await update.message.reply_text("Please upload a document or a photo.")
        return FORM_PHOTO

    form["photo_file_id"] = file_id

    # Show payment block
    await update.message.reply_text(THANK_YOU_PAYMENT_TEXT, reply_markup=payment_kb())

    # End conversation here; admin will mark paid manually
    return ConversationHandler.END


# Fallback / cancel (back to main menu)
async def form_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await safe_edit_or_send(update, context, "Cancelled. Back to main menu.", reply_markup=main_menu_kb())
    return ConversationHandler.END


# =========================
# Payment flow handlers (new)
# =========================

async def user_paid_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User presses '✅ I paid' — notify admin with inline 'Mark as paid' button."""
    query = update.callback_query  # FIX-PAID
    try:
        await query.answer()  # FIX-PAID
        user = update.effective_user
        user_id = user.id
        form = FORMS.get(user_id, {})  # FIX-PAID

        # Short ack for user
        await query.message.reply_text("Thanks! Our specialist will review the payment shortly.")  # FIX-PAID

        # Compose admin pending message
        summary = (
            f"⏳ Payment pending\n"
            f"User: {user.full_name} (ID: {user_id})\n\n"
            f"Full name: {form.get('full_name')}\n"
            f"Date of birth: {form.get('dob')}\n"
            f"Nationality: {form.get('nationality')}\n"
            f"Passport number: {form.get('passport_number')}\n"
            f"Phone: {form.get('phone')}\n"
            f"Email: {form.get('email')}\n"
        )  # FIX-PAID

        kb = InlineKeyboardMarkup([  # FIX-PAID
            [InlineKeyboardButton("Mark as paid", callback_data=f"admin_mark_paid:{user_id}")]
        ])
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=summary, reply_markup=kb)  # FIX-PAID

    except Exception as e:
        logger.exception("user_paid_clicked failed: %s", e)  # FIX-PAID


async def admin_mark_paid_clicked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin presses 'Mark as paid' — send summary+files to admin and final message to user."""
    query = update.callback_query  # FIX-PAID
    try:
        await query.answer()  # FIX-PAID
        actor_id = update.effective_user.id
        if actor_id != ADMIN_CHAT_ID:
            await query.answer("Only admin can confirm payment.", show_alert=True)  # FIX-PAID
            return

        data = query.data
        _, user_id_str = data.split("admin_mark_paid:", maxsplit=1)  # FIX-PAID
        target_user_id = int(user_id_str)

        form = FORMS.get(target_user_id)
        if not form:
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=f"No form data found for user {target_user_id}.")  # FIX-PAID
            return

        # Send admin a detailed summary
        summary = (
            "✅ PAYMENT CONFIRMED\n\n"
            f"User ID: {target_user_id}\n"
            f"Full name: {form.get('full_name')}\n"
            f"Date of birth: {form.get('dob')}\n"
            f"Nationality: {form.get('nationality')}\n"
            f"Passport number: {form.get('passport_number')}\n"
            f"Phone: {form.get('phone')}\n"
            f"Email: {form.get('email')}\n"
        )  # FIX-PAID
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=summary)  # FIX-PAID

        # Attach files to admin
        if form.get("passport_file_id"):  # FIX-PAID
            try:
                await context.bot.send_document(
                    chat_id=ADMIN_CHAT_ID, document=form["passport_file_id"], caption="Passport scan"
                )
            except Exception:
                try:
                    await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=form["passport_file_id"], caption="Passport scan")
                except Exception as e:
                    logger.exception("Failed to send passport file to admin: %s", e)

        if form.get("photo_file_id"):  # FIX-PAID
            try:
                await context.bot.send_photo(chat_id=ADMIN_CHAT_ID, photo=form["photo_file_id"], caption="Digital photo")
            except Exception:
                try:
                    await context.bot.send_document(chat_id=ADMIN_CHAT_ID, document=form["photo_file_id"], caption="Digital photo")
                except Exception as e:
                    logger.exception("Failed to send photo file to admin: %s", e)

        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text="✅ Payment confirmed")  # FIX-PAID

        # Notify user
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="✅ Your application has been received. Our specialist will contact you shortly. PDF guide is attached below.",
                reply_markup=pdf_kb(),
            )  # FIX-PAID
        except Exception as e:
            logger.exception("Failed to notify user after admin confirmation: %s", e)  # FIX-PAID

    except Exception as e:
        logger.exception("admin_mark_paid_clicked failed: %s", e)  # FIX-PAID


# =========================
# Error handler
# =========================
async def error_handler(update: Optional[Update], context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    # Do not swallow exceptions silently; notify admin for visibility
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"⚠️ Error: {context.error}",
        )
    except Exception:
        pass


# =========================
# Application setup
# =========================

def build_application():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # /start and admin command
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mark_paid", mark_paid))

    # General menu callbacks
    app.add_handler(CallbackQueryHandler(on_menu_click, pattern="^(apply|requirements|faq|back_main|eligible|nat_hint)$"))

    # Conversation for Fill the Form
    form_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(form_entry, pattern="^fill_form$"),  # FIX: start via CallbackQuery with pattern
        ],
        states={
            FORM_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_name),  # FIX: explicit text filter
            ],
            FORM_DOB: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_dob),
            ],
            FORM_NATIONALITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_nationality_text),  # FIX: accept text on this step
                CallbackQueryHandler(form_nationality_button, pattern="^set_nat:"),       # FIX: and inline via pattern
            ],
            FORM_PASSPORT_NUM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_passport_number),
            ],
            FORM_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_phone),
            ],
            FORM_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, form_email),
            ],
            FORM_PASSPORT: [
                MessageHandler(
                    (filters.Document.ALL | filters.PHOTO), form_passport_file
                ),  # FIX: accept documents and photos
            ],
            FORM_PHOTO: [
                MessageHandler(
                    (filters.Document.ALL | filters.PHOTO), form_photo_file
                ),  # FIX: accept documents and photos
            ],
        },
        fallbacks=[
            CallbackQueryHandler(form_cancel, pattern="^back_main$"),
            CommandHandler("cancel", form_cancel),
        ],
        allow_reentry=True,
    )
    app.add_handler(form_conv)

    # FIX-PAID: обработчики оплаты должны идти до catch-all, чтобы не перехватывались on_menu_click
    app.add_handler(CallbackQueryHandler(user_paid_clicked, pattern="^user_paid$"))  # FIX-PAID
    app.add_handler(CallbackQueryHandler(admin_mark_paid_clicked, pattern=r"^admin_mark_paid:\d+$"))  # FIX-PAID

    # Also need to handle Apply/Eligible buttons outside conversation
    app.add_handler(CallbackQueryHandler(on_menu_click))

    app.add_error_handler(error_handler)
    return app


def main():
    app = build_application()
    logger.info("Bot started")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()