"""Privacy classification for message routing."""
import re

# Keywords that indicate sensitive content (German + English, lowercase)
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

# Regex patterns for structured sensitive data
S3_PATTERNS = [
    re.compile(r"DE\d{20}", re.IGNORECASE),                          # German IBAN
    re.compile(r"\d{2}\s?\d{3}\s?\d{3}\s?\d{3}"),                    # German tax ID
    re.compile(r"(brutto|netto|gehalt)\s*[:\-]?\s*[\d.,]+", re.IGNORECASE),  # Salary amounts
    re.compile(r"-----BEGIN\s+\w*\s*PRIVATE KEY-----"),               # Private keys
    re.compile(r"(postgres|mysql|mongodb)://\S+"),                    # Connection strings
]


def classify_privacy(message: str) -> str:
    """Classify a message as S1 (safe) or S3 (private).

    Checks keywords first (fast), then regex patterns.

    Returns:
        "S1" for safe messages, "S3" for private/sensitive messages
    """
    lower = message.lower()

    # Fast keyword check
    for keyword in S3_KEYWORDS:
        if keyword in lower:
            return "S3"

    # Pattern check
    for pattern in S3_PATTERNS:
        if pattern.search(message):
            return "S3"

    return "S1"
