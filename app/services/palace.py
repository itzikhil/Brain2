"""MemPalace integration — conversation memory storage and search."""
import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

BERLIN_TZ = ZoneInfo("Europe/Berlin")
CONVOS_DIR = Path.home() / ".mempalace" / "conversations"
PALACE_PATH = None  # resolved lazily

# Track exchanges since last mine
_exchange_count = 0
MINE_EVERY = 10


def _get_palace_path() -> str:
    """Get the palace path from mempalace config."""
    global PALACE_PATH
    if PALACE_PATH is None:
        try:
            from mempalace.config import MempalaceConfig
            PALACE_PATH = MempalaceConfig().palace_path
        except Exception:
            PALACE_PATH = str(Path.home() / ".mempalace" / "palace")
    return PALACE_PATH


def _ensure_convos_dir():
    """Create the conversations directory if it doesn't exist."""
    CONVOS_DIR.mkdir(parents=True, exist_ok=True)


async def store_conversation(user_message: str, bot_response: str, timestamp: str = None):
    """
    Append a conversation exchange to the daily file.

    Format: timestamp\\nUser: message\\nBrain: response\\n---\\n
    """
    global _exchange_count

    _ensure_convos_dir()

    if timestamp is None:
        now = datetime.now(BERLIN_TZ)
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    else:
        now = datetime.now(BERLIN_TZ)

    date_str = now.strftime("%Y-%m-%d")
    filename = CONVOS_DIR / f"conversations_{date_str}.txt"

    entry = f"{timestamp}\nUser: {user_message}\nBrain: {bot_response}\n---\n"

    # File I/O in a thread to avoid blocking the event loop
    await asyncio.to_thread(_write_entry, filename, entry)

    _exchange_count += 1
    logger.info(f"📦 Stored conversation exchange ({_exchange_count} since last mine)")

    # Auto-mine every N exchanges
    if _exchange_count >= MINE_EVERY:
        _exchange_count = 0
        asyncio.create_task(_run_mine())


def _write_entry(filepath: Path, entry: str):
    """Synchronous file append."""
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(entry)


async def search_memory(query: str, n_results: int = 3) -> str:
    """
    Search the MemPalace for relevant conversation memories.

    Returns a formatted context string, or empty string if nothing found.
    """
    try:
        results = await asyncio.to_thread(_search_sync, query, n_results)
        if not results:
            return ""
        return results
    except Exception as e:
        logger.error(f"MemPalace search failed: {e}")
        return ""


def _search_sync(query: str, n_results: int) -> str:
    """Synchronous ChromaDB search against the palace."""
    try:
        import chromadb
        palace_path = _get_palace_path()
        client = chromadb.PersistentClient(path=palace_path)
        col = client.get_collection("mempalace_drawers")
    except Exception:
        return ""

    try:
        results = col.query(
            query_texts=[query],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return ""

    docs = results["documents"][0]
    dists = results["distances"][0]

    if not docs:
        return ""

    parts = []
    for doc, dist in zip(docs, dists):
        similarity = round(1 - dist, 2)
        if similarity < 0.3:
            continue
        parts.append(f"[Memory, relevance: {similarity}]\n{doc[:400]}")

    if not parts:
        return ""

    return "\n\n---\n\n".join(parts)


async def get_wakeup_context() -> str:
    """
    Get L0 + L1 wake-up context from MemPalace.

    Returns the wake-up text, or empty string if unavailable.
    """
    try:
        return await asyncio.to_thread(_wakeup_sync)
    except Exception as e:
        logger.error(f"MemPalace wake-up failed: {e}")
        return ""


def _wakeup_sync() -> str:
    """Synchronous wake-up call."""
    try:
        from mempalace.layers import MemoryStack
        palace_path = _get_palace_path()
        stack = MemoryStack(palace_path=palace_path)
        return stack.wake_up()
    except Exception:
        return ""


async def _run_mine():
    """Run mempalace mine on conversations directory in background."""
    try:
        logger.info("🔨 Mining new conversations into MemPalace...")
        await asyncio.to_thread(_mine_sync)
        logger.info("🔨 MemPalace mining complete")
    except Exception as e:
        logger.error(f"MemPalace mining failed: {e}")


def _mine_sync():
    """Synchronous mine call."""
    _ensure_convos_dir()
    try:
        from mempalace.convo_miner import mine_convos
        palace_path = _get_palace_path()
        mine_convos(
            convo_dir=str(CONVOS_DIR),
            palace_path=palace_path,
            wing="brain2",
            agent="Brain",
            limit=0,
            dry_run=False,
            extract_mode="exchange",
        )
    except Exception as e:
        logger.error(f"mine_convos error: {e}")


async def run_scheduled_mine():
    """Entry point for the scheduler — just wraps _run_mine."""
    await _run_mine()
