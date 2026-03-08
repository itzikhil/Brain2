import logging
import traceback
from datetime import datetime
from telegram import Update, Bot
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

# Cache settings
_settings = None


def get_cached_settings():
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings


async def log_to_channel(bot: Bot, message: str, level: str = "info"):
    """
    Send a log message to the private Telegram channel.

    Args:
        bot: The Telegram bot instance
        message: The message to log
        level: Log level (info, success, warning, error)
    """
    settings = get_cached_settings()

    if not settings.log_channel_id:
        logger.info(f"[NO_CHANNEL] {message}")
        return

    # Add emoji based on level
    icons = {
        "info": "ℹ️",
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
        "pending": "⏳",
        "document": "📄",
        "photo": "📷",
        "search": "🔍",
        "memory": "🧠",
    }
    icon = icons.get(level, "📌")
    timestamp = datetime.now().strftime("%H:%M:%S")

    formatted_message = f"{icon} `{timestamp}`\n{message}"

    try:
        await bot.send_message(
            chat_id=settings.log_channel_id,
            text=formatted_message,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Failed to send to log channel: {e}")


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

    await log_to_channel(
        context.bot,
        f"👤 *New /start*\nUser: `{user['first_name']}` (@{user.get('username', 'N/A')})\nID: `{user['telegram_id']}`",
        "info"
    )

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

    try:
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

        await log_to_channel(
            context.bot,
            f"🛒 *Shopping Item Added*\nUser: `{user['id']}`\nItem: {qty_str} {item_name}",
            "success"
        )
    except Exception as e:
        await log_to_channel(
            context.bot,
            f"*Shopping Add Error*\nUser: `{user['id']}`\nError: `{str(e)[:200]}`",
            "error"
        )
        await update.message.reply_text("Error adding item. Please try again.")


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
        check = "✓" if item["is_checked"] else "○"
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

    try:
        await log_to_channel(
            context.bot,
            f"🧠 *Storing Memory*\nUser: `{user['id']}`\nContent: {content[:100]}...",
            "pending"
        )

        async with get_db_context() as db:
            memory_service = MemoryService(db)
            result = await memory_service.store_memory(
                user_id=user["id"],
                content=content,
                source="telegram"
            )

        await update.message.reply_text(f"Stored in memory.\nID: {result['id'][:8]}...")

        await log_to_channel(
            context.bot,
            f"🧠 *Memory Stored*\nUser: `{user['id']}`\nID: `{result['id'][:8]}`\nVector: 3072d ✓",
            "success"
        )
    except Exception as e:
        error_msg = str(e)[:200]
        await log_to_channel(
            context.bot,
            f"*Memory Store Error*\nUser: `{user['id']}`\nError: `{error_msg}`\n\n```{traceback.format_exc()[:500]}```",
            "error"
        )
        await update.message.reply_text("Error storing memory. Please try again.")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command for associative retrieval."""
    user = await get_user(update)

    if not context.args:
        await update.message.reply_text("Usage: /search <query>")
        return

    query = " ".join(context.args)

    try:
        await log_to_channel(
            context.bot,
            f"🔍 *Search Query*\nUser: `{user['id']}`\nQuery: {query[:100]}",
            "search"
        )

        async with get_db_context() as db:
            memory_service = MemoryService(db)
            result = await memory_service.associative_search(
                user_id=user["id"],
                query=query,
                limit=5
            )

        if not result["results"]:
            await update.message.reply_text("No matching results found.")
            await log_to_channel(context.bot, f"🔍 Search complete: 0 results", "info")
            return

        lines = [f"Search: {query}\n"]

        for i, item in enumerate(result["results"], 1):
            source = "📄" if item["source_type"] == "document" else "🧠"
            similarity = f"{item['similarity']:.0%}"
            content = item["content"][:100] + "..." if len(item["content"]) > 100 else item["content"]
            lines.append(f"{i}. {source} [{similarity}] {content}")

        if result["answer"]:
            lines.append(f"\n💡 Answer:\n{result['answer']}")

        await update.message.reply_text("\n".join(lines))

        await log_to_channel(
            context.bot,
            f"🔍 *Search Complete*\nResults: {len(result['results'])}\nTop similarity: {result['results'][0]['similarity']:.0%}",
            "success"
        )
    except Exception as e:
        await log_to_channel(
            context.bot,
            f"*Search Error*\nUser: `{user['id']}`\nQuery: {query[:50]}\nError: `{str(e)[:200]}`",
            "error"
        )
        await update.message.reply_text("Error performing search. Please try again.")


async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ask command - same as search but focused on answer."""
    await search_command(update, context)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages for OCR."""
    user = await get_user(update)

    await log_to_channel(
        context.bot,
        f"📷 *Photo Received*\nUser: `{user['id']}` (@{update.effective_user.username or 'N/A'})\nProcessing...",
        "pending"
    )

    await update.message.reply_text("Processing document...")

    # Get largest photo
    photo = update.message.photo[-1]

    try:
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        await log_to_channel(
            context.bot,
            f"📷 *Photo Downloaded*\nSize: {len(image_bytes)} bytes\nStarting OCR...",
            "info"
        )

        async with get_db_context() as db:
            doc_service = DocumentService(db)
            result = await doc_service.process_document(
                user_id=user["id"],
                image_bytes=bytes(image_bytes),
                filename=f"telegram_{photo.file_id}.jpg"
            )

        response = (
            f"Document Processed\n\n"
            f"Type: {result['document_type']}\n\n"
            f"Summary: {result['summary']}\n\n"
            f"Original (German):\n{result['original_text'][:500]}{'...' if len(result['original_text']) > 500 else ''}\n\n"
            f"Translation (English):\n{result['translated_text'][:500]}{'...' if len(result['translated_text']) > 500 else ''}"
        )
        await update.message.reply_text(response)

        await log_to_channel(
            context.bot,
            f"📷 *Photo Processed Successfully*\nUser: `{user['id']}`\nType: {result['document_type']}\nDoc ID: `{result['id'][:8]}`\nVector: 3072d ✓\n\nSummary: {result['summary'][:200]}",
            "success"
        )

    except Exception as e:
        error_msg = str(e)[:300]
        logger.error(f"Photo processing error: {e}")

        await log_to_channel(
            context.bot,
            f"*Photo Processing FAILED*\nUser: `{user['id']}`\nError: `{error_msg}`\n\n```{traceback.format_exc()[:500]}```",
            "error"
        )

        await update.message.reply_text(f"Error processing image: {str(e)[:100]}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document messages (PDFs, images sent as files)."""
    user = await get_user(update)
    document = update.message.document

    # Check file type
    mime_type = document.mime_type or ""
    filename = document.file_name or "document"

    await log_to_channel(
        context.bot,
        f"📄 *Document Received*\nUser: `{user['id']}` (@{update.effective_user.username or 'N/A'})\nFile: `{filename}`\nMIME: `{mime_type}`\nSize: {document.file_size} bytes",
        "pending"
    )

    supported_types = ["application/pdf", "image/jpeg", "image/png", "image/webp"]
    if not any(t in mime_type for t in ["pdf", "image"]):
        await log_to_channel(
            context.bot,
            f"📄 *Unsupported File Type*\nFile: `{filename}`\nMIME: `{mime_type}`",
            "warning"
        )
        await update.message.reply_text(
            f"Unsupported file type: {mime_type}\n"
            "Please send a PDF or image file."
        )
        return

    await update.message.reply_text(f"Processing {filename}...")

    try:
        file = await context.bot.get_file(document.file_id)
        file_bytes = await file.download_as_bytearray()

        await log_to_channel(
            context.bot,
            f"📄 *File Downloaded*\nFile: `{filename}`\nSize: {len(file_bytes)} bytes\nStarting OCR with Gemini 2.0...",
            "info"
        )

        async with get_db_context() as db:
            doc_service = DocumentService(db)
            result = await doc_service.process_document(
                user_id=user["id"],
                image_bytes=bytes(file_bytes),
                filename=filename
            )

        response = (
            f"Document Processed\n\n"
            f"File: {filename}\n"
            f"Type: {result['document_type']}\n\n"
            f"Summary: {result['summary']}\n\n"
            f"Original (German):\n{result['original_text'][:500]}{'...' if len(result['original_text']) > 500 else ''}\n\n"
            f"Translation (English):\n{result['translated_text'][:500]}{'...' if len(result['translated_text']) > 500 else ''}"
        )
        await update.message.reply_text(response)

        await log_to_channel(
            context.bot,
            f"📄 *Document Processed Successfully*\nUser: `{user['id']}`\nFile: `{filename}`\nType: {result['document_type']}\nDoc ID: `{result['id'][:8]}`\nVector: 3072d ✓\n\nSummary: {result['summary'][:200]}",
            "success"
        )

    except Exception as e:
        error_msg = str(e)[:300]
        logger.error(f"Document processing error: {e}")

        await log_to_channel(
            context.bot,
            f"*Document Processing FAILED*\nUser: `{user['id']}`\nFile: `{filename}`\nError: `{error_msg}`\n\n```{traceback.format_exc()[:500]}```",
            "error"
        )

        await update.message.reply_text(f"Error processing document: {str(e)[:100]}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular text messages - treat as search query."""
    user = await get_user(update)
    query = update.message.text

    await log_to_channel(
        context.bot,
        f"💬 *Text Message*\nUser: `{user['id']}` (@{update.effective_user.username or 'N/A'})\nText: {query[:100]}{'...' if len(query) > 100 else ''}",
        "info"
    )

    try:
        async with get_db_context() as db:
            memory_service = MemoryService(db)
            result = await memory_service.associative_search(
                user_id=user["id"],
                query=query,
                limit=3
            )

        if result["answer"]:
            await update.message.reply_text(result["answer"])
            await log_to_channel(
                context.bot,
                f"💬 *AI Answer Generated*\nResults: {len(result['results'])}",
                "success"
            )
        elif result["results"]:
            content = result["results"][0]["content"]
            await update.message.reply_text(f"Best match:\n{content[:500]}")
            await log_to_channel(
                context.bot,
                f"💬 *Best Match Found*\nSimilarity: {result['results'][0]['similarity']:.0%}",
                "success"
            )
        else:
            await update.message.reply_text(
                "I don't have information about that yet.\n"
                "Use /remember to store knowledge or send a document photo."
            )
            await log_to_channel(context.bot, f"💬 No matches found", "info")

    except Exception as e:
        error_msg = str(e)[:200]
        logger.error(f"Text handling error: {e}")

        await log_to_channel(
            context.bot,
            f"*Text Search FAILED*\nUser: `{user['id']}`\nError: `{error_msg}`\n\n```{traceback.format_exc()[:500]}```",
            "error"
        )

        await update.message.reply_text("Error processing your message. Please try again.")


def create_bot_application() -> Application:
    """Create and configure the Telegram bot application."""
    settings = get_cached_settings()
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
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return application
