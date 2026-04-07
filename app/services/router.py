"""Message routing — privacy classification + complexity detection."""
import re
import unicodedata

# ---------------------------------------------------------------------------
# Privacy classification (S1 = safe, S3 = private)
# ---------------------------------------------------------------------------

S3_KEYWORDS = [
    "password", "passwort",
    "payslip", "gehaltsabrechnung", "lohnabrechnung",
    "salary", "gehalt", "brutto", "netto",
    "tax id", "steuer-id", "steuernummer",
    "iban", "kontonummer",
    "sozialversicherungsnummer",
    "personalausweis", "reisepass", "passport",
    "api_key", "token", "ssh", "private_key",
    "pin", "kredit", "credit card",
]

S3_PATTERNS = [
    re.compile(r"DE\d{20}", re.IGNORECASE),
    re.compile(r"\d{2}\s?\d{3}\s?\d{3}\s?\d{3}"),
    re.compile(r"(brutto|netto|gehalt)\s*[:\-]?\s*[\d.,]+", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+\w*\s*PRIVATE KEY-----"),
    re.compile(r"(postgres|mysql|mongodb)://\S+"),
]


def classify_privacy(message: str) -> str:
    """Return 'S3' for private/sensitive messages, 'S1' otherwise."""
    lower = message.lower()

    for keyword in S3_KEYWORDS:
        if keyword in lower:
            return "S3"

    for pattern in S3_PATTERNS:
        if pattern.search(message):
            return "S3"

    return "S1"


# ---------------------------------------------------------------------------
# Complexity classification (simple vs complex)
# ---------------------------------------------------------------------------

COMPLEX_KEYWORDS = [
    "analyze", "analyse", "compare", "explain in detail",
    "summarize this", "summary of", "review this", "review the",
    "what are the implications", "pros and cons",
    "break down", "step by step", "calculate",
    # German
    "analysiere", "vergleiche", "erkläre", "zusammenfassung",
]

# Phrases that reference a specific document in the knowledge base
DOC_REFERENCE_PATTERNS = [
    re.compile(r"\b(my|the|this|that)\s+(payslip|contract|invoice|receipt|document|letter|bill|form|report|certificate|tax\s+return)", re.IGNORECASE),
    re.compile(r"\b(mein[e]?|die|das|der|dies[e]?[rms]?)\s+(gehaltsabrechnung|vertrag|rechnung|quittung|dokument|brief|formular|bericht|bescheinigung|steuererklärung)", re.IGNORECASE),
]

SIMPLE_PREFIXES = [
    "remind me", "remember", "note:", "note ", "/add", "/list", "/clear", "/done",
    "hi", "hello", "hey", "good morning", "good evening", "thanks", "thank you",
    "hallo", "guten morgen", "guten abend", "danke",
    "shalom", "toda",
]


def _is_non_latin_heavy(text: str) -> bool:
    """Check if a significant portion of the text is non-Latin (Hebrew, Arabic, CJK, etc.)."""
    if len(text) < 10:
        return False
    non_latin = sum(
        1 for ch in text
        if ch.isalpha() and unicodedata.category(ch).startswith("L")
        and not ("LATIN" in unicodedata.name(ch, ""))
    )
    alpha = sum(1 for ch in text if ch.isalpha())
    if alpha == 0:
        return False
    return non_latin / alpha > 0.3


def classify_complexity(message: str, has_document_context: bool = False) -> str:
    """Return 'complex' or 'simple'.

    Args:
        message: The user's raw message text.
        has_document_context: True when the knowledge-base search returned
            document content (not just memories).
    """
    lower = message.lower()

    # --- Definite simple: commands, greetings, very short ---
    if len(message) < 40:
        for prefix in SIMPLE_PREFIXES:
            if lower.startswith(prefix):
                return "simple"
        # Very short messages are almost always simple
        if len(message) < 20:
            return "simple"

    # --- Definite complex checks ---

    # Long messages
    if len(message) > 500:
        return "complex"

    # Document context present (user is asking about an uploaded doc)
    if has_document_context:
        return "complex"

    # Complex keywords
    for kw in COMPLEX_KEYWORDS:
        if kw in lower:
            return "complex"

    # References a specific document
    for pattern in DOC_REFERENCE_PATTERNS:
        if pattern.search(message):
            return "complex"

    # Non-Latin text over 200 chars (German doesn't trigger this; Hebrew/Arabic will)
    if len(message) > 200 and _is_non_latin_heavy(message):
        return "complex"

    # --- Default: simple ---
    return "simple"


def classify_message(message: str, has_document_context: bool = False) -> dict:
    """Full classification for routing.

    Returns dict with keys:
        privacy: "S1" | "S3"
        complexity: "simple" | "complex"
    """
    return {
        "privacy": classify_privacy(message),
        "complexity": classify_complexity(message, has_document_context),
    }
