"""PII detection: structured patterns via regex, person names via spaCy.

Detection is deliberately two-tier:
  - Regex handles structured, format-predictable PII (emails, IDs, phone
    numbers, government IDs, dates).
  - spaCy's NER handles unstructured PII (person names) that regex cannot
    reliably capture.

Both tiers emit PIIMatch objects with character offsets into the ORIGINAL
text, so redaction can be done purely by offset without re-scanning text.
"""

import re
from dataclasses import dataclass

import spacy

from pii_app.config import (
    ADDRESS_KEYWORDS,
    DEFAULT_ENABLED_CATEGORIES,
    DOB_KEYWORD_WINDOW,
    DOB_KEYWORDS,
    PERSON_CONFIDENCE,
    PERSON_MAX_WORDS,
    PERSON_NAME_STOPWORDS,
    REGEX_PATTERNS,
)

# Word shapes accepted inside a candidate person name: ordinary title-case
# words (allowing an internal apostrophe/hyphen, e.g. "O'Brien", "Szeto-Lin")
# and short all-caps tokens treated as initials ("KC", "DK").
_TITLE_CASE_WORD = re.compile(r"^[A-Z][a-z]*(?:['’\-][A-Za-z]+)*$")
_INITIALS_WORD = re.compile(r"^[A-Z]{1,3}$")

# Characters stripped from the edges of a candidate name/address segment
# before validation (punctuation left over from sentence/list formatting).
_EDGE_PUNCT = " \t:;,.()[]\"'"

_NLP_CACHE = {}


@dataclass
class PIIMatch:
    label: str
    start: int
    end: int
    text: str
    confidence: float
    source: str  # "regex" or "spacy"


def get_nlp():
    """Load (and cache) the spaCy pipeline. Kept lazy so imports stay fast."""
    from pii_app.config import SPACY_MODEL

    if SPACY_MODEL not in _NLP_CACHE:
        try:
            _NLP_CACHE[SPACY_MODEL] = spacy.load(SPACY_MODEL)
        except OSError as exc:
            raise RuntimeError(
                f"spaCy model '{SPACY_MODEL}' is not installed. "
                f"Run: python -m spacy download {SPACY_MODEL}"
            ) from exc
    return _NLP_CACHE[SPACY_MODEL]


def _detect_regex_matches(text: str, enabled_categories: dict) -> list:
    matches = []

    for key, spec in REGEX_PATTERNS.items():
        if key == "DATE_OF_BIRTH":
            continue  # handled separately with keyword context
        if key == "PINCODE" and not enabled_categories.get("PINCODE", False):
            continue
        if key != "PINCODE" and not enabled_categories.get(key, True):
            continue

        for m in spec["pattern"].finditer(text):
            matches.append(
                PIIMatch(
                    label=spec["label"],
                    start=m.start(),
                    end=m.end(),
                    text=m.group(),
                    confidence=spec["confidence"],
                    source="regex",
                )
            )

    return matches


def _detect_dates_of_birth(text: str, enabled_categories: dict) -> list:
    if not enabled_categories.get("DATE_OF_BIRTH", True):
        return []

    matches = []
    date_pattern = REGEX_PATTERNS["DATE_OF_BIRTH"]["pattern"]
    confidence = REGEX_PATTERNS["DATE_OF_BIRTH"]["confidence"]
    lower_text = text.lower()

    for m in date_pattern.finditer(text):
        window_start = max(0, m.start() - DOB_KEYWORD_WINDOW)
        context = lower_text[window_start:m.start()]
        if any(keyword in context for keyword in DOB_KEYWORDS):
            matches.append(
                PIIMatch(
                    label="DATE_OF_BIRTH",
                    start=m.start(),
                    end=m.end(),
                    text=m.group(),
                    confidence=min(confidence + 0.25, 0.95),
                    source="regex",
                )
            )

    return matches


_ADDRESS_KEYWORD_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in ADDRESS_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def _looks_like_address(snippet: str) -> bool:
    """Require actual address-shaped evidence, not just a nearby keyword.

    A bare keyword match (e.g. "address" inside "addressee", or "road" in
    running prose) is not enough — a real address line almost always
    carries a house/PIN number or multiple comma-separated segments.
    """
    if not snippet.strip():
        return False
    has_digit = bool(re.search(r"\d", snippet))
    has_multiple_segments = snippet.count(",") >= 2
    return has_digit or has_multiple_segments


def _detect_addresses(text: str, enabled_categories: dict) -> list:
    """Heuristic address detection: flag the line following an address
    keyword, up to the next line break or a reasonable character cap, then
    require the captured text to actually look like an address.

    This is intentionally simple (no NLP address parser) and should be
    treated as a starting point for analyst review, not a precise extractor.
    """
    if not enabled_categories.get("ADDRESS", True):
        return []

    matches = []

    for keyword_match in _ADDRESS_KEYWORD_PATTERN.finditer(text):
        keyword_end = keyword_match.end()

        line_end = text.find("\n", keyword_end)
        if line_end == -1:
            line_end = len(text)

        # Capture from just after the keyword (and any ":" / whitespace)
        # to the end of the line, capped at 120 chars.
        content_start = keyword_end
        while content_start < line_end and text[content_start] in ":, \t":
            content_start += 1

        content_end = min(line_end, content_start + 120)

        if content_end <= content_start:
            continue

        snippet = text[content_start:content_end]
        if not _looks_like_address(snippet):
            continue

        matches.append(
            PIIMatch(
                label="ADDRESS",
                start=content_start,
                end=content_end,
                text=snippet,
                confidence=0.55,
                source="regex",
            )
        )

    return matches


def _looks_like_person_name(candidate: str) -> bool:
    """Validate a candidate name's shape and screen it against the domain
    noun stoplist (see config.PERSON_NAME_STOPWORDS for why this exists).
    """
    words = candidate.split()
    if not (2 <= len(words) <= PERSON_MAX_WORDS):
        return False

    for word in words:
        bare = word.strip("'’")
        stoplist_key = re.sub(r"['’]s$", "", bare).lower()
        if stoplist_key in PERSON_NAME_STOPWORDS:
            return False

        if _INITIALS_WORD.match(word):
            continue
        if word.isupper() and len(word) > 3:
            return False  # likely an acronym (TPRM), not initials
        if not _TITLE_CASE_WORD.match(word):
            return False

    return True


def _detect_person_names(text: str, enabled_categories: dict) -> list:
    if not enabled_categories.get("PERSON", True):
        return []

    nlp = get_nlp()
    doc = nlp(text)
    matches = []

    for ent in doc.ents:
        if ent.label_ != "PERSON":
            continue

        # Extraction from DOCX/PPTX joins paragraphs/cells with bare "\n",
        # which gives spaCy no sentence boundary — it can fuse several
        # adjacent names (or a name and the next line's header text) into
        # one entity. Split on line breaks and validate each piece
        # independently, in its own absolute offsets, before accepting it.
        raw = text[ent.start_char:ent.end_char]
        for line_match in re.finditer(r"[^\n]+", raw):
            segment = line_match.group()
            seg_start = ent.start_char + line_match.start()

            stripped = segment.strip(_EDGE_PUNCT)
            if not stripped:
                continue
            lead_trim = len(segment) - len(segment.lstrip(_EDGE_PUNCT))
            trail_trim = len(segment) - len(segment.rstrip(_EDGE_PUNCT))
            candidate_start = seg_start + lead_trim
            candidate_end = seg_start + len(segment) - trail_trim
            candidate_text = text[candidate_start:candidate_end]

            if not _looks_like_person_name(candidate_text):
                continue

            matches.append(
                PIIMatch(
                    label="PERSON",
                    start=candidate_start,
                    end=candidate_end,
                    text=candidate_text,
                    confidence=PERSON_CONFIDENCE,
                    source="spacy",
                )
            )

    return matches


def detect_pii(text: str, enabled_categories: dict = None) -> list:
    """Run all detectors and return a de-duplicated, offset-sorted list of
    PIIMatch objects. Overlapping matches are resolved by preferring the
    higher-confidence (generally regex) match, then the longer span.
    """
    enabled_categories = enabled_categories or DEFAULT_ENABLED_CATEGORIES

    all_matches = []
    all_matches.extend(_detect_regex_matches(text, enabled_categories))
    all_matches.extend(_detect_dates_of_birth(text, enabled_categories))
    all_matches.extend(_detect_addresses(text, enabled_categories))
    all_matches.extend(_detect_person_names(text, enabled_categories))

    return _resolve_overlaps(all_matches)


def _resolve_overlaps(matches: list) -> list:
    """Greedy interval scheduling: sort by (confidence desc, length desc),
    keep a match only if it doesn't overlap one already kept.
    """
    ordered = sorted(
        matches, key=lambda m: (-m.confidence, -(m.end - m.start), m.start)
    )

    kept = []
    occupied = []  # list of (start, end) already claimed

    for match in ordered:
        overlaps = any(
            match.start < end and match.end > start for start, end in occupied
        )
        if not overlaps:
            kept.append(match)
            occupied.append((match.start, match.end))

    return sorted(kept, key=lambda m: m.start)
