"""Deterministic pre-bootstrap and pre-export secret & credential scrubber.

Redacts known secret formats (OpenAI, Google, GitHub, AWS, Bearer tokens, private keys)
from text prompts to prevent accidental leakage into AI conversations.
Carefully preserves hex strings (such as 64-character SHA-256 digests).
"""

import re
from typing import Tuple

SECRET_PATTERNS = [
    # OpenAI & generic AI sk- keys (sk-...)
    re.compile(r"\b(sk-[A-Za-z0-9_-]{10,})\b"),
    # Google API Keys (AIza...)
    re.compile(r"\b(AIza[0-9A-Za-z_-]{35})\b"),
    # GitHub Personal Access Tokens (ghp_, gho_, ghu_, ghs_, ghr_)
    re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,})\b"),
    # AWS Access Key IDs
    re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
    # Bearer tokens
    re.compile(r"\bBearer\s+([A-Za-z0-9._\-]{20,})\b", re.IGNORECASE),
    # PEM Private Key Blocks
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    # Common .env assignments with sensitive variable names
    re.compile(r"\b((?:API_KEY|SECRET|PASSWORD|TOKEN|AUTH_TOKEN)\s*=\s*['\"]?)([^'\s\"\n\r]{8,})(['\"]?)", re.IGNORECASE),
]

REDACTED_TAG = "[REDACTED_SECRET]"


def scrub_secrets(text: str) -> Tuple[str, int]:
    """Scans text and redacts detected secrets, returning (scrubbed_text, redaction_count).

    Does NOT redact standard 64-character lowercase/uppercase hex hashes (SHA-256).
    """
    if not text:
        return "", 0

    redaction_count = 0
    scrubbed = text

    # Handle PEM blocks first
    def pem_repl(match: re.Match) -> str:
        nonlocal redaction_count
        redaction_count += 1
        return REDACTED_TAG

    scrubbed = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----", pem_repl, scrubbed)

    # Handle standard token patterns
    for pat in SECRET_PATTERNS[:-2]:  # exclude PEM and .env
        def token_repl(match: re.Match) -> str:
            nonlocal redaction_count
            token = match.group(1)
            # Guard: If token is purely a 64-character hex hash, do NOT redact!
            if len(token) == 64 and re.fullmatch(r"[0-9a-fA-F]{64}", token):
                return match.group(0)
            redaction_count += 1
            if match.group(0).startswith("Bearer "):
                return f"Bearer {REDACTED_TAG}"
            return REDACTED_TAG

        scrubbed = pat.sub(token_repl, scrubbed)

    # Handle .env assignments
    def env_repl(match: re.Match) -> str:
        nonlocal redaction_count
        prefix = match.group(1)
        val = match.group(2)
        suffix = match.group(3)
        # Guard: If val is a 64-char hash or already redacted, skip
        if (len(val) == 64 and re.fullmatch(r"[0-9a-fA-F]{64}", val)) or val == REDACTED_TAG:
            return match.group(0)
        redaction_count += 1
        return f"{prefix}{REDACTED_TAG}{suffix}"

    scrubbed = SECRET_PATTERNS[-1].sub(env_repl, scrubbed)

    return scrubbed, redaction_count
