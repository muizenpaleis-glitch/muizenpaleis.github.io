"""Text normalization for the matching engine (req. 5 Level 2):
case-folding, diacritics, punctuation, "feat." handling, and common
transliterations for JP/KR markets.
"""

from __future__ import annotations

import re
import unicodedata

# "Title (feat. X)", "Title ft. X", "Title featuring X", "Title with X".
_FEAT_RE = re.compile(
    r"[\(\[（]?\s*(?:feat\.?|featuring|ft\.?)\s+[^)\]）]*[\)\]）]?\s*$",
    re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")

# Common transliteration/spelling equivalences seen on JP/KR sources.
# Extensible: collectors and deployments can register additional pairs.
_TRANSLITERATIONS: dict[str, str] = {
    "&": " and ",
    "＆": " and ",
    "ヴ": "v",
    "・": " ",
    "〜": "-",
    "ー": "-",
}


def register_transliteration(source: str, replacement: str) -> None:
    _TRANSLITERATIONS[source] = replacement


def strip_feat(text: str) -> str:
    """Remove a trailing featured-artist clause from a title."""
    return _FEAT_RE.sub("", text).strip()


def normalize(text: str) -> str:
    """Normalize a name or title for fuzzy comparison.

    NFKC folds fullwidth Latin (common on Japanese services) to ASCII;
    NFKD + combining-mark removal strips diacritics.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    for src, repl in _TRANSLITERATIONS.items():
        text = text.replace(src, repl)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def normalize_title(title: str) -> str:
    """Normalize a song/work title, dropping any "feat." clause."""
    return normalize(strip_feat(title or ""))
