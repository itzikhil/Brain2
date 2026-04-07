"""Automatic memory extraction - learns personal facts from every conversation."""
import json
import logging
import re

import google.generativeai as genai

from app.config import get_settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Extract any personal facts about the user from this conversation exchange.
Return a JSON array of objects with keys: category, fact, confidence (0.0-1.0).

Categories: personal, family, work, preferences, health, finance, schedule, location

Rules:
- Only extract CLEAR facts stated by the user, not assumptions
- Do not extract questions the user asks (those are not facts)
- Do not extract facts about the AI assistant
- Confidence should reflect how explicitly the fact was stated
- If no personal facts found, return: []

User message: {message}
Assistant response: {response}

Return ONLY the JSON array, no other text."""


async def extract_facts(message: str, response: str) -> list[dict]:
    """
    Analyze a conversation exchange and extract personal facts.

    Uses Gemini directly (lightweight call, no privacy concern since
    we're analyzing what the user already sent to the bot).
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        return []

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = EXTRACTION_PROMPT.format(message=message, response=response)

        result = await model.generate_content_async(prompt)
        text = result.text.strip()

        # Strip markdown code fences if present
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

        facts = json.loads(text)

        if not isinstance(facts, list):
            return []

        # Filter for confidence > 0.7
        valid_facts = [
            f for f in facts
            if isinstance(f, dict)
            and f.get("confidence", 0) > 0.7
            and f.get("fact")
            and f.get("category")
        ]

        return valid_facts

    except (json.JSONDecodeError, ValueError) as e:
        logger.debug(f"Failed to parse extraction response: {e}")
        return []
    except Exception as e:
        logger.error(f"Fact extraction failed: {e}")
        return []
