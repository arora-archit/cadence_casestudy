"""
Configurable PII detection settings.

Each entry in REGEX_PATTERNS defines a structured PII type detected via
regular expressions. Add, remove, or tweak patterns here without touching
detection logic elsewhere in the app.

Fields:
    label:       Category name used in reports and redaction placeholders.
    pattern:     Compiled-at-load regex (case-insensitive by default).
    confidence:  Static confidence score reported to the user (0-1).
                 Regex matches are deterministic, so these are high but not
                 all patterns are equally reliable (see README limitations).
"""

import re

REGEX_PATTERNS = {
    "EMAIL": {
        "label": "EMAIL",
        "pattern": re.compile(
            r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        ),
        "confidence": 0.95,
    },
    "PHONE": {
        "label": "PHONE",
        # Indian mobile numbers, with or without +91/0 prefix, optional
        # spacing/hyphens. Deliberately conservative to limit false positives
        # on generic 10-digit numbers (e.g. employee IDs).
        "pattern": re.compile(
            r"(?:\+91[\-\s]?|0)?[6-9]\d{9}\b"
        ),
        "confidence": 0.80,
    },
    "AADHAAR": {
        "label": "AADHAAR",
        # 12 digits, optionally grouped as 4-4-4 with spaces or hyphens.
        "pattern": re.compile(
            r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"
        ),
        "confidence": 0.75,
    },
    "PAN": {
        "label": "PAN",
        # Indian PAN: 5 letters, 4 digits, 1 letter.
        "pattern": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
        "confidence": 0.90,
    },
    "EMPLOYEE_ID": {
        "label": "EMPLOYEE_ID",
        # Common internal ID conventions: EMP-1234, EMP12345, E-00123, etc.
        "pattern": re.compile(r"\b(?:EMP|EID)[\-_]?\d{3,8}\b", re.IGNORECASE),
        "confidence": 0.85,
    },
    "DATE_OF_BIRTH": {
        "label": "DATE_OF_BIRTH",
        # dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy — flagged as DOB only when
        # near a DOB keyword by the detector (see pii_detection.py), since
        # a bare date could be any date.
        "pattern": re.compile(
            r"\b\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}\b"
        ),
        "confidence": 0.60,
    },
    "PINCODE": {
        "label": "PINCODE",
        "pattern": re.compile(r"\b\d{6}\b"),
        "confidence": 0.55,
    },
}

# Keywords that, when found within this many characters before a DATE match,
# upgrade a generic date into a DATE_OF_BIRTH detection.
DOB_KEYWORD_WINDOW = 25
DOB_KEYWORDS = ["dob", "date of birth", "born", "birth date"]

# Keywords that, when found on the same line as a PINCODE/number run,
# help flag an ADDRESS block. Simple heuristic, not a full NLP parse.
ADDRESS_KEYWORDS = ["address", "residing at", "resident of", "flat", "street", "road", "sector"]

# spaCy model used for PERSON name detection. "en_core_web_sm" is small and
# fast but prone to tagging title-cased business jargon (headers, product
# names, acronyms) as PERSON — see PERSON_NAME_STOPWORDS below for the
# mitigation. For higher-precision production use, swap in
# "en_core_web_lg" or "en_core_web_trf" (larger download, slower, more
# accurate) without changing any detection code.
SPACY_MODEL = "en_core_web_sm"

# Confidence assigned to spaCy PERSON detections.
PERSON_CONFIDENCE = 0.70

# A raw spaCy PERSON entity is only accepted as a name if it survives
# _looks_like_person_name() in pii_detection.py:
#   - 2 to PERSON_MAX_WORDS words (full names only — filters single-word
#     noise like "TPRM", "Workflow", "Trigger" outright)
#   - every word is alphabetic title-case (allows apostrophes/hyphens) or
#     a short (<=3 letter) all-caps token treated as initials ("KC", "DK")
#   - no word, once lowercased and stripped of a trailing possessive "'s",
#     appears in PERSON_NAME_STOPWORDS
# This is a precision-over-recall tradeoff appropriate for jargon-heavy
# corporate documents; see README "Limitations" for what it costs.
PERSON_MAX_WORDS = 4

# Domain/business nouns that are commonly Title-Cased in headers and
# templates and get misread as proper nouns by a small NER model. Extend
# this list per-document-set rather than relying on the model alone.
PERSON_NAME_STOPWORDS = {
    "tier", "workflow", "workflows", "trigger", "vendor", "vendors",
    "change", "type", "created", "description", "key", "diligence",
    "questionnaire", "questionnaires", "artificial", "intelligence",
    "cloud", "apps", "group", "groups", "template", "templates",
    "background", "navigate", "appendix", "document", "revision",
    "composed", "email", "database", "metadata", "admin", "privacy",
    "shield", "procurement", "finance", "it", "risk", "management",
    "tprm", "cadence", "ironclad", "optiv", "launching", "due",
    "disclosures", "approved", "contains", "reassessment", "custom",
    "no", "timeline", "custom field", "reviewed", "status", "stage",
    "process", "policy", "section", "overview", "summary", "scope",
    "purpose", "objective", "attachment", "attachments", "confidential",
}

# Minimum confidence a detection must have to be shown/redacted by default.
DEFAULT_MIN_CONFIDENCE = 0.5

# Which PII categories are active by default. UI can toggle these.
DEFAULT_ENABLED_CATEGORIES = {
    "PERSON": True,
    "EMAIL": True,
    "PHONE": True,
    "AADHAAR": True,
    "PAN": True,
    "EMPLOYEE_ID": True,
    "DATE_OF_BIRTH": True,
    "ADDRESS": True,
    "PINCODE": False,  # noisy on its own; off by default, address heuristic uses it
}
