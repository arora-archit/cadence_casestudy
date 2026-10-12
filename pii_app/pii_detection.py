"""PII detection: Presidio (structured patterns + spaCy NER) plus one
custom heuristic (ADDRESS) that Presidio has no fixed shape for.

Why Presidio: it gives real phone-number validation (`phonenumbers`
library — actual national number-plan rules, not "10 digits"), a
context-aware scorer (boosts a match's confidence when a relevant keyword
sits nearby, replacing a hand-written character-offset window), and a
single recognizer-registry architecture — see pii_app/presidio_engine.py
for the custom AADHAAR/PAN/EMPLOYEE_ID/DATE_OF_BIRTH/PINCODE recognizers
registered into it, each backed by real validation where one exists
(checksums.py).

Presidio's own PERSON recognizer is just spaCy's NER under the hood, so
it inherits the same failure mode as before: a small general-English
model reads Title-Cased business jargon ("TPRM", "Trigger", "Vendor
Tier") as names, and text joined across paragraphs/table cells with bare
"\\n" (no sentence punctuation) gets multiple adjacent names fused into
one entity. _looks_like_person_name() and the per-line split in
_filter_person_result() are the same precision fix as before, just
applied to Presidio's RecognizerResult instead of a raw spaCy entity.

All detectors emit PIIMatch objects with character offsets into the
ORIGINAL text, so redaction can be done purely by offset without
re-scanning text.
"""

import re
from dataclasses import dataclass

from pii_app.config import (
    ADDRESS_KEYWORDS,
    DEFAULT_ENABLED_CATEGORIES,
    DEFAULT_MIN_CONFIDENCE,
    PERSON_MAX_WORDS,
    PERSON_NAME_STOPWORDS,
)
from pii_app.presidio_engine import get_analyzer

# Word shapes accepted inside a candidate person name: ordinary title-case
# words (allowing an internal apostrophe/hyphen, e.g. "O'Brien", "Szeto-Lin")
# and short all-caps tokens treated as initials ("KC", "DK").
_TITLE_CASE_WORD = re.compile(r"^[A-Z][a-z]*(?:['’\-][A-Za-z]+)*$")
_INITIALS_WORD = re.compile(r"^[A-Z]{1,3}$")

# Characters stripped from the edges of a candidate name/address segment
# before validation (punctuation left over from sentence/list formatting).
_EDGE_PUNCT = " \t:;,.()[]\"'"

# Our category names <-> Presidio's entity type names.
_LABEL_TO_PRESIDIO_ENTITY = {
    "EMAIL": "EMAIL",
    "PHONE": "PHONE_NUMBER",
    "PERSON": "PERSON",
    "AADHAAR": "AADHAAR",
    "PAN": "PAN",
    "EMPLOYEE_ID": "EMPLOYEE_ID",
    "DATE_OF_BIRTH": "DATE_OF_BIRTH",
    "PINCODE": "PINCODE",
}
_PRESIDIO_ENTITY_TO_LABEL = {v: k for k, v in _LABEL_TO_PRESIDIO_ENTITY.items()}


@dataclass
class PIIMatch:
    label: str
    start: int
    end: int
    text: str
    confidence: float
    source: str  # "presidio" or "regex" (the ADDRESS heuristic)


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


def _filter_person_result(text: str, result) -> list:
    """Split a Presidio PERSON result on line breaks and validate each
    piece independently (see module docstring for why the split matters).
    """
    matches = []
    raw = text[result.start:result.end]

    for line_match in re.finditer(r"[^\n]+", raw):
        segment = line_match.group()
        seg_start = result.start + line_match.start()

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
                confidence=result.score,
                source="presidio",
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

    Presidio has no generic unstructured-address recognizer to lean on
    here, so this stays a hand-written heuristic — intentionally simple
    and meant as a starting point for analyst review, not a precise
    address parser.
    """
    if not enabled_categories.get("ADDRESS", True):
        return []

    matches = []

    for keyword_match in _ADDRESS_KEYWORD_PATTERN.finditer(text):
        keyword_end = keyword_match.end()

        line_end = text.find("\n", keyword_end)
        if line_end == -1:
            line_end = len(text)

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


def detect_pii(text: str, enabled_categories: dict = None) -> list:
    """Run Presidio plus the address heuristic and return a de-duplicated,
    offset-sorted list of PIIMatch objects. Overlapping matches are
    resolved by preferring the higher-confidence match, then the longer
    span; matches below DEFAULT_MIN_CONFIDENCE are dropped afterward.

    Each category's base confidence (config.py) is deliberately tuned
    against this threshold: AADHAAR/PAN sit just above it so an
    unverified-but-shape-matching ID still surfaces for review, while a
    bare DATE_OF_BIRTH candidate sits below it and only clears the bar
    once Presidio's context-aware enhancer boosts it (i.e. a DOB keyword
    was actually nearby) — see presidio_engine.py.
    """
    enabled_categories = enabled_categories or DEFAULT_ENABLED_CATEGORIES

    requested_entities = [
        presidio_entity
        for label, presidio_entity in _LABEL_TO_PRESIDIO_ENTITY.items()
        if enabled_categories.get(label, True)
    ]

    all_matches = []

    if requested_entities:
        analyzer = get_analyzer()
        results = analyzer.analyze(text=text, language="en", entities=requested_entities)

        for result in results:
            label = _PRESIDIO_ENTITY_TO_LABEL[result.entity_type]
            if label == "PERSON":
                all_matches.extend(_filter_person_result(text, result))
            else:
                all_matches.append(
                    PIIMatch(
                        label=label,
                        start=result.start,
                        end=result.end,
                        text=text[result.start:result.end],
                        confidence=result.score,
                        source="presidio",
                    )
                )

    all_matches.extend(_detect_addresses(text, enabled_categories))

    resolved = _resolve_overlaps(all_matches)
    return [m for m in resolved if m.confidence >= DEFAULT_MIN_CONFIDENCE]


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
