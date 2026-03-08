import logging
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from app.config import get_settings
from app.database import get_db_context
from app.services.user import UserService
from app.services.documents import DocumentService
from app.services.shopping import ShoppingService
from app.services.memory import MemoryService

logger = logging.getLogger(__name__)


async def get_user(update: Update):
    """Get or create user from Telegram update."""
    async with get_db_context() as db:
        user_service = UserService(db)
        return await user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name
        )


# Command Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = await get_user(update)
    await update.message.reply_text(
        f"Hello {user['first_name'] or 'there'}! I'm your External Brain.\n\n"
        "Commands:\n"
        "/photo - Send a German document photo for OCR & translation\n"
        "/search <query> - Search your documents & memories\n"
        "/remember <text> - Store a memory\n"
        "/add <item> - Add item to shopping list\n"
        "/list - Show shopping list\n"
        "/done - Close shopping session\n"
        "/help - Show this message"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "External Brain Commands:\n\n"
        "Document Filing:\n"
        "  Send any photo of a German document\n"
        "  I'll OCR, translate, and store it\n\n"
        "Shopping List:\n"
        "  /add <item> - Add item (e.g., /add 2 kg apples)\n"
        "  /list - Show current list\n"
        "  /check <item> - Mark item done\n"
        "  /clear - Remove checked items\n"
        "  /done - Close shopping session\n\n"
        "Memory & Search:\n"
        "  /remember <text> - Store a memory\n"
        "  /search <query> - Search everything\n"
        "  /ask <question> - Ask about your data"
    )


async def add_item_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add command for shopping list."""
    user = await get_user(update)

    if not context.args:
        await update.message.reply_text("Usage: /add <item> [quantity] [unit]\nExample: /add milk 2 liters")
        return

    item_text = " ".join(context.args)

    # Parse quantity if provided
    parts = item_text.split()
    quantity = 1
    unit = None
    item_name = item_text

    if len(parts) >= 2 and parts[0].isdigit():
        quantity = int(parts[0])
        if len(parts) >= 3 and parts[1] in ["kg", "g", "l", "ml", "pcs", "units", "liters", "bottles"]:
            unit = parts[1]
            item_name = " ".join(parts[2:])
        else:
            item_name = " ".join(parts[1:])

    async with get_db_context() as db:
        shopping_service = ShoppingService(db)
        item = await shopping_service.add_item(
            user_id=user["id"],
            item_name=item_name,
            quantity=quantity,
            unit=unit
        )

    qty_str = f"{quantity}" + (f" {unit}" if unit else "")
    await update.message.reply_text(f"Added: {qty_str} {item_name}")


async def list_items_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list command."""
    user = await get_user(update)

    async with get_db_context() as db:
        shopping_service = ShoppingService(db)
        result = await shopping_service.list_items(user["id"])

    if not result["items"]:
        await update.message.reply_text("Your shopping list is empty.\nUse /add <item> to add items.")
        return

    lines = ["Shopping List:"]
    for item in result["items"]:
        check = "" if item["is_checked"] else ""
        qty = f"{item['quantity']}"
        if item["unit"]:
            qty += f" {item['unit']}"
        lines.append(f"{check} {qty} {item['item_name']}")

    lines.append(f"\nTotal: {result['total_items']} items ({result['checked_items']} done)")
    await update.message.reply_text("\n".join(lines))


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /done command to close shopping session."""
    user = await get_user(update)

    async with get_db_context() as db:
        shopping_service = ShoppingService(db)
        result = await shopping_service.close_list(user["id"])

    if result:
        await update.message.reply_text(
            f"Shopping session closed.\n"
            f"Started: {result['created_at'].strftime('%Y-%m-%d %H:%M')}\n"
            f"Closed: {result['closed_at'].strftime('%Y-%m-%d %H:%M')}"
        )
    else:
        await update.message.reply_text("No active shopping session to close.")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /clear command to remove checked items."""
    user = await get_user(update)

    async with get_db_context() as db:
        shopping_service = ShoppingService(db)
        count = await shopping_service.clear_checked(user["id"])

    await update.message.reply_text(f"Removed {count} checked items.")


async def remember_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remember command to store a memory."""
    user = await get_user(update)

    if not context.args:
        await update.message.reply_text("Usage: /remember <text to remember>")
        return

    content = " ".join(context.args)

    async with get_db_context() as db:
        memory_service = MemoryService(db)
        result = await memory_service.store_memory(
            user_id=user["id"],
            content=content,
            source="telegram"
        )

    await update.message.reply_text(f"Stored in memory.\nID: {result['id'][:8]}...")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command for associative retrieval."""
    user = await get_user(update)

    if not context.args:
        await update.message.reply_text("Usage: /search <query>")
        return

    query = " ".join(context.args)

    async with get_db_context() as db:
        memory_service = MemoryService(db)
        result = await memory_service.associative_search(
            user_id=user["id"],
            query=query,
            limit=5
        )

    if not result["results"]:
        await update.message.reply_text("No matching results found.")
        return

    lines = [f"Search: {query}\n"]

    for i, item in enumerate(result["results"], 1):
        source = "" if item["source_type"] == "document" else ""
        similarity = f"{item['similarity']:.0%}"
        content = item["content"][:100] + "..." if len(item["content"]) > 100 else item["content"]
        lines.append(f"{i}. {source} [{similarity}] {content}")

    if result["answer"]:
        lines.append(f"\n Answer:\n{result['answer']}")

    await update.message.reply_text("\n".join(lines))


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ask command - same as search but focused on answer."""
    await search_command(update, context)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages for OCR."""
    user = await get_user(update)

    await update.message.reply_text("Processing document...")

    # Get largest photo
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = await file.download_as_bytearray()

    async with get_db_context() as db:
        doc_service = DocumentService(db)
        result = await doc_service.process_document(
            user_id=user["id"],
            image_bytes=bytes(image_bytes),
            filename=f"telegram_{photo.file_id}.jpg"
        )

    response = (
        f" Document Processed\n\n"
        f"Type: {result['document_type']}\n\n"
        f"Summary: {result['summary']}\n\n"
        f"Original (German):\n{result['original_text'][:500]}{'...' if len(result['original_text']) > 500 else ''}\n\n"
        f"Translation (English):\n{result['translated_text'][:500]}{'...' if len(result['translated_text']) > 500 else ''}"
    )

    await update.message.reply_text(response)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages - treat as search query."""
    user = await get_user(update)
    query = update.message.text

    async with get_db_context() as db:
        memory_service = MemoryService(db)
        result = await memory_service.associative_search(
            user_id=user["id"],
            query=query,
            limit=3
        )

    if result["answer"]:
        await update.message.reply_text(result["answer"])
    elif result["results"]:
        content = result["results"][0]["content"]
        await update.message.reply_text(f"Best match:\n{content[:500]}")
    else:
        await update.message.reply_text(
            "I don't have information about that yet.\n"
            "Use /remember to store knowledge or send a document photo."
        )


def create_bot_application() -> Application:
    """Create and configure the Telegram bot application."""
    settings = get_settings()
    application = Application.builder().token(settings.telegram_bot_token).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_item_command))
    application.add_handler(CommandHandler("list", list_items_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("remember", remember_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return application
