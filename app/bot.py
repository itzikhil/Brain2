"""Telegram bot with conversational AI agent."""
import logging
import traceback
import re
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
from app.services.gemini import get_gemini
from app.services.storage import get_storage
from app.services.obsidian import get_obsidian

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
    Optional logging to private Telegram channel.

    Args:
        bot: The Telegram bot instance
        message: The message to log
        level: Log level (info, success, warning, error)
    """
    settings = get_cached_settings()

    if not settings.log_channel_id:
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
        f"Hello {user['first_name'] or 'there'}! I'm Brain, your personal assistant.\n\n"
        "Just talk to me naturally:\n"
        "• Ask me questions\n"
        "• Tell me to remember things\n"
        "• Send photos of documents (I'll OCR and translate German)\n\n"
        "Shopping commands:\n"
        "/add <item> - Add item to shopping list\n"
        "/list - Show shopping list\n"
        "/clear - Remove checked items\n"
        "/done - Close shopping session"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    await update.message.reply_text(
        "I'm Brain, your conversational assistant.\n\n"
        "Talk to me naturally:\n"
        "• Ask questions about your stored information\n"
        "• Tell me to remember things\n"
        "• Send photos of documents for OCR & translation\n\n"
        "Shopping List Commands:\n"
        "/add <item> - Add item (e.g., /add 2 kg apples)\n"
        "/list - Show current list\n"
        "/clear - Remove checked items\n"
        "/done - Close shopping session"
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
        logger.error(f"Shopping add error: {e}")
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


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages for OCR."""
    user = await get_user(update)

    await log_to_channel(
        context.bot,
        f"📷 *Photo Received*\nUser: `{user['id']}` (@{update.effective_user.username or 'N/A'})",
        "pending"
    )

    await update.message.reply_text("Processing document...")

    # Get largest photo
    photo = update.message.photo[-1]

    try:
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        logger.info(f"Photo downloaded: {len(image_bytes)} bytes")

        async with get_db_context() as db:
            doc_service = DocumentService(db)
            result = await doc_service.process_document(
                user_id=user["id"],
                image_bytes=bytes(image_bytes),
                filename=f"telegram_{photo.file_id}.jpg"
            )

        # Build response message
        language = result.get('language', 'Unknown')
        amount = result.get('amount', '')
        sender = result.get('sender', '')

        # Determine translation status
        is_english = language.lower() in ['english', 'eng']
        translation_status = "already in English" if is_english else f"translated to English"

        response_lines = [
            f"✅ Archived: {result['document_type']}",
            f"🌐 Language: {language} ({translation_status})",
        ]

        # Add optional fields only if present
        if amount and amount.lower() != 'none':
            response_lines.append(f"💰 Amount: {amount}")

        if sender and sender.lower() != 'none':
            response_lines.append(f"🏢 From: {sender}")

        response_lines.append(f"\nSummary: {result['summary']}")
        response_lines.append("\nAsk me anytime to find this document.")

        response = "\n".join(response_lines)
        await update.message.reply_text(response)

        await log_to_channel(
            context.bot,
            f"📷 *Photo Processed*\nUser: `{user['id']}`\nType: {result['document_type']}\nDoc ID: `{result['id'][:8]}`",
            "success"
        )

    except Exception as e:
        error_msg = str(e)[:300]
        logger.error(f"Photo processing error: {e}\n{traceback.format_exc()}")

        await log_to_channel(
            context.bot,
            f"*Photo Processing FAILED*\nUser: `{user['id']}`\nError: `{error_msg}`",
            "error"
        )

        await update.message.reply_text(f"Error processing photo: {error_msg}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document messages (PDFs, images sent as files)."""
    user = await get_user(update)
    document = update.message.document

    # Check file type
    mime_type = document.mime_type or ""
    filename = document.file_name or "document"

    await log_to_channel(
        context.bot,
        f"📄 *Document Received*\nUser: `{user['id']}`\nFile: `{filename}`\nMIME: `{mime_type}`",
        "pending"
    )

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

        logger.info(f"File downloaded: {filename} ({len(file_bytes)} bytes)")

        async with get_db_context() as db:
            doc_service = DocumentService(db)
            result = await doc_service.process_document(
                user_id=user["id"],
                image_bytes=bytes(file_bytes),
                filename=filename
            )

        # Build response message
        language = result.get('language', 'Unknown')
        amount = result.get('amount', '')
        sender = result.get('sender', '')

        # Determine translation status
        is_english = language.lower() in ['english', 'eng']
        translation_status = "already in English" if is_english else f"translated to English"

        response_lines = [
            f"✅ Archived: {result['document_type']}",
            f"📁 File: {filename}",
            f"🌐 Language: {language} ({translation_status})",
        ]

        # Add optional fields only if present
        if amount and amount.lower() != 'none':
            response_lines.append(f"💰 Amount: {amount}")

        if sender and sender.lower() != 'none':
            response_lines.append(f"🏢 From: {sender}")

        response_lines.append(f"\nSummary: {result['summary']}")
        response_lines.append("\nAsk me anytime to find this document.")

        response = "\n".join(response_lines)
        await update.message.reply_text(response)

        await log_to_channel(
            context.bot,
            f"📄 *Document Processed*\nUser: `{user['id']}`\nFile: `{filename}`\nType: {result['document_type']}\nDoc ID: `{result['id'][:8]}`",
            "success"
        )

    except Exception as e:
        error_msg = str(e)[:300]
        logger.error(f"Document processing error: {e}\n{traceback.format_exc()}")

        await log_to_channel(
            context.bot,
            f"*Document Processing FAILED*\nUser: `{user['id']}`\nFile: `{filename}`\nError: `{error_msg}`",
            "error"
        )

        await update.message.reply_text(f"Error processing document: {error_msg}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle regular text messages with conversational AI.

    Detects "remember X" naturally, searches knowledge base,
    and provides natural responses with context.
    """
    user = await get_user(update)
    message = update.message.text

    logger.info(f"Text from user {user['id']}: {message[:100]}")

    try:
        # Detect "note:" or "note " prefix for Obsidian integration
        note_patterns = [
            r'^note:\s*(.+)$',
            r'^note\s+(.+)$',
        ]

        for pattern in note_patterns:
            match = re.match(pattern, message.lower())
            if match:
                # Extract content after "note:" or "note "
                content_start = message.lower().find("note")
                if ":" in message[content_start:content_start+10]:
                    # "note:" format
                    content = message[message.find(":", content_start) + 1:].strip()
                else:
                    # "note " format
                    content = message[content_start + 4:].strip()

                # Save to Obsidian
                obsidian = get_obsidian()
                if obsidian.enabled:
                    try:
                        result = await obsidian.save_note(content)

                        # Also store as memory for searchability
                        async with get_db_context() as db:
                            memory_service = MemoryService(db)
                            await memory_service.store_memory(
                                user_id=user["id"],
                                content=content,
                                source="obsidian_note"
                            )

                        await update.message.reply_text(f"📝 Saved to Obsidian: \"{result['title']}\"")
                        logger.info(f"Obsidian note saved: {result['filename']}")
                        return
                    except Exception as e:
                        logger.error(f"Obsidian save failed: {e}")
                        await update.message.reply_text(f"Failed to save to Obsidian: {str(e)[:100]}")
                        return
                else:
                    await update.message.reply_text("Obsidian integration is not enabled. Set OBSIDIAN_VAULT_PATH in settings.")
                    return

        # Detect "remember" intent naturally
        remember_patterns = [
            r'^remember\s+(.+)$',
            r'^please remember\s+(.+)$',
            r'^can you remember\s+(.+)$',
            r'^store\s+(.+)$',
            r'^save\s+(.+)$',
        ]

        for pattern in remember_patterns:
            match = re.match(pattern, message.lower())
            if match:
                content = message[match.start(1) - match.start():].strip()

                # Store memory
                async with get_db_context() as db:
                    memory_service = MemoryService(db)
                    result = await memory_service.store_memory(
                        user_id=user["id"],
                        content=content,
                        source="telegram"
                    )

                await update.message.reply_text(f"Got it! I'll remember that.")
                logger.info(f"Stored memory: {result['id'][:8]}")
                return

        # Detect time-based queries for latest documents
        # Only trigger for generic "last document" queries, not "last electricity bill"
        time_based_keywords = [
            "last document", "latest document", "most recent document",
            "last uploaded", "newest document", "recently uploaded",
            "last file", "latest file", "most recent file",
            "newest file", "last upload", "latest upload"
        ]
        message_lower = message.lower()
        is_time_based = any(keyword in message_lower for keyword in time_based_keywords)

        # Additional check: if there's a file retrieval intent AND specific content after "last/latest",
        # treat it as semantic search, not time-based
        file_retrieval_keywords = [
            "send me", "get me", "fetch", "download", "show me", "give me",
            "send the", "get the", "retrieve", "attach", "share the"
        ]
        has_file_retrieval_intent = any(keyword in message_lower for keyword in file_retrieval_keywords)

        # If user says "send me my latest X" where X is not "document/file", use semantic search
        if is_time_based and has_file_retrieval_intent:
            # Check if they're asking for a specific type (has words after latest/last)
            for keyword in ["last", "latest", "most recent", "newest"]:
                if keyword in message_lower:
                    # Find position of keyword
                    idx = message_lower.find(keyword)
                    after_keyword = message_lower[idx + len(keyword):].strip()
                    # If there are specific words after (not just "document" or "file"), use semantic search
                    if after_keyword and not after_keyword.startswith(("document", "file", "upload")):
                        is_time_based = False
                        logger.info(f"Time-based keyword found but specific content detected - using semantic search instead")
                        break

        # Initialize search_result
        search_result = {"results": []}

        if is_time_based:
            logger.info(f"Time-based query detected - using DB query for latest document: '{message[:100]}'")
            # Use direct database query for latest document
            async with get_db_context() as db:
                doc_service = DocumentService(db)
                latest_docs = await doc_service.get_latest_document(user_id=user["id"], limit=1)

            if latest_docs:
                # Convert to search_result format
                search_result["results"] = [
                    {
                        "source_type": "document",
                        "content": f"{latest_docs[0]['original_text']}\n\n{latest_docs[0]['translated_text']}",
                        "similarity": 1.0,  # Perfect match since it's the latest
                        "category": None,
                        "metadata": latest_docs[0]["metadata"]
                    }
                ]
                logger.info(f"Time-based path: found latest document: {latest_docs[0]['document_type']} from {latest_docs[0]['created_at']}")
        else:
            logger.info(f"Using semantic search for query: '{message[:100]}'")
            # Search knowledge base for relevant context
            async with get_db_context() as db:
                memory_service = MemoryService(db)
                search_result = await memory_service.associative_search(
                    user_id=user["id"],
                    query=message,
                    limit=3
                )

        # Build context string from relevant results
        context_str = None
        if search_result["results"]:
            context_parts = []
            for item in search_result["results"]:
                source = "Document" if item["source_type"] == "document" else "Memory"
                context_parts.append(f"[{source}, similarity: {item['similarity']:.0%}]\n{item['content'][:500]}")
            context_str = "\n\n---\n\n".join(context_parts)
            logger.info(f"Found {len(search_result['results'])} relevant items (top: {search_result['results'][0]['similarity']:.0%})")

        # Get AI response with context
        gemini = get_gemini()
        response = await gemini.chat(message, context=context_str)

        await update.message.reply_text(response)
        logger.info(f"AI response sent (with context: {bool(context_str)})")

        # Check file retrieval intent (already computed above for time-based detection)
        wants_file = has_file_retrieval_intent

        if wants_file:
            logger.info(f"File retrieval intent detected - will send files from {'time-based' if is_time_based else 'semantic'} search results")

        # Send back original files from R2 if user wants them
        storage = get_storage()
        if wants_file and storage.enabled and search_result["results"]:
            # Count documents with R2 keys
            docs_with_r2 = [item for item in search_result["results"]
                           if item["source_type"] == "document" and item.get("metadata", {}).get("r2_key")]
            logger.info(f"Found {len(docs_with_r2)} document(s) with R2 keys in search results")

            for item in search_result["results"]:
                # Only send documents (not memories) that have R2 keys
                if item["source_type"] == "document" and item.get("metadata", {}).get("r2_key"):
                    r2_key = item["metadata"]["r2_key"]
                    logger.info(f"Attempting to retrieve file from R2: {r2_key}")
                    try:
                        # Download file from R2
                        file_bytes = storage.download_file(r2_key)
                        if file_bytes:
                            # Extract filename from R2 key (format: category/year/date_type_filename)
                            filename = r2_key.split("/")[-1]  # Get last part of path
                            # Remove date and type prefix (date_type_filename -> filename)
                            parts = filename.split("_", 2)
                            if len(parts) >= 3:
                                filename = parts[2]

                            # Send document back to user
                            from io import BytesIO
                            await context.bot.send_document(
                                chat_id=update.effective_chat.id,
                                document=BytesIO(file_bytes),
                                filename=filename,
                                caption=f"📎 {item['category'] or 'Document'}"
                            )
                            logger.info(f"Successfully sent file from R2: {r2_key}")
                    except Exception as e:
                        logger.error(f"Failed to send file from R2 ({r2_key}): {e}")
        elif wants_file and search_result["results"]:
            logger.info("File retrieval intent detected but no documents with R2 keys found in search results")

    except Exception as e:
        error_msg = str(e)[:200]
        logger.error(f"Text handling error: {e}\n{traceback.format_exc()}")

        await log_to_channel(
            context.bot,
            f"*Text Handling Error*\nUser: `{user['id']}`\nError: `{error_msg}`",
            "error"
        )

        await update.message.reply_text(f"Sorry, I encountered an error: {error_msg}")


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
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return application
