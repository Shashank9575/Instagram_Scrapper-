"""
Parser — Email, Hashtag & Category extraction utilities
"""

import re
from typing import List, Dict

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

OBFUSCATED_EMAIL = re.compile(
    r"([a-zA-Z0-9._%+\-]+)\s*[\[\(]?\s*at\s*[\]\)]?\s*"
    r"([a-zA-Z0-9.\-]+)\s*[\[\(]?\s*dot\s*[\]\)]?\s*([a-zA-Z]{2,})",
    re.IGNORECASE,
)

HASHTAG_PATTERN = re.compile(r"#(\w+)", re.IGNORECASE)


def extract_email(text: str) -> str:
    if not text:
        return ""
    m = EMAIL_PATTERN.search(text)
    if m:
        return m.group(0).lower()
    m = OBFUSCATED_EMAIL.search(text)
    if m:
        return f"{m.group(1)}@{m.group(2)}.{m.group(3)}".lower()
    return ""


def extract_hashtags(text: str) -> List[str]:
    if not text:
        return []
    return [t.lower() for t in HASHTAG_PATTERN.findall(text)]


def detect_category(bio: str, hashtags: List[str]) -> str:
    from config.settings import CATEGORY_KEYWORDS
    combined = f"{bio} {' '.join(hashtags)}".lower()
    scores: Dict[str, int] = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score:
            scores[cat] = score
    return max(scores, key=scores.get) if scores else "Other"
