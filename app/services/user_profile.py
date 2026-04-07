"""User profile service - stores and retrieves automatically extracted facts."""
import logging
from datetime import datetime

from sqlalchemy import text

from app.database import get_db_context

logger = logging.getLogger(__name__)

CATEGORIES = [
    "personal", "family", "work", "preferences",
    "health", "finance", "schedule", "location",
]

CATEGORY_ICONS = {
    "personal": "👤",
    "family": "👨‍👩‍👧‍👦",
    "work": "💼",
    "preferences": "⭐",
    "health": "🏥",
    "finance": "💰",
    "schedule": "📅",
    "location": "📍",
}


async def store_fact(
    category: str, fact: str, source_message: str, confidence: float
) -> bool:
    """
    Store or update a user fact.

    If a similar fact already exists (same category, similar text), update it.
    Otherwise insert a new one.
    """
    category = category.lower().strip()
    if category not in CATEGORIES:
        category = "personal"

    async with get_db_context() as db:
        # Check for existing similar fact (exact match or substring)
        result = await db.execute(
            text("""
                SELECT id, fact FROM user_facts
                WHERE category = :category
                AND active = true
                AND (
                    fact = :fact
                    OR fact ILIKE '%' || :fact_short || '%'
                    OR :fact ILIKE '%' || fact || '%'
                )
                LIMIT 1
            """),
            {
                "category": category,
                "fact": fact,
                "fact_short": fact[:50] if len(fact) > 50 else fact,
            },
        )
        existing = result.fetchone()

        if existing:
            # Update existing fact
            await db.execute(
                text("""
                    UPDATE user_facts
                    SET fact = :fact,
                        source_message = :source_message,
                        confidence = :confidence,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": existing.id,
                    "fact": fact,
                    "source_message": source_message,
                    "confidence": confidence,
                },
            )
            logger.info(f"Updated existing fact [{category}]: {fact[:60]}")
            return False  # updated, not new
        else:
            # Insert new fact
            await db.execute(
                text("""
                    INSERT INTO user_facts (category, fact, source_message, confidence)
                    VALUES (:category, :fact, :source_message, :confidence)
                """),
                {
                    "category": category,
                    "fact": fact,
                    "source_message": source_message,
                    "confidence": confidence,
                },
            )
            logger.info(f"Stored new fact [{category}]: {fact[:60]}")
            return True  # new


async def get_profile_summary() -> str:
    """Return a formatted summary of all known facts grouped by category."""
    async with get_db_context() as db:
        result = await db.execute(
            text("""
                SELECT category, fact, confidence, updated_at
                FROM user_facts
                WHERE active = true
                ORDER BY category, updated_at DESC
            """)
        )
        rows = result.fetchall()

    if not rows:
        return "I don't know anything about you yet. Just keep chatting and I'll learn!"

    # Group by category
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row.category, []).append(row)

    lines = ["🧠 What I know about you:\n"]
    for category in CATEGORIES:
        facts = grouped.get(category, [])
        if not facts:
            continue
        icon = CATEGORY_ICONS.get(category, "•")
        lines.append(f"{icon} {category.title()}")
        for f in facts:
            lines.append(f"  • {f.fact}")
        lines.append("")

    return "\n".join(lines).strip()


async def get_relevant_facts(message: str) -> str:
    """Find facts relevant to the current message via keyword search."""
    # Extract meaningful words (skip very short ones and common words)
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "do", "does", "did", "have", "has", "had", "will", "would",
        "can", "could", "should", "may", "might", "shall", "must",
        "i", "me", "my", "you", "your", "we", "our", "they", "their",
        "it", "its", "this", "that", "what", "which", "who", "how",
        "when", "where", "why", "not", "no", "yes", "and", "or", "but",
        "if", "then", "so", "to", "of", "in", "on", "at", "for", "with",
        "about", "from", "up", "out", "just", "also", "very", "too",
    }
    words = [
        w.lower().strip(".,!?;:'\"")
        for w in message.split()
        if len(w) > 2
    ]
    keywords = [w for w in words if w not in stop_words]

    if not keywords:
        return ""

    # Build OR condition for keyword matching
    conditions = " OR ".join(
        f"fact ILIKE '%' || :kw{i} || '%'" for i in range(len(keywords))
    )
    params = {f"kw{i}": kw for i, kw in enumerate(keywords)}

    async with get_db_context() as db:
        result = await db.execute(
            text(f"""
                SELECT category, fact FROM user_facts
                WHERE active = true AND ({conditions})
                ORDER BY updated_at DESC
                LIMIT 5
            """),
            params,
        )
        rows = result.fetchall()

    if not rows:
        return ""

    facts = [f"[{r.category}] {r.fact}" for r in rows]
    return "What I know about you:\n" + "\n".join(facts)


async def forget_fact(fact_text: str) -> int:
    """Deactivate facts matching the given text. Returns count of deactivated facts."""
    async with get_db_context() as db:
        result = await db.execute(
            text("""
                UPDATE user_facts
                SET active = false, updated_at = NOW()
                WHERE active = true
                AND fact ILIKE '%' || :fact_text || '%'
                RETURNING id
            """),
            {"fact_text": fact_text},
        )
        rows = result.fetchall()
        count = len(rows)

    if count:
        logger.info(f"Deactivated {count} fact(s) matching: {fact_text[:60]}")
    return count
